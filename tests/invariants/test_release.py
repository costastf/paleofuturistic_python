"""Invariants over the release flow: commit, changelog, bump, tag, attest and publish."""

import ast
import re
import subprocess
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

# conftest.py wires sys.path so _CI.tasks.* is importable; pytest loads it
# before this module, which is why no path setup is needed here.
from .support import (
    HOOK_FAILED,
    RELEASE_DETECTION,
    SIGNING_FAILED,
    StubContext,
    collect_nav_pages,
    exec_from,
    load_generated_configuration,
    load_generated_shared,
    step_index,
    stub_result,
)


def test_gitlab_release_mr_is_implemented(generated_project):
    """`create_release_pr` calls the MR API and URL-encodes the project path.

    An unencoded (nested) group path 404s, so the encoding is the part worth pinning.
    """
    project, cell = generated_project
    if cell['git_hosting_service'] != 'gitlab':
        pytest.skip('github combo')
    gitlab_py = (project / '_CI' / 'tasks' / 'gitlab.py').read_text(encoding='utf-8')
    tree = ast.parse(gitlab_py)
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'create_release_pr')
    body = ast.unparse(func)
    assert 'not yet implemented' not in body, 'create_release_pr is still a stub'
    assert '/api/v4/projects/' in body, 'no call to the projects API'
    assert 'merge_requests' in body, 'no call to the merge-requests endpoint'
    assert 'GITLAB_TOKEN' in body, 'no documented token is read'
    assert "quote(origin.path, safe='')" in body, 'the project path is not URL-encoded'


def test_commit_leaves_signing_to_git_when_it_succeeds(generated_project):
    """A successful commit carries no signing flag at all — git honours `commit.gpgsign`."""
    project, _ = generated_project
    context = StubContext([('git commit', stub_result())])
    load_generated_shared(project).commit(context, 'docs: update changelog')
    assert context.commands == ['git commit -m "docs: update changelog"']


def test_commit_retries_unsigned_when_no_signing_key_is_available(generated_project):
    """Signing configured but unusable — the CI case — falls back so the release continues."""
    project, _ = generated_project
    context = StubContext(
        [
            ('--no-gpg-sign', stub_result()),
            ('git commit', stub_result(ok=False, stderr=SIGNING_FAILED)),
            ('commit.gpgsign', stub_result(stdout='true\n')),
        ]
    )
    load_generated_shared(project).commit(context, 'docs: update changelog')
    assert context.commands[-1] == 'git commit --no-gpg-sign -m "docs: update changelog"'


def test_commit_does_not_retry_when_a_hook_failed(generated_project):
    """A failing pre-commit hook must not be reported or retried as a signing problem."""
    project, _ = generated_project
    context = StubContext(
        [
            ('git commit', stub_result(ok=False, stderr=HOOK_FAILED)),
            ('commit.gpgsign', stub_result(stdout='true\n')),
        ]
    )
    with pytest.raises(SystemExit):
        load_generated_shared(project).commit(context, 'docs: update changelog')
    assert not any('--no-gpg-sign' in cmd for cmd in context.commands), 'retried a non-signing failure'


def test_commit_does_not_retry_when_signing_was_not_requested(generated_project):
    """Both guards are required: without `commit.gpgsign` the fallback must not engage."""
    project, _ = generated_project
    context = StubContext(
        [
            ('git commit', stub_result(ok=False, stderr=SIGNING_FAILED)),
            ('commit.gpgsign', stub_result(stdout='false\n')),
        ]
    )
    with pytest.raises(SystemExit):
        load_generated_shared(project).commit(context, 'docs: update changelog')
    assert not any('--no-gpg-sign' in cmd for cmd in context.commands), 'retried without signing configured'


def test_signing_requested_reads_the_normalized_boolean(generated_project):
    """`--type=bool` is what makes `yes`/`on`/`1` safe to compare against `true`."""
    project, _ = generated_project
    shared = load_generated_shared(project)
    context = StubContext([('commit.gpgsign', stub_result(stdout='true\n'))])
    assert shared.signing_requested(context) is True
    assert '--type=bool' in context.commands[0], 'the config read does not normalize the value'
    unset = StubContext([('commit.gpgsign', stub_result(ok=False))])
    assert shared.signing_requested(unset) is False


def test_changelog_never_forces_an_unsigned_commit(generated_project):
    """`release.changelog --write` must not hardcode `--no-gpg-sign`; only the fallback may."""
    project, _ = generated_project
    release_py = (project / '_CI' / 'tasks' / 'release.py').read_text(encoding='utf-8')
    assert '--no-gpg-sign' not in release_py, 'release.py forces an unsigned commit'
    assert 'commit(context,' in release_py, 'the changelog commit does not route through shared.commit'


def test_changelog_skips_the_commit_when_nothing_is_staged(generated_project):
    """Regenerating an unchanged changelog is a no-op, not a failed commit on an empty index."""
    project, _ = generated_project
    release_py = (project / '_CI' / 'tasks' / 'release.py').read_text(encoding='utf-8')
    tree = ast.parse(release_py)
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'changelog')
    body = ast.unparse(func)
    assert 'git diff --cached --quiet' in body, 'the changelog commit is not guarded by a staged-changes check'


def test_publish_is_one_task_plus_provenance_over_what_it_uploaded(generated_project):
    """The GitHub publish job hands the push to `release.ship` and attests the files it uploaded.

    One workflow command carries the logic, the same one the GitLab job runs, so the two
    pipelines cannot drift. `release.tag` inside it creates the tag through the API, which is
    why the job holds `contents: write` and the step gets `GITHUB_TOKEN`. Provenance runs
    afterwards, only when a release shipped, over the wheel and sdist still in `dist/` — not
    `dist/*`, which would also attest the `.publish.attestation` files beside them.
    """
    project, cell = generated_project
    if cell['git_hosting_service'] != 'github':
        pytest.skip('GitHub-only workflow')
    config = yaml.safe_load((project / '.github' / 'workflows' / 'publish.yaml').read_text(encoding='utf-8'))
    job = config['jobs']['publish']
    assert job['permissions']['contents'] == 'write', 'release.tag cannot create the tag without Contents: write'
    steps = job['steps']
    commands = [step.get('run') for step in steps if step.get('run')]
    assert commands == [RELEASE_DETECTION.format(task='release.ship')], f'the publish job runs {commands}'
    ship = step_index(steps, 'release.ship')
    assert 'GITHUB_TOKEN' in steps[ship]['env'], 'the ship step has no token to create the tag with'
    assert {'UV_PUBLISH_URL', 'UV_PUBLISH_USERNAME', 'UV_PUBLISH_PASSWORD'} <= set(steps[ship]['env'])
    provenance = step_index(steps, 'attest-build-provenance')
    assert ship < provenance, 'provenance is taken before the files exist'
    assert steps[provenance]['if'] == "${{ steps.ship.outputs.tag != '' }}", 'provenance runs with nothing to attest'
    subjects = steps[provenance]['with']['subject-path'].split()
    assert subjects == ['dist/*.whl', 'dist/*.tar.gz'], f'provenance covers {subjects}'


def test_ship_publishes_a_version_bump_however_it_was_merged(generated_project, tmp_path):
    """`release.ship` publishes when the pushed range bumped the version, from the new tip.

    Exercised against a real git history: a release branch squash-merged into main — the case
    a tag-on-branch design lost — is detected, tagged on the squash commit through the host
    API, built, signed and uploaded, with `dist/` left for provenance. A push with no bump
    publishes nothing and exits 0. The tag is created once: a re-run that finds the tag on the
    same commit carries on without creating it again.
    """
    project, _ = generated_project
    repo = tmp_path / 'repo'
    repo.mkdir()

    def git(*args: str) -> str:
        identity = ('-c', 'user.name=t', '-c', 'user.email=t@example.com', '-c', 'commit.gpgsign=false')
        return subprocess.run(
            ['git', *identity, *args], cwd=repo, check=True, capture_output=True, text=True
        ).stdout.strip()

    def set_version(version: str) -> None:
        (repo / 'pyproject.toml').write_text(f'[project]\nname = "x"\nversion = "{version}"\n', encoding='utf-8')

    git('init', '-q', '-b', 'main')
    set_version('0.1.0')
    git('add', 'pyproject.toml')
    git('commit', '-q', '-m', 'init')
    before = git('rev-parse', 'HEAD')
    git('checkout', '-q', '-b', 'release/0.2.0')
    set_version('0.2.0')
    git('commit', '-q', '-am', 'bump: version 0.1.0 → 0.2.0')
    git('checkout', '-q', 'main')
    git('merge', '-q', '--squash', 'release/0.2.0')
    git('commit', '-q', '-m', 'chore(release): v0.2.0 (#1)')
    after = git('rev-parse', 'HEAD')

    class RepoContext:
        """`context.run` against the scratch repository, with invoke's `Result` shape."""

        def run(self, command: str, **_kwargs: object) -> SimpleNamespace:
            done = subprocess.run(command, shell=True, cwd=repo, capture_output=True, text=True, check=False)  # noqa: S602
            return SimpleNamespace(failed=done.returncode != 0, stdout=done.stdout, stderr=done.stderr)

    ran: list[str] = []
    created: list[tuple[str, str]] = []
    tags: dict[str, str] = {}

    def create_release(_context, tag, sha):
        created.append((tag, sha))
        tags[tag] = sha
        return f'https://example.invalid/releases/{tag}'

    namespace = exec_from(
        (project / '_CI' / 'tasks' / 'release.py').read_text(encoding='utf-8'),
        'NO_PREVIOUS_TIP',
        'project_version',
        'version_at',
        'commit_sha',
        'released_version',
        'record_outputs',
        'tag_release',
        'ship',
        tomllib=tomllib,
        Path=Path,
        Context=object,
        task=lambda *args, **_kwargs: args[0] if args else (lambda fn: fn),
        logged=lambda _name: lambda fn: fn,
        execute=lambda context, command: context.run(command),
        dist=lambda _context: ran.append('dist'),
        attest=lambda _context: ran.append('attest'),
        upload=lambda _context: ran.append('upload'),
        release_tag_commit=lambda _context, tag: tags.get(tag, ''),
        create_release=create_release,
    )
    released_version, ship = namespace['released_version'], namespace['ship']
    context = RepoContext()

    assert released_version(context, before, after) == ('v0.2.0', after), 'a squash-merged bump is not a release'
    assert released_version(context, before, before) is None
    assert released_version(context, '0' * 40, after) is None, 'a branch creation is not a release'
    assert released_version(context, '', after) == ('v0.2.0', after), 'no lower bound compares the tip with its parent'

    outputs = tmp_path / 'outputs'
    ship(context, before=before, after=before, output=str(outputs))
    assert ran == [], 'a push with no bump published'
    assert outputs.read_text(encoding='utf-8') == 'tag=\nsha=\n', 'outputs are not written when there is no release'

    ship(context, before=before, after=after)
    assert ran == ['dist', 'attest', 'upload'], 'ship does not build, sign and upload in that order'
    assert created == [('v0.2.0', after)], 'the tag is not created on the new tip of main'

    ship(context, before=before, after=after)
    assert created == [('v0.2.0', after)], 'a re-run created the tag again'
    assert ran == ['dist', 'attest', 'upload'] * 2, 'a re-run does not retry the upload'


def test_oidc_detection_names_the_hosts_own_token(generated_project):
    """`OIDC_ENV_VARS` is what the chosen host injects, or Trusted Publishing is never detected."""
    project, cell = generated_project
    expected = {
        'github': ('ACTIONS_ID_TOKEN_REQUEST_URL', 'ACTIONS_ID_TOKEN_REQUEST_TOKEN'),
        'gitlab': ('PYPI_ID_TOKEN',),
    }[cell['git_hosting_service']]
    actual = load_generated_configuration(project).OIDC_ENV_VARS
    assert actual == expected, f'OIDC_ENV_VARS is {actual}, the host injects {expected}'


def test_publish_skips_attestations_only_on_the_credential_path(generated_project):
    """Credentials upload without attestations; OIDC uploads through Trusted Publishing.

    PyPI accepts attestations only from a Trusted Publisher, and other indexes may reject an
    upload that carries them, so the credential path must pass `--no-attestations`. The OIDC
    path must force Trusted Publishing, or a missing publisher on PyPI would surface as a
    confusing credential prompt instead of an OIDC error.
    """
    project, _ = generated_project
    source = (project / '_CI' / 'tasks' / 'release.py').read_text(encoding='utf-8')
    commands = re.findall(r"command = '(uv publish[^']*)'", source)
    assert sorted(commands) == [
        'uv publish --trusted-publishing always',
        'uv publish --trusted-publishing never --no-attestations',
    ], f'publish commands: {commands}'
    assert "execute(context, 'uv publish')" not in source, 'a bare `uv publish` bypasses the mode choice'


def test_build_checks_the_distributions_it_builds(generated_project):
    """`build.package` runs twine and check-wheel-contents over wheels and sdists by name.

    `dist/*` would also match the `.publish.attestation` files `release.attest` writes, which
    neither tool accepts, so a rebuild after signing would fail for no real reason.
    """
    project, _ = generated_project
    source = (project / '_CI' / 'tasks' / 'build.py').read_text(encoding='utf-8')
    assert "'uv build'" in source
    assert "'uv run twine check --strict dist/*.whl dist/*.tar.gz'" in source
    assert "'uv run check-wheel-contents dist/*.whl'" in source
    assert "dist/*'" not in source, 'a bare dist/* glob reaches a checker'
    assert 'dist/* ' not in source, 'a bare dist/* glob reaches a checker'


def test_pypirc_is_never_committed(generated_project):
    """`.pypirc` is gitignored: this project never reads one, so one in the tree is a leak."""
    project, _ = generated_project
    ignored = (project / '.gitignore').read_text(encoding='utf-8').splitlines()
    assert '.pypirc' in ignored


def test_changelog_is_one_file_everywhere(generated_project):
    """commitizen, `release.changelog`, the docs nav and the Changelog URL name the same file.

    They once disagreed: commitizen wrote `docs/changelog.md`, which no nav entry listed, while
    the nav's Reference → Changelog was a placeholder no release touched. Every release then
    updated a page nobody could reach from the site and left the reachable one stale.
    """
    project, _ = generated_project
    pyproject = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    written = pyproject['tool']['commitizen']['changelog_file']
    staged = load_generated_configuration(project).CHANGELOG_FILE.as_posix()
    assert staged == written, f'release.changelog stages {staged}, commitizen writes {written}'
    # Incremental, or every release rewrites the page and drops its title and intro.
    assert pyproject['tool']['commitizen'].get('changelog_incremental') is True
    nav = collect_nav_pages(yaml.safe_load((project / 'properdocs.yml').read_text(encoding='utf-8'))['nav'])
    assert written.removeprefix('docs/') in nav, f'{written} is not in the docs nav'
    assert (project / written).is_file(), f'{written} does not ship, so the nav entry is broken before a release'
    url = pyproject['project'].get('urls', {}).get('Changelog')
    if url:
        assert url.endswith(f'/HEAD/{written}'), f'the Changelog URL {url} is not {written}'


def test_prebuilt_publish_never_rebuilds(generated_project):
    """`publish --prebuilt` must not call `dist()`, or CI would publish unattested files."""
    project, _ = generated_project
    release_py = (project / '_CI' / 'tasks' / 'release.py').read_text(encoding='utf-8')
    tree = ast.parse(release_py)
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'publish')
    guarded = [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.If) and any('dist(context)' in ast.unparse(child) for child in node.body)
    ]
    assert guarded, 'publish() calls dist() unconditionally; --prebuilt would still rebuild'
    assert 'prebuilt' in ast.unparse(guarded[0].test), 'the rebuild is not guarded by the prebuilt flag'


def test_a_failed_bump_leaves_no_badge_for_it(generated_project):
    """`release.bump` puts the version badge back when `cz bump` refuses.

    The badge is written first on purpose, so `cz bump` sweeps it into the commit the release
    tag points at. That leaves the failure case to handle: `cz bump` refuses on a dirty tree,
    an unparseable history or a hook it cannot satisfy, and a badge announcing a version
    nobody released is worse than the failure that caused it. The restore reads the version
    from pyproject.toml, which a failed bump has not touched, and goes through `apply_badge`
    like every other write.
    """
    project, _ = generated_project
    release = (project / '_CI' / 'tasks' / 'release.py').read_text(encoding='utf-8')
    body = release.split('def bump', 1)[1].split('\n@task', 1)[0]
    assert 'except SystemExit:' in body, 'a failed bump keeps the badge it wrote'
    restore = body.split('except SystemExit:', 1)[1]
    assert 'update_package_version_badge()' in restore, 'the restore does not go through the one writer'
    assert 'raise' in restore, 'the failure is swallowed'
