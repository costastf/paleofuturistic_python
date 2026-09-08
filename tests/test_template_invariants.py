"""Per-axis invariants over the cartesian product of copier answer combinations.

Each test below receives one generated project per matrix cell via the
``generated_project`` fixture in ``conftest.py``. Adding a new assertion is one
new ``test_*`` function; adding a new combo axis edits ``matrix_combos()`` in
``_CI/tasks/configuration.py`` and both the pytest suite and the Invoke matrix
runner pick it up automatically.
"""

import ast
import importlib.util
import inspect
import json
import os
import re
import subprocess
import tomllib
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

# conftest.py wires sys.path so _CI.tasks.* is importable; pytest loads it
# before this module, which is why no path setup is needed here.
from _CI.tasks.configuration import (  # noqa: E402
    PROJECT_SLUG,
    UV_VERSION_ENV,
    generation_env,
    matrix_combos,
    template_uv_version,
)


def test_host_scaffolding_present(generated_project):
    """`.github/workflows/` ships only for github; `.gitlab-ci.yml` ships only for gitlab."""
    project, cell = generated_project
    if cell['git_hosting_service'] == 'github':
        assert (project / '.github' / 'workflows').is_dir()
        assert not (project / '.gitlab-ci.yml').exists()
    else:
        assert not (project / '.github').exists()
        assert (project / '.gitlab-ci.yml').exists()


def test_host_submodule_present(generated_project):
    """`_CI/tasks/<host>.py` is present for the chosen host and absent for the other."""
    project, cell = generated_project
    chosen_name = cell['git_hosting_service']
    other_name = 'gitlab' if chosen_name == 'github' else 'github'
    assert (project / '_CI' / 'tasks' / f'{chosen_name}.py').exists()
    assert not (project / '_CI' / 'tasks' / f'{other_name}.py').exists()


def test_pages_workflow_matches_choice(generated_project):
    """`pages.yaml` ships iff integrate_pages=true AND the host is github."""
    project, cell = generated_project
    expected = cell['integrate_pages'] and cell['git_hosting_service'] == 'github'
    assert (project / '.github' / 'workflows' / 'pages.yaml').exists() == expected


def test_docs_publish_on_release_not_on_every_push(generated_project):
    """The site is published when a release lands, by the same rule the package uses.

    Built from every push to main, the docs describe code that is on main but in no release
    yet, so a reader following them can reach for something they cannot install. And a
    `push: tags:` trigger would be the same mistake mirrored: `release` pushes the tag from the
    release branch before the pull request merges, so the site would go out for a version that
    has not landed.

    So both this and `publish.yaml` trigger on a push to main and ask one reusable workflow
    whether it carried a v-prefixed tag — one copy of that question, so the package and its
    documentation cannot disagree about what counts as released. `workflow_dispatch` stays,
    because a project that has not released yet would otherwise never publish docs at all.
    """
    project, cell = generated_project
    # Pages ships for GitHub only, as `test_pages_workflow_matches_choice` asserts.
    if not cell['integrate_pages'] or cell['git_hosting_service'] != 'github':
        return
    workflows = project / '.github' / 'workflows'
    shared = 'detect-release-tag.yaml'
    assert (workflows / shared).is_file(), 'the shared release-tag detector does not ship'

    pages = yaml.safe_load((workflows / 'pages.yaml').read_text(encoding='utf-8'))
    triggers = pages.get('on') or pages[True]
    assert 'tags' not in (triggers.get('push') or {}), 'a tag trigger fires before the release merges'
    assert 'workflow_dispatch' in triggers, 'a project that has not released yet could never publish docs'
    assert pages['jobs']['detect']['uses'].endswith(shared), 'pages does not use the shared detector'
    guard = pages['jobs']['deploy']['if']
    assert "needs.detect.outputs.tag != ''" in guard, f'pages deploys without a release tag: {guard!r}'
    assert 'workflow_dispatch' in guard, f'a manual run could never deploy: {guard!r}'

    publish = (workflows / 'publish.yaml').read_text(encoding='utf-8')
    assert shared in publish, 'publish and pages no longer share one definition of "released"'


def test_release_detection_pins_a_commit_and_bounds_its_search(generated_project):
    """The detector reports the commit it found, and only looks at commits that arrived.

    Callers check out `sha`, not `tag`: a tag is a mutable pointer, so a move between detection
    and checkout would publish a different tree than was detected.

    The search range comes from the event. Only a push has a previous tip to diff against; on a
    manual run `github.event.before` is empty, and walking from the tip with no lower bound
    would sweep in every release the branch ever carried and report the newest as arriving now
    — publishing an old version's docs from a dispatch meant to republish the current ones.
    """
    project, cell = generated_project
    if cell['git_hosting_service'] != 'github':
        return
    workflows = project / '.github' / 'workflows'
    detector = (workflows / 'detect-release-tag.yaml').read_text(encoding='utf-8')
    parsed = yaml.safe_load(detector)

    outputs = ((parsed.get('on') or parsed[True])['workflow_call'])['outputs']
    assert 'sha' in outputs, 'the detector reports a mutable tag name and nothing else'
    assert 'sha=${tag_sha}' in detector, 'the sha output is declared but never written'

    assert 'github.event_name' in detector, 'the search range ignores how the workflow was triggered'
    assert '--max-count=1' in detector, 'a non-push event walks the whole history for a tag'
    assert '-z "${BEFORE}"' not in detector, 'an empty before-sha is still read as a new branch'

    consumers = ['publish.yaml']
    if cell['integrate_pages']:
        consumers.append('pages.yaml')
    for name in consumers:
        body = (workflows / name).read_text(encoding='utf-8')
        assert 'ref: ${{ needs.detect.outputs.tag }}' not in body, f'{name} checks out a mutable tag name'
        assert 'ref: ${{ needs.detect.outputs.sha }}' in body, f'{name} does not check out the detected commit'


def test_pages_task_definition_matches_choice(generated_project):
    """`deploy_github` is defined iff integrate_pages=true AND the host is github."""
    project, cell = generated_project
    expected = cell['integrate_pages'] and cell['git_hosting_service'] == 'github'
    document_py = (project / '_CI' / 'tasks' / 'document.py').read_text(encoding='utf-8')
    assert ('def deploy_github' in document_py) == expected


def test_dependency_track_imports_match_choice(generated_project):
    """`OWASP_DTRACK_SETTINGS` is imported by secure.py iff integrate_dependency_track=true."""
    project, cell = generated_project
    secure_py = (project / '_CI' / 'tasks' / 'secure.py').read_text(encoding='utf-8')
    assert ('OWASP_DTRACK_SETTINGS' in secure_py) == cell['integrate_dependency_track']


def test_pyproject_is_valid_toml(generated_project):
    """The generated pyproject.toml parses cleanly and carries the expected blocks."""
    project, _ = generated_project
    data = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    assert data['project']['name']
    assert 'dependency-groups' in data


# Rules switched off for `_CI/tasks/sbom.py` because py-serializable annotates an
# intersection as a union. They are the rules most likely to catch a real bug, so the
# scoping is the whole point — see the comment beside the override in the template.
UNION_WORKAROUND_RULES = {
    'unknown-argument',
    'unresolved-attribute',
    'too-many-positional-arguments',
    'invalid-argument-type',
}


def test_ty_suppressions_stay_scoped_to_one_module(generated_project):
    """The py-serializable workaround must never become a project-wide rule change.

    Moving these four rules to `[tool.ty.rules]` would silence them everywhere and look
    like a tidy-up in review, while quietly removing the checks most likely to catch a real
    call-signature bug across the whole project.
    """
    project, _ = generated_project
    ty_config = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))['tool']['ty']
    disabled_globally = UNION_WORKAROUND_RULES & set(ty_config.get('rules', {}))
    assert not disabled_globally, f'ty rules disabled project-wide: {sorted(disabled_globally)}'
    overrides = ty_config.get('overrides', [])
    assert overrides, 'no scoped ty override; the sbom.py workaround has gone missing'
    for override in overrides:
        assert override.get('include'), 'a ty override applies to every file, defeating the scoping'


def python_floor(pyproject):
    """Return the `requires-python` lower bound of a pyproject as a (major, minor) tuple."""
    spec = tomllib.loads(pyproject.read_text(encoding='utf-8'))['project']['requires-python']
    match = re.search(r'>=\s*(\d+)\.(\d+)', spec)
    assert match, f'{pyproject} has no >= lower bound: {spec!r}'
    return int(match.group(1)), int(match.group(2))


def test_ci_tooling_never_claims_a_newer_python_than_the_project(generated_project):
    """`_CI/pyproject.toml` must not require a newer Python than the project itself.

    Ruff resolves that file for everything under `_CI/` and infers its Python target from
    it, but `_CI/tasks/*` runs on the *project's* interpreter. When it claimed 3.12 against a
    3.10 project, ruff offered fixes that would break the generated project at runtime —
    deleting the tomli fallback (UP036) and using the 3.11-only `datetime.UTC` (UP017).
    """
    project, _ = generated_project
    assert python_floor(project / '_CI' / 'pyproject.toml') <= python_floor(project / 'pyproject.toml'), (
        '_CI tooling is linted against a newer Python than the project supports'
    )


def test_workflow_cmd_is_executable(generated_project):
    """The polyglot launcher has the executable bit so `./workflow.cmd …` works on Unix."""
    project, _ = generated_project
    assert os.access(project / 'workflow.cmd', os.X_OK)


def test_sbom_file_path_is_inside_package(generated_project):
    """The SBOM file lands under `src/<slug>/` so `uv build` ships it inside the wheel."""
    project, _ = generated_project
    configuration = (project / '_CI' / 'tasks' / 'configuration.py').read_text(encoding='utf-8')
    assert "SBOM_FILE = Path('src') / PROJECT_NAME / 'sbom.cdx.json'" in configuration


def test_ratchet_defaults_to_auto_detect(generated_project):
    """`[tool.test-ratchet] mode = "auto-detect"` ships by default so the ratchet starts dormant."""
    project, _ = generated_project
    data = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    assert data['tool']['test-ratchet']['mode'] == 'auto-detect'


def test_scaffold_test_sanity_marker_present(generated_project):
    """`def test_sanity` ships in the scaffolded test file — it doubles as the ratchet dormancy marker."""
    project, _ = generated_project
    slug = project.name
    test_file = project / 'tests' / f'test_{slug}.py'
    assert 'def test_sanity' in test_file.read_text(encoding='utf-8')


def collect_nav_pages(nav_entry):
    """Recursively collect the `.md` leaf paths from a properdocs/mkdocs nav structure."""
    pages = []
    if isinstance(nav_entry, str):
        pages.append(nav_entry)
    elif isinstance(nav_entry, list):
        for item in nav_entry:
            pages.extend(collect_nav_pages(item))
    elif isinstance(nav_entry, dict):
        for value in nav_entry.values():
            pages.extend(collect_nav_pages(value))
    return pages


def test_every_environment_variable_the_workflow_reads_is_documented(generated_project):
    """The reference page lists every variable the shipped tasks actually read.

    A variable nobody documents is one nobody sets until a job fails for a reason the log does
    not explain. This walks the task modules for the names they read — through the constants in
    `configuration.py` as well as literal `os.environ` lookups — and requires each to appear on
    the page. Host-specific ones only need to appear for the host that ships them.
    """
    project, _ = generated_project
    tasks = project / '_CI' / 'tasks'
    page = (project / 'docs' / 'developer' / 'reference' / 'environment-and-flags.md').read_text(encoding='utf-8')

    sources = '\n'.join(path.read_text(encoding='utf-8') for path in tasks.glob('*.py'))
    # Both forms. `os.environ['NAME']` is how the deps-image job reads its registry settings,
    # and matching only the call form meant six variables were exempt from this page.
    # Either quote style: an f-string forces the inner lookup to double quotes, and matching
    # only single ones left `os.environ["OWASP_DTRACK_URL"]` invisible to this walk.
    quoted = '[\'"]'
    reads = (
        rf'os\.environ(?:\.get)?\(\s*{quoted}([A-Z][A-Z0-9_]+){quoted}',
        rf'os\.environ\[\s*{quoted}([A-Z][A-Z0-9_]+){quoted}\s*\]',
        rf'os\.getenv\(\s*{quoted}([A-Z][A-Z0-9_]+){quoted}',
        rf'password_env={quoted}([A-Z][A-Z0-9_]+){quoted}',
    )
    literal = {name for pattern in reads for name in re.findall(pattern, sources)}
    # The names the tasks reach through a constant rather than inline.
    for constant in ('OWASP_DTRACK_SETTINGS', 'UV_PUBLISH_SETTINGS', 'OIDC_ENV_VARS'):
        match = re.search(rf'^{constant} = \(([^)]*)\)', sources, re.MULTILINE)
        if match:
            literal.update(re.findall(r"'([A-Z][A-Z0-9_]+)'", match.group(1)))
    override = re.search(r"SECURITY_OVERRIDE_ENV = '([A-Z_]+)'", sources)
    if override:
        literal.add(override.group(1))

    # Set by the runner, not read by us, and covered in prose rather than the table.
    ignored = {'PATH', 'HOME', 'COMSPEC', 'PAGER'}
    # As a code span, not a substring: `INVOKE_SHELL` must not be satisfied by a page that
    # happens to mention `INVOKE_SHELL_SOMETHING_ELSE`.
    documented = set(re.findall(r'`([A-Z][A-Z0-9_]+)`', page))
    undocumented = sorted(literal - ignored - documented)
    assert not undocumented, f'variables the workflow reads but nobody documented: {undocumented}'


def test_docs_nav_resolves(generated_project):
    """Every page listed in the generated properdocs.yml nav exists on disk, for every knob combo."""
    project, _ = generated_project
    config = yaml.safe_load((project / 'properdocs.yml').read_text(encoding='utf-8'))
    missing = [page for page in collect_nav_pages(config['nav']) if not (project / 'docs' / page).is_file()]
    assert not missing, f'nav entries without a file: {missing}'


def test_docs_have_no_orphans(generated_project):
    """Every markdown file shipped under docs/ is reachable from the nav (no silent orphans)."""
    project, _ = generated_project
    config = yaml.safe_load((project / 'properdocs.yml').read_text(encoding='utf-8'))
    nav_pages = set(collect_nav_pages(config['nav']))
    shipped = {str(path.relative_to(project / 'docs')) for path in (project / 'docs').rglob('*.md')}
    orphans = shipped - nav_pages
    assert not orphans, f'docs pages missing from nav: {orphans}'


def test_dependency_track_doc_matches_choice(generated_project):
    """The SBOM-upload how-to (file and nav entry) ships iff integrate_dependency_track=true."""
    project, cell = generated_project
    expected = cell['integrate_dependency_track']
    page = project / 'docs' / 'developer' / 'how-to' / 'upload-an-sbom-to-dependency-track.md'
    assert page.exists() == expected
    nav_text = (project / 'properdocs.yml').read_text(encoding='utf-8')
    assert ('upload-an-sbom-to-dependency-track' in nav_text) == expected


CREDENTIALED_URLS = [
    # (origin URL as CI leaves it, expected published form)
    ('https://x-access-token:ghs_SECRETTOKEN@github.com/owner/repo.git', 'https://github.com/owner/repo.git'),
    ('https://gitlab-ci-token:glcbt-SECRETTOKEN@gitlab.com/group/proj.git', 'https://gitlab.com/group/proj.git'),
    ('https://user:pw@git.example.com:8443/o/r.git', 'https://git.example.com:8443/o/r.git'),
    ('ssh://git@github.com/owner/repo.git', 'ssh://github.com/owner/repo.git'),
    # No userinfo — must pass through byte-for-byte.
    ('https://github.com/owner/repo.git', 'https://github.com/owner/repo.git'),
    ('https://github.com/owner/repo', 'https://github.com/owner/repo'),
    # An `@` outside the netloc is not a credential.
    ('https://github.com/owner/repo@v1.2.3', 'https://github.com/owner/repo@v1.2.3'),
]


def load_uv_release_module():
    """Import `template/_CI/uv_release.py` from source.

    The same file both this repo and generated projects use, so there is one implementation to
    test rather than two that could drift.
    """
    path = REPO_ROOT / 'template' / '_CI' / 'uv_release.py'
    spec = importlib.util.spec_from_file_location('uv_release_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_generated_configuration(project):
    """Import the generated project's `_CI/tasks/configuration.py` as a standalone module.

    Pure stdlib (`re`, `pathlib`), so it loads without the rest of the `_CI.tasks` package.
    """
    path = project / '_CI' / 'tasks' / 'configuration.py'
    spec = importlib.util.spec_from_file_location('generated_configuration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_generated_shared(project):
    """Import the generated project's `_CI/tasks/shared.py` as a standalone module.

    It imports only `invoke`, which ``conftest.py`` already puts on ``sys.path`` via the
    vendored tree, so the module loads without the rest of the `_CI.tasks` package.
    """
    path = project / '_CI' / 'tasks' / 'shared.py'
    spec = importlib.util.spec_from_file_location('generated_shared', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_strip_credentials_removes_userinfo(generated_project):
    """`strip_credentials` drops userinfo and leaves credential-free URLs untouched."""
    project, _ = generated_project
    strip_credentials = load_generated_shared(project).strip_credentials
    for url, expected in CREDENTIALED_URLS:
        assert strip_credentials(url) == expected, f'{url!r} was not sanitized to {expected!r}'


def test_no_token_survives_into_a_published_url(generated_project):
    """No secret and no netloc `@` survives sanitizing — the invariant the SBOM's VCS ref relies on."""
    project, _ = generated_project
    strip_credentials = load_generated_shared(project).strip_credentials
    for url, _expected in CREDENTIALED_URLS:
        sanitized = strip_credentials(url)
        assert 'SECRETTOKEN' not in sanitized, f'token survived sanitizing {url!r}'
        assert '@' not in sanitized.split('//', 1)[-1].split('/', 1)[0], f'userinfo survived in {sanitized!r}'


def test_sbom_and_slug_helpers_sanitize_the_remote(generated_project):
    """Every consumer of `git remote get-url origin` sanitizes it before use.

    `parse_remote_url` counts as sanitizing: it calls `strip_credentials` itself, which
    `test_parse_remote_url_strips_credentials` pins down.
    """
    project, cell = generated_project
    sbom_py = (project / '_CI' / 'tasks' / 'sbom.py').read_text(encoding='utf-8')
    assert 'strip_credentials' in sbom_py, 'sbom.py does not sanitize the origin URL'
    host_py = (project / '_CI' / 'tasks' / f'{cell["git_hosting_service"]}.py').read_text(encoding='utf-8')
    sanitizers = ('strip_credentials', 'parse_remote_url')
    assert any(name in host_py for name in sanitizers), 'origin_slug() does not sanitize the origin URL'


def strip_prose(source):
    """Return `source` as code only — no comments, no docstrings.

    Both routinely mention the very literals a "don't hardcode this" assertion looks for, so
    matching raw text would fail on an explanation of the fix. `ast.unparse` drops comments;
    the docstrings have to be removed by hand.
    """
    tree = ast.parse(source)
    scopes = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, scopes) or len(node.body) < 2:
            continue
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            node.body.pop(0)
    return ast.unparse(tree)


REMOTE_URLS = [
    ('https://gitlab.com/group/project.git', 'gitlab.com', 'group/project'),
    ('git@gitlab.com:group/project.git', 'gitlab.com', 'group/project'),
    # The case the hardcoded gitlab.com match silently dropped.
    ('https://gitlab.example.com/group/project.git', 'gitlab.example.com', 'group/project'),
    ('git@gitlab.example.com:group/project.git', 'gitlab.example.com', 'group/project'),
    # Nested groups: every path segment has to survive.
    ('https://gitlab.example.com/group/sub/deeper/project.git', 'gitlab.example.com', 'group/sub/deeper/project'),
    # No .git suffix, and a trailing slash.
    ('https://gitlab.example.com/group/project/', 'gitlab.example.com', 'group/project'),
    # An https port belongs in the web URL...
    ('https://gitlab.example.com:8443/group/project.git', 'gitlab.example.com:8443', 'group/project'),
    # ...but an ssh port does not.
    ('ssh://git@gitlab.example.com:2222/group/project.git', 'gitlab.example.com', 'group/project'),
]


@pytest.mark.parametrize(('url', 'host', 'path'), REMOTE_URLS)
def test_parse_remote_url_reads_host_and_path(generated_project, url, host, path):
    """The host comes from the remote, so a self-hosted instance is not mistaken for gitlab.com."""
    project, _ = generated_project
    assert load_generated_shared(project).parse_remote_url(url) == (host, path)


def test_parse_remote_url_strips_credentials(generated_project):
    """The token CI bakes into origin never reaches a parsed host or path."""
    project, _ = generated_project
    parse_remote_url = load_generated_shared(project).parse_remote_url
    ref = parse_remote_url('https://gitlab-ci-token:SECRETTOKEN@gitlab.example.com/group/project.git')
    assert ref == ('gitlab.example.com', 'group/project')
    assert 'SECRETTOKEN' not in ref.host + ref.path


def test_parse_remote_url_reports_failure_rather_than_guessing(generated_project):
    """An unparseable remote yields empty strings; callers must not invent a host."""
    project, _ = generated_project
    parse_remote_url = load_generated_shared(project).parse_remote_url
    for url in ('', 'not a url', '/local/path/repo'):
        assert parse_remote_url(url) == ('', ''), f'{url!r} was parsed into something'


def test_gitlab_helpers_never_hardcode_the_instance_host(generated_project):
    """No gitlab.com literal survives in the GitLab module — the host comes from `origin`.

    Hardcoding it made `origin_slug()` return '' on every self-hosted instance, which
    disabled the manual MR URL and the API call without printing anything.
    """
    project, cell = generated_project
    if cell['git_hosting_service'] != 'gitlab':
        pytest.skip('github combo')
    gitlab_py = (project / '_CI' / 'tasks' / 'gitlab.py').read_text(encoding='utf-8')
    assert 'gitlab.com' not in strip_prose(gitlab_py), 'the GitLab instance host is still hardcoded'


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


def stub_result(*, ok=True, stdout='', stderr=''):
    """A stand-in for invoke's `Result`, carrying only what the code under test reads."""
    return SimpleNamespace(ok=ok, failed=not ok, stdout=stdout, stderr=stderr)


class StubContext:
    """Minimal invoke-`Context` stand-in returning canned results and recording every command.

    `responses` is an ordered list of `(fragment, result)` pairs and the first fragment
    contained in the command wins, so more specific commands must come first —
    `git commit --no-gpg-sign` contains `git commit`.
    """

    def __init__(self, responses) -> None:
        """Store the ordered `(fragment, result)` pairs this context will answer with."""
        self.responses = responses
        self.commands = []

    def run(self, cmd, **_kwargs: object):
        """Record `cmd` and return the canned result for the first matching fragment."""
        self.commands.append(cmd)
        for fragment, result in self.responses:
            if fragment in cmd:
                return result
        message = f'unexpected command: {cmd!r}'
        raise AssertionError(message)


# Real `git commit` stderr, captured from git 2.x. The ssh case is used deliberately: it
# contains none of the plausible-looking "signing failed"/"failed to sign" phrasings, so a
# marker matched against those instead of git's summary line fails this test.
SIGNING_FAILED = (
    "error: Couldn't load public key /nonexistent/key.pub: No such file or directory?\n"
    'fatal: failed to write commit object\n'
)
HOOK_FAILED = 'hook says no\n'


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


def test_deps_image_tag_covers_every_content_input(generated_project):
    """The deps-image tag hashes the lockfile, the Dockerfile and the base image, not just the lock.

    Keying on `uv.lock` alone let a `Dockerfile.deps` edit or a base-image bump reuse a
    stale image, because the tag never changed.
    """
    project, _ = generated_project
    container_py = (project / '_CI' / 'tasks' / 'container.py').read_text(encoding='utf-8')
    assert 'def deps_image_tag' in container_py
    tag_source = container_py.split('def deps_image_tag', 1)[1].split('\n@task', 1)[0]
    for required in ('UV_LOCK', 'DOCKERFILE_DEPS', 'info.base-image'):
        assert required in tag_source, f'deps_image_tag() does not hash {required}'
    # Per-input digests are fixed-width, which is what stops ("AB","C") colliding
    # with ("A","BC") and what makes the algorithm reproducible in shell.
    assert 'hexdigest()' in tag_source, 'deps_image_tag() does not fold per-input digests'


def test_gitlab_deps_job_matches_the_python_tag_algorithm(generated_project):
    """GitLab's inlined deps job hashes the same three inputs and pins by digest.

    Its deps job runs in kaniko with no Python, so it cannot call ``deps_image_tag()``
    and reimplements it in shell. That duplicate is easy to leave behind — this pins it.
    """
    project, cell = generated_project
    if cell['git_hosting_service'] != 'gitlab':
        pytest.skip('GitLab-only pipeline')
    pipeline = (project / '.gitlab-ci.yml').read_text(encoding='utf-8')
    deps_job = pipeline.split('build-deps-image:', 1)[1].split('\nlint:', 1)[0]
    for required in ('uv.lock', 'Dockerfile.deps', 'BASE_IMAGE'):
        assert required in deps_job, f'GitLab deps job does not hash {required}'
    assert 'sha256sum uv.lock' in deps_job, 'the deps tag does not hash the lockfile'
    assert 'sha256sum Dockerfile.deps' in deps_job, 'the deps tag does not hash the Dockerfile'
    assert 'cut -c1-16' not in deps_job, 'GitLab deps job still uses the old 64-bit lockfile-only tag'
    assert '--digest-file' in deps_job, 'GitLab deps job does not capture the pushed digest'
    assert 'DEPS_IMAGE=${CI_REGISTRY_IMAGE}@${DIGEST}' in deps_job, 'DEPS_IMAGE is not digest-pinned'


def test_deps_image_reference_is_digest_pinned(generated_project):
    """`container.publish` hands downstream jobs a digest, so a repointed tag can't swap the image."""
    project, cell = generated_project
    host = cell['git_hosting_service']
    host_py = (project / '_CI' / 'tasks' / f'{host}.py').read_text(encoding='utf-8')
    if host == 'github':
        # Daemon-based build: resolve the repo digest of the local image.
        assert 'image_digest_reference' in host_py
        shared = load_generated_shared(project)
        resolver = inspect.getsource(shared.image_digest_reference)
        assert 'RepoDigests' in resolver
        # Parsed as JSON rather than via a Go --format template, which docker and
        # podman expose differently and which needs brace quoting in a shell command.
        assert 'json.loads' in resolver
    else:
        # kaniko is daemonless, so there is no local image to inspect afterwards.
        assert '--digest-file' in host_py


def test_security_audit_is_automated_without_failing_unrelated_changes(generated_project):
    """The audit runs automatically, but never on a push that cannot have caused it.

    Two failure modes, and the fix for one is the cause of the other. Reachable only as a
    local command, the `.security-overrides` expiry mechanism gates nothing and a dependency
    with a known CVE ships green. Wired to every push, it fails pull requests for advisories
    published overnight that the author did not introduce and cannot fix in their branch —
    and a pipeline that goes red for reasons outside the author's control is one people learn
    to ignore.

    So it is automated on the axis it actually varies along: time (a schedule) and the
    dependency surface (the files that can introduce a vulnerable package). Publishing is
    gated separately by `release.dist`.
    """
    project, cell = generated_project
    # The lockfile alone. The project runs `--frozen` throughout, so a `pyproject.toml` edit
    # that changes what is installed changes `uv.lock` with it, while the edits that do not —
    # a ratchet bump, a `cz bump` — used to fire a full audit of an untouched dependency set.
    dependency_surface = {'uv.lock'}
    if cell['git_hosting_service'] == 'github':
        pipeline = (project / '.github' / 'workflows' / 'continuous-integration.yaml').read_text(encoding='utf-8')
        assert 'secure.audit' not in pipeline, 'the per-push pipeline audits every change'
        audit_workflow = yaml.safe_load(
            (project / '.github' / 'workflows' / 'security-audit.yaml').read_text(encoding='utf-8')
        )
        # yaml parses a bare `on:` key as the boolean True, hence the lookup.
        triggers = audit_workflow.get('on') or audit_workflow[True]
        paths = set(triggers['push']['paths'])
        assert dependency_surface <= paths, f'the audit is not triggered by {dependency_surface - paths}'
        assert 'pyproject.toml' not in paths, 'a version bump fires a full dependency audit'
    else:
        jobs = yaml.safe_load((project / '.gitlab-ci.yml').read_text(encoding='utf-8'))
        rules = jobs['secure']['rules']
        assert any('schedule' in str(rule.get('if', '')) for rule in rules), 'no scheduled audit'
        changes = {path for rule in rules for path in rule.get('changes') or []}
        assert dependency_surface <= changes, f'the audit is not triggered by {dependency_surface - changes}'
        assert 'pyproject.toml' not in changes, 'a version bump fires a full dependency audit'


def test_scheduled_security_audit_ships_for_github(generated_project):
    """GitHub projects get a scheduled audit, so expiries come due without a push."""
    project, cell = generated_project
    workflow = project / '.github' / 'workflows' / 'security-audit.yaml'
    if cell['git_hosting_service'] != 'github':
        assert not workflow.exists()
        return
    content = workflow.read_text(encoding='utf-8')
    assert 'schedule:' in content, 'the audit is not scheduled'
    assert 'cron:' in content, 'the schedule has no cron expression'
    assert 'workflow_dispatch:' in content, 'no way to trigger the audit on demand'
    assert 'secure.audit' in content
    config = yaml.safe_load(content)
    # Least privilege: the audit only reads the repo; only the image build may publish.
    assert config['permissions'] == {'contents': 'read'}
    assert config['jobs']['secure']['permissions'] == {'contents': 'read', 'packages': 'read'}


def test_building_a_wheel_does_not_depend_on_the_advisory_database(generated_project):
    """`build` composes the SBOM and builds; it does not audit.

    The SBOM belongs to the build — `uv build` ships it inside the wheel, and it is derived
    from the lockfile and the tree. The audit does not: its answer depends on the advisory
    database on the day it runs, so bundling them meant a newly published CVE made it
    impossible to produce a wheel from code that built yesterday, blocking a hotfix on an
    advisory it had nothing to do with.
    """
    project, _ = generated_project
    build_py = (project / '_CI' / 'tasks' / 'build.py').read_text(encoding='utf-8')
    assert 'run_steps(sbom, package)' in build_py, 'build no longer composes the SBOM before building'
    assert 'from .secure import sbom' in build_py, 'build imports more of secure than the SBOM half'
    # The word appears in the docstring explaining its absence; what must not appear is a call.
    assert 'audit(' not in build_py, 'build audits dependencies again, so a fresh CVE blocks every wheel'


def test_publishing_audits_before_it_builds(generated_project):
    """`release.dist` audits, so the decoupling above does not leave publishing unguarded.

    Publishing is the moment the outside world is exposed to what these dependencies
    contain, and the one place where refusing to proceed protects somebody.
    """
    project, _ = generated_project
    release_py = (project / '_CI' / 'tasks' / 'release.py').read_text(encoding='utf-8')
    dist = release_py.split("@logged('release.dist')", 1)[1].split('@task', 1)[0]
    assert 'audit(context)' in dist, 'release.dist publishes without auditing'
    assert dist.index('audit(context)') < dist.index('build(context)'), 'the audit runs after the build'


def test_qa_steps_cover_what_preflight_does_not():
    """QA_STEPS runs the generated project's own gate, plus the two things it leaves out.

    `preflight` covers format, lint, ty, pyscn, the tox matrix, the wheel and the derived
    files, so naming those separately would re-run them in a different shape and leave the
    matrix with two lists of checks to keep in step — the same duplication the generated
    project's pipeline shed. What has to be listed is what `preflight` deliberately omits:
    the dependency audit, and the docs build.

    `secure.audit` in particular has to be here explicitly. The matrix runner exports
    `<PROJECT>_SECURITY_OVERRIDE` for it, and that plumbing feeds nothing unless it runs.
    """
    from _CI.tasks.configuration import QA_STEPS  # noqa: PLC0415

    assert 'secure.audit' in QA_STEPS
    assert 'preflight --write' in QA_STEPS, 'the matrix no longer exercises the generated gate'
    # The audit last, as in the generated project's own registry: it reports on the world
    # rather than on this tree, so the top of each cell's log is about the thing under test.
    assert QA_STEPS.index('secure.audit') > QA_STEPS.index('preflight --write')


def test_the_matrix_verifies_what_it_wrote():
    """The matrix runs the read-only gate after the writers, on a cell that has values to write.

    `preflight --write` alone cannot catch a writer and a checker disagreeing: it writes and is
    happy. Running the bare `preflight` afterwards asks the question the pipeline asks — is this
    tree consistent with its derived files? — about a tree whose derived files were just
    produced. A deadlock where writing a coverage floor makes the next run fail is invisible
    until something re-reads.

    The eight knob cells have nothing interesting to write: a generated project keeps the
    scaffolded smoke test, so coverage is 100% and the ratchet stays dormant, and it has no
    remote for the CI badge to name. One matured cell removes both of those, which is where a
    disagreement can exist at all.
    """
    from _CI.tasks.configuration import QA_SETTLE_STEP, QA_STEPS, qa_cells  # noqa: PLC0415

    assert QA_SETTLE_STEP == 'preflight', 'the matrix no longer re-checks the tree it wrote'
    assert QA_SETTLE_STEP not in QA_STEPS, 'the gate has to run after the writers, not among them'

    matured = [cell for cell in qa_cells() if cell['mature']]
    assert len(matured) == 1, f'expected exactly one matured cell, got {[c["label"] for c in matured]}'

    from _CI.tasks.test import MATURE_ORIGIN, MATURE_TEST_MODULE  # noqa: PLC0415

    assert 'test_sanity' not in MATURE_TEST_MODULE, 'the ratchet stays dormant while test_sanity exists'
    assert MATURE_ORIGIN, 'without an origin the CI badge has no slug to write'


def workflow_run_scripts(workflow):
    """Yield every `run:` script in a parsed GitHub workflow, with a `job/step` label."""
    for job_name, job in (workflow.get('jobs') or {}).items():
        for index, step in enumerate(job.get('steps') or []):
            script = step.get('run')
            if script:
                yield f'{job_name}/step{index}', script


def test_this_repo_runs_tasks_only_through_the_launcher():
    """No pipeline step assembles its own invoke call; every task goes through `./workflow.cmd`.

    A hand-built `uvx --from invoke --with … invoke --search-root _CI` runs a *different*
    invoke from the one developers use: unpinned, and without the vendored copy's
    search-root patch, which is the only reason such a step needs `PYTHONPATH`. Its `--with`
    list is maintained by hand too, and once left `main` red because `configuration.py`
    imports yaml and the list had no pyyaml.
    """
    for path in sorted((REPO_ROOT / '.github' / 'workflows').glob('*.yaml')):
        workflow = yaml.safe_load(path.read_text(encoding='utf-8'))
        for label, script in workflow_run_scripts(workflow):
            assert '--from invoke' not in script, f'{path.name}:{label} installs invoke itself'
            assert '--search-root' not in script, f'{path.name}:{label} calls invoke directly'


def test_the_launcher_stays_executable():
    """`./workflow.cmd` is committed with its executable bit, or every pipeline step 126s."""
    mode = subprocess.run(
        ['git', 'ls-files', '--stage', 'workflow.cmd'],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()[0]
    assert mode == '100755', f'workflow.cmd is committed as {mode}, not executable'


def test_documented_override_format_is_actually_accepted(generated_project):
    """Every `.security-overrides` example in the docs parses as a real entry.

    The how-to previously documented a space-separated `<ID> <DATE> <justification>` form
    that `validate_override_entry` rejects outright, so following the docs broke the build.
    """
    project, _ = generated_project
    pattern = load_generated_configuration(project).IGNORE_PATTERN
    # Every doc, not just the how-to: the same wrong format was also sitting in the
    # configuration-files reference, where a check scoped to one page could not see it.
    examples = []
    for doc_path in sorted((project / 'docs').rglob('*.md')):
        doc = doc_path.read_text(encoding='utf-8')
        # ```text fences hold override-file content; sample command output lives in
        # ```console fences and is deliberately not a valid entry.
        for block in re.findall(r'^```text\n(.*?)^```', doc, re.MULTILINE | re.DOTALL):
            for line in block.splitlines():
                entry = line.strip()
                # Skip comments and `<PLACEHOLDER>` format specs; the rest must be real.
                if not entry or entry.startswith('#') or '<' in entry:
                    continue
                examples.append((doc_path.relative_to(project), entry))
    # Prose can also spell the format out inline; catch the space-separated shape directly.
    for doc_path in sorted((project / 'docs').rglob('*.md')):
        doc = doc_path.read_text(encoding='utf-8')
        bad = re.search(r'`<[A-Za-z_-]*(VULN|vuln)[A-Za-z_-]*>\s+<YYYY-MM-DD>', doc)
        assert not bad, f'{doc_path.relative_to(project)} documents a space-separated override format'
    assert examples, 'no override examples found anywhere in the docs'
    for source, example in examples:
        assert pattern.fullmatch(example), f'{source}: documented example {example!r} would be rejected'


def test_suppressions_are_validated_whole_not_scanned(generated_project):
    """Suppression entries are matched with `fullmatch`, never scanned out of a joined string.

    `finditer` over the merged list failed open in the worst direction: a mistyped expiry
    like `CVE-1::2020-1-1` does not match the optional expiry group, so the bare id
    matched and the entry became a *permanent* suppression, with `2020`, `1`, `1` added
    as extra ids.
    """
    project, _ = generated_project
    secure_py = (project / '_CI' / 'tasks' / 'secure.py').read_text(encoding='utf-8')
    audit_source = secure_py.split("@logged('secure.audit')", 1)[1].split('\n@task', 1)[0]
    assert 'IGNORE_PATTERN.finditer' not in audit_source, 'audit still scans for id-shaped substrings'
    assert 'parse_suppressions' in audit_source
    assert 'IGNORE_PATTERN.fullmatch' in secure_py


def suppression_calls(secure_py, function_name='audit'):
    """Return `{source label: {keyword: value}}` for each `parse_suppressions()` call in `audit`.

    Parsed with `ast`, not matched textually. Line-based matching broke the moment a call was
    wrapped across lines, and a regex stops at the wrong parenthesis because one call nests
    `os.environ.get(...)` inside it. The AST is indifferent to both.
    """
    tree = ast.parse(secure_py)
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function_name)
    calls = {}
    for node in ast.walk(func):
        if not (isinstance(node, ast.Call) and getattr(node.func, 'id', '') == 'parse_suppressions'):
            continue
        label = ast.unparse(node.args[1]) if len(node.args) > 1 else ''
        calls[label] = {kw.arg: ast.unparse(kw.value) for kw in node.keywords}
    return calls


def test_untracked_suppression_sources_require_an_expiry(generated_project):
    """`--ignore` and the env var must carry an expiry; `.security-overrides` need not.

    Those two leave no trace in the repo, so a permanent entry there could mute a finding
    with no code change to review.
    """
    project, _ = generated_project
    secure_py = (project / '_CI' / 'tasks' / 'secure.py').read_text(encoding='utf-8')
    calls = suppression_calls(secure_py)
    cli = next(kwargs for label, kwargs in calls.items() if '--ignore' in label)
    env = next(kwargs for label, kwargs in calls.items() if 'SECURITY_OVERRIDE_ENV' in label)
    assert cli.get('require_expiry') == 'True', '--ignore does not require an expiry'
    assert env.get('require_expiry') == 'True', 'the env var does not require an expiry'
    # The file keeps permanent entries: load_overrides_file must not opt in.
    file_loader = secure_py.split('def load_overrides_file', 1)[1].split('\n@task', 1)[0]
    assert 'require_expiry=True' not in file_loader, '.security-overrides should still allow permanent entries'


def test_applied_suppressions_are_logged_with_their_source(generated_project):
    """Whatever is applied is printed with its origin, so an env-only mute leaves a footprint."""
    project, _ = generated_project
    secure_py = (project / '_CI' / 'tasks' / 'secure.py').read_text(encoding='utf-8')
    audit_source = secure_py.split("@logged('secure.audit')", 1)[1].split('\n@task', 1)[0]
    assert 'Applying' in audit_source, 'applied suppressions are not announced'
    assert 'suppression.source' in audit_source, 'the origin of each suppression is not printed'
    assert 'expired on' in audit_source, 'expired suppressions are not reported'


def test_parent_overrides_document_the_expiry_requirement():
    """The parent's `.security-overrides` warns that its entries travel by env and need expiries.

    The matrix runner forwards them through `<PROJECT>_SECURITY_OVERRIDE`, which now rejects
    permanent entries — so an expiry-less entry here would fail every matrix cell.
    """
    header = (REPO_ROOT / '.security-overrides').read_text(encoding='utf-8')
    assert 'expiry' in header.lower()
    entries = [line.strip() for line in header.splitlines() if line.strip() and not line.startswith('#')]
    for entry in entries:
        assert '::' in entry, f'{entry!r} has no expiry but is forwarded via the environment'


def github_workflows(project):
    """Yield (name, parsed) for every shipped GitHub workflow."""
    directory = project / '.github' / 'workflows'
    for path in sorted(directory.iterdir()):
        yield path.name, yaml.safe_load(path.read_text(encoding='utf-8'))


def test_no_workflow_writes_the_token_into_a_git_remote(generated_project):
    """No workflow embeds the token in a remote URL.

    `origin` carrying `x-access-token:<token>` is what leaked a credential into the
    published SBOM; checkout now authenticates with a non-persisted header instead.
    """
    project, cell = generated_project
    if cell['git_hosting_service'] != 'github':
        pytest.skip('GitHub-only workflows')
    for name, _ in github_workflows(project):
        raw = (project / '.github' / 'workflows' / name).read_text(encoding='utf-8')
        code = '\n'.join(line for line in raw.splitlines() if not line.strip().startswith('#'))
        assert 'x-access-token' not in code, f'{name} still builds a credentialed remote URL'


def test_checkouts_do_not_persist_credentials(generated_project):
    """Every `actions/checkout` that precedes an SBOM-capable task refuses to persist auth.

    The Pages *deploy job* is the deliberate exception: `properdocs gh-deploy` pushes to the
    `gh-pages` branch and needs the credential to survive the checkout. Only that job — the
    exemption used to be written per file, which silently covered every other job in
    `pages.yaml` too, including ones added later.
    """
    project, cell = generated_project
    if cell['git_hosting_service'] != 'github':
        pytest.skip('GitHub-only workflows')
    exempt = ('pages.yaml', 'deploy')
    for name, config in github_workflows(project):
        for job_name, job in config['jobs'].items():
            for step in job.get('steps') or []:
                if not str(step.get('uses', '')).startswith('actions/checkout@'):
                    continue
                persists = (step.get('with') or {}).get('persist-credentials')
                if (name, job_name) == exempt:
                    assert persists is True, f'{name}:{job_name} cannot push gh-pages without the credential'
                    continue
                assert persists is False, f'{name}:{job_name} checkout persists credentials'


def test_every_github_job_declares_least_privilege_permissions(generated_project):
    """No job silently inherits the repository's default token scopes."""
    project, cell = generated_project
    if cell['git_hosting_service'] != 'github':
        pytest.skip('GitHub-only workflows')
    for name, config in github_workflows(project):
        for job_name, job in config['jobs'].items():
            declared = job.get('permissions') or config.get('permissions')
            assert declared, f'{name}:{job_name} inherits default token permissions'
            # Only the image build (pushes to ghcr) and the docs deploy (pushes gh-pages)
            # may mutate anything. Two write scopes are exempt everywhere because neither
            # grants access to repository contents: `id-token` mints an OIDC token for PyPI
            # Trusted Publishing, and `attestations` records a signed build-provenance
            # statement. Both produce a signature; neither can change what is in the repo.
            signing_scopes = ('id-token', 'attestations')
            if job_name not in ('build-deps-image', 'deploy'):
                writes = [
                    scope for scope, level in declared.items() if level == 'write' and scope not in signing_scopes
                ]
                assert not writes, f'{name}:{job_name} asks for write scopes {writes}'


def publish_steps(project):
    """Return the `publish` job's steps from the generated publish workflow."""
    config = yaml.safe_load((project / '.github' / 'workflows' / 'publish.yaml').read_text(encoding='utf-8'))
    return config['jobs']['publish']['steps']


def step_index(steps, needle):
    """Return the index of the first step whose `run` or `uses` contains `needle`."""
    for index, step in enumerate(steps):
        if needle in (step.get('run') or '') or needle in (step.get('uses') or ''):
            return index
    return -1


def test_publish_attests_the_artifacts_it_uploads(generated_project):
    """Provenance is taken between building and uploading, over the files actually published.

    The ordering is the whole guarantee. Attesting one build and uploading a different one
    yields an attestation that fails verification, which reads to a consumer as tampering —
    strictly worse than shipping no attestation at all. So this pins both the order and the
    `--prebuilt` flag that stops the publish step rebuilding.
    """
    project, cell = generated_project
    if cell['git_hosting_service'] != 'github':
        pytest.skip('GitHub-only workflow')
    steps = publish_steps(project)
    built = step_index(steps, 'release.dist')
    attested = step_index(steps, 'attest-build-provenance')
    published = step_index(steps, 'release.publish')
    assert built >= 0, 'nothing builds the distribution before publishing'
    assert attested >= 0, 'no build-provenance attestation step'
    assert built < attested < published, f'wrong order: build={built}, attest={attested}, publish={published}'
    assert '--prebuilt' in steps[published]['run'], 'the publish step rebuilds, orphaning the attestation'


def test_attestation_action_is_pinned_by_sha(generated_project):
    """The attestation action is SHA-pinned like every other action in the generated workflows."""
    project, cell = generated_project
    if cell['git_hosting_service'] != 'github':
        pytest.skip('GitHub-only workflow')
    uses = next(s['uses'] for s in publish_steps(project) if 'attest-build-provenance' in (s.get('uses') or ''))
    ref = uses.split('@', 1)[1]
    assert re.fullmatch(r'[0-9a-f]{40}', ref), f'attestation action is pinned to {ref!r}, not a commit SHA'


TEMPLATE_WORKFLOWS = REPO_ROOT / 'template' / "{% if git_hosting_service == 'github' %}.github{% endif %}" / 'workflows'
# `uses: owner/repo@ref  # vX.Y.Z`. Local refs (`uses: ./.github/...`) carry no `@` and are
# skipped by the pattern, which is correct: they are versioned by the commit being built.
ACTION_USE = re.compile(r'^\s*-?\s*uses:\s*(?P<action>[^@\s]+)@(?P<ref>\S+)(?:\s+#\s*(?P<comment>.+?))?\s*$')


def action_pins(directory):
    """Return {action: {ref: [where, ...]}} for every third-party `uses:` under `directory`."""
    pins = {}
    for path in sorted(directory.glob('*')):
        if not path.is_file():
            continue
        for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
            match = ACTION_USE.match(line)
            if match:
                where = f'{path.name}:{lineno}'
                pins.setdefault(match.group('action'), {}).setdefault(match.group('ref'), []).append(where)
    return pins


def test_generated_actions_are_pinned_to_a_sha_with_a_version_comment(generated_project):
    """Every third-party action is pinned to a full commit SHA, annotated with its tag.

    A tag is a moving target: `@v6` silently becomes whatever the owner pushes next, inside a
    job holding the publish credentials. The trailing `# vX.Y.Z` is what makes a 40-character
    hex string reviewable, so it is required too.
    """
    project, cell = generated_project
    if cell['git_hosting_service'] != 'github':
        pytest.skip('GitHub-only workflows')
    for action, refs in action_pins(project / '.github' / 'workflows').items():
        for ref, places in refs.items():
            assert re.fullmatch(r'[0-9a-f]{40}', ref), f'{action} pinned to {ref!r} at {places[0]}, not a SHA'
    for path in sorted((project / '.github' / 'workflows').glob('*')):
        for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
            match = ACTION_USE.match(line)
            if match:
                assert match.group('comment'), f'{path.name}:{lineno} pins {match.group("action")} with no # vX.Y.Z'


def test_action_pins_never_drift_apart():
    """One action, one SHA — across this repository and the template it ships.

    `actions/checkout` alone appears fourteen times. Bumping the copies you happen to grep for
    and missing the rest is the failure this catches: the result still runs, so nothing else
    reports it, and the workflows quietly disagree about which version they trust. It also
    catches the parent moving ahead of the template, which would leave generated projects on
    an older action indefinitely.
    """
    combined = {}
    for directory in (REPO_ROOT / '.github' / 'workflows', TEMPLATE_WORKFLOWS):
        for action, refs in action_pins(directory).items():
            for ref, places in refs.items():
                combined.setdefault(action, {}).setdefault(ref, []).extend(places)
    assert combined, 'no pinned actions found; the workflow paths are wrong'
    for action, refs in combined.items():
        assert len(refs) == 1, f'{action} is pinned to {len(refs)} different SHAs: ' + '; '.join(
            f'{ref} at {", ".join(places)}' for ref, places in sorted(refs.items())
        )


def test_publish_job_may_write_attestations(generated_project):
    """Without `attestations: write` the attest step 403s at the end of a release."""
    project, cell = generated_project
    if cell['git_hosting_service'] != 'github':
        pytest.skip('GitHub-only workflow')
    config = yaml.safe_load((project / '.github' / 'workflows' / 'publish.yaml').read_text(encoding='utf-8'))
    permissions = config['jobs']['publish']['permissions']
    assert permissions.get('attestations') == 'write', 'publish job cannot record an attestation'
    assert permissions.get('id-token') == 'write', 'attestation signing also needs the OIDC token'


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


def test_deps_image_runs_as_non_root(generated_project):
    """`Dockerfile.deps` drops root and makes the venv path writable to that user."""
    project, _ = generated_project
    dockerfile = (project / 'Dockerfile.deps').read_text(encoding='utf-8')
    assert 'USER 1001' in dockerfile, 'deps image still runs as root'
    assert 'chown -R 1001:1001 /app' in dockerfile, 'uv run could not write to UV_PROJECT_ENVIRONMENT'
    assert '--create-home' in dockerfile, 'uv needs a writable HOME for its cache'
    # The uid is part of the tag inputs, so changing it cannot serve a stale image.
    container_py = (project / '_CI' / 'tasks' / 'container.py').read_text(encoding='utf-8')
    assert 'DOCKERFILE_DEPS' in container_py


def test_gitlab_credentials_are_environment_scoped(generated_project):
    """The GitLab deps job declares an environment so its registry token can be scoped."""
    project, cell = generated_project
    if cell['git_hosting_service'] != 'gitlab':
        pytest.skip('GitLab-only pipeline')
    config = yaml.safe_load((project / '.gitlab-ci.yml').read_text(encoding='utf-8'))
    assert config['build-deps-image'].get('environment'), 'deps job has no environment to scope variables to'
    assert config['publish'].get('environment') == 'pypi'


class RecordingContext:
    """Minimal stand-in for an Invoke context that records commands instead of running them."""

    def __init__(self, stdout_for=None) -> None:
        """Optionally map command prefixes to the stdout each should return."""
        self.commands = []
        self.stdout_for = stdout_for or {}

    def run(self, cmd, **_kwargs: object):
        """Record `cmd` and return canned stdout when a prefix matches."""
        self.commands.append(cmd)
        for prefix, stdout in self.stdout_for.items():
            if cmd.startswith(prefix):
                return SimpleNamespace(stdout=stdout, failed=False)
        return SimpleNamespace(stdout='', failed=False)


def opener(project, system, *, has_wslview=False, interop=False):
    """Load the generated `shared.py` and drive `open_target` for one platform.

    Returns (commands issued via context.run, commands routed through `execute`). The
    split matters: `execute` fails the task on a non-zero exit, so which list a command
    lands in *is* the failure-semantics contract.
    """
    shared = load_generated_shared(project)
    executed = []
    shared.get_operating_system = lambda: system
    shared.shutil = SimpleNamespace(which=lambda n: '/wslview' if (n == 'wslview' and has_wslview) else None)
    shared.wsl_interop_available = lambda: interop
    shared.execute = lambda _ctx, cmd: executed.append(cmd)
    context = RecordingContext({'wslpath': r'\\wsl.localhost\Ubuntu\home\me\site\index.html'})
    shared.open_target(context, 'site/index.html')
    return context.commands, executed


@pytest.mark.parametrize(
    ('system', 'expected'),
    [('macos', 'open site/index.html'), ('linux', 'xdg-open site/index.html'), ('windows', 'start site/index.html')],
)
def test_open_target_keeps_strict_failure_off_wsl(generated_project, system, expected):
    """macOS, Linux and Windows keep the pre-existing command and keep failing loudly."""
    project, _ = generated_project
    ran, executed = opener(project, system)
    assert executed == [expected], f'{system} should go through execute() so a failure fails the task'
    assert ran == []


def test_open_target_uses_wslview_when_still_installed(generated_project):
    """An existing `wslu` install keeps working, rather than being bypassed."""
    project, _ = generated_project
    ran, executed = opener(project, 'wsl', has_wslview=True, interop=True)
    assert ran == ['wslview "site/index.html"']
    assert executed == [], 'WSL must not use execute(): the Windows helpers exit non-zero on success'


def test_open_target_hands_a_translated_path_to_windows(generated_project):
    """Without `wslview`, the path is translated with `wslpath -w` and opened via cmd.exe.

    Both details are load-bearing: Windows cannot resolve a Linux path, and `start`
    needs its empty window-title argument or it treats the quoted path as a title and
    opens nothing.
    """
    project, _ = generated_project
    ran, executed = opener(project, 'wsl', interop=True)
    assert ran[0] == 'wslpath -w "site/index.html"'
    assert ran[1] == "cmd.exe /c start '' '\\\\wsl.localhost\\Ubuntu\\home\\me\\site\\index.html'"
    assert executed == []


def test_open_target_degrades_when_wsl_interop_is_disabled(generated_project):
    """A distro with interop off gets a message, not a traceback or a failed task."""
    project, _ = generated_project
    ran, executed = opener(project, 'wsl', interop=False)
    assert ran == [], f'unexpected run() calls: {ran}'
    assert executed == [], f'unexpected execute() calls: {executed}'


def test_no_task_still_depends_on_wslu(generated_project):
    """Nothing tells the user to install the deprecated `wslu` package, or shells out to it blindly."""
    project, _ = generated_project
    for name in ('shared.py', 'document.py', 'test.py', 'quality.py'):
        source = (project / '_CI' / 'tasks' / name).read_text(encoding='utf-8')
        assert 'install the wslu' not in source, f'{name} still recommends the deprecated wslu package'
        assert 'open_command' not in source, f'{name} still uses the removed open_command()'


def test_exclude_newer_is_a_fixed_date(generated_project):
    """`exclude-newer` is an absolute date, not a rolling window.

    A relative `"1 week"` moved forward daily, so a resolution — and a green gate — could
    change with no commit behind it. That is how the toolchain drifted into a red lint run
    with no code change.
    """
    project, _ = generated_project
    for pyproject in (project / 'pyproject.toml', REPO_ROOT / 'pyproject.toml'):
        value = tomllib.loads(pyproject.read_text(encoding='utf-8'))['tool']['uv']['exclude-newer']
        assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', value), f'{pyproject} has a relative window: {value!r}'


def test_generated_quarantine_date_is_stamped_not_inherited(generated_project):
    """A new project's `exclude-newer` is its generation date, not a literal from the template.

    The template's own value recedes into the past between bumps; inheriting it would hand a
    project created a year later a boundary pinned to year-old packages. `tasks_render.py`
    overwrites it at generation, and this catches the stamp silently not running — in which
    case the fallback literal shows through and is already days stale.
    """
    project, _ = generated_project
    stamped = date.fromisoformat(
        tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))['tool']['uv']['exclude-newer']
    )
    # A day of slack absorbs a suite running across midnight; a missed stamp is far staler.
    today = date.today()  # noqa: DTZ011 - compared against a stamped calendar date
    assert abs((today - stamped).days) <= 1, f'quarantine date {stamped} was not stamped at generation'


def test_base_image_is_pinned_by_digest(generated_project):
    """The base image carries a digest and its tag matches the project's minimum Python.

    `[tool.docker-versions]` holds exactly one image. It used to also carry an `alpine-image`
    that nothing read — dead since the copier migration — which still had to be kept
    version-consistent with uv on every bump.
    """
    project, _ = generated_project
    data = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    images = data['tool']['docker-versions']
    minimum = data['project']['requires-python'].removeprefix('>=')
    base = images['base-image']
    assert '@sha256:' in base, f'base image not pinned by digest: {base}'
    assert f'python{minimum}-trixie-slim@' in base, f'tag does not match requires-python {minimum}: {base}'
    extra = sorted(set(images) - {'base-image'})
    assert set(images) == {'base-image'}, f'unused image references reintroduced: {extra}'


def test_generated_project_ships_a_lockfile(generated_project):
    """A resolved `uv.lock` ships, and it is not ignored.

    `Dockerfile.deps` runs `uv sync --frozen` and the deps-image tag hashes the lockfile;
    both previously relied on a lock created as a side effect of the first `uv run`.
    """
    project, _ = generated_project
    lock = project / 'uv.lock'
    assert lock.is_file(), 'no uv.lock was resolved at generation time'
    data = tomllib.loads(lock.read_text(encoding='utf-8'))
    assert data['package'], 'lockfile resolved no packages'
    ignore = (project / '.gitignore').read_text(encoding='utf-8')
    assert not re.search(r'^\s*/?uv\.lock\s*$', ignore, re.MULTILINE), 'uv.lock is gitignored'


def uv_pins(project):
    """Return every uv version a generated project pins, keyed by where it came from.

    Five places have to agree. They are collected together because the failure that matters is
    *disagreement* — most of all a base-image tag that has moved while its digest has not,
    since a reference carrying both resolves to the digest and silently keeps the old image.
    """
    data = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    base = data['tool']['docker-versions']['base-image']
    lock_data = tomllib.loads((project / 'uv.lock').read_text(encoding='utf-8'))
    locked = {p['name']: p['version'] for p in lock_data['package']}
    return {
        'required-version': data['tool']['uv']['required-version'].removeprefix('=='),
        'test group': next(d for d in data['dependency-groups']['test'] if d.startswith('uv==')).removeprefix('uv=='),
        'uv_build bound': data['build-system']['requires'][0].split('<=')[1],
        'base-image tag': base.split('@')[0].split(':')[-1].split('-python')[0],
        'uv.lock': locked['uv'],
    }


def test_every_uv_pin_agrees(generated_project):
    """All five uv pins in a generated project carry the same version."""
    project, _ = generated_project
    pins = uv_pins(project)
    assert len(set(pins.values())) == 1, f'uv pins disagree: {pins}'


def test_generation_honours_the_uv_version_override(generated_project):
    """Generation stamps exactly the version `TEMPLATE_UV_VERSION` asks for.

    The template's own CI depends on this: it installs the uv the template pins, then generates
    projects and runs `uv sync` with it. A freshly resolved `required-version` the ambient uv
    cannot satisfy would fail every matrix cell, so the fixture pins generation via this
    variable — and this asserts the pin actually took effect.
    """
    project, _ = generated_project
    assert set(uv_pins(project).values()) == {template_uv_version()}


def test_base_image_tag_matches_the_pinned_version(generated_project):
    """The base image's tag names the same uv version and Python as the project pins.

    Network-free on purpose: this is the drift a hand-edit causes, and it should be caught
    whether or not a registry is reachable.
    """
    project, _ = generated_project
    data = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    base = data['tool']['docker-versions']['base-image']
    version = data['tool']['uv']['required-version'].removeprefix('==')
    python_version = data['project']['requires-python'].removeprefix('>=')
    tag_reference, _, digest = base.partition('@')
    assert f'{version}-python{python_version}-trixie-slim' in tag_reference, f'tag disagrees with the pin: {base}'
    assert digest.startswith('sha256:'), f'no digest pinned: {base}'


def test_committed_digests_resolve_to_their_tags():
    """Every digest in the template is the one its tag actually resolves to.

    The failure `maintain.bump-uv` exists to prevent: move the tag, leave a digest behind, and
    the reference still resolves to the *digest* — so projects keep building the old image while
    the file claims otherwise. Checks all five Pythons at once rather than once per matrix cell.

    Skipped when the registry cannot be reached: an unreachable ghcr is not a defect in this
    repository, and failing here would make the suite depend on network weather.
    """
    uv_release = load_uv_release_module()
    template = (REPO_ROOT / 'template' / 'pyproject.toml.jinja').read_text(encoding='utf-8')
    version = uv_release.current_pin(template)
    committed = dict(re.findall(r"^\s*'(\d+\.\d+)': '(sha256:[0-9a-f]+)',$", template, re.MULTILINE))
    assert committed, 'no per-Python digests found in the template'
    for python_version, digest in sorted(committed.items()):
        try:
            live = uv_release.image_digest(version, python_version)
        except uv_release.UvReleaseError as exc:
            pytest.skip(f'registry unreachable: {exc}')
        assert live == digest, f'uv {version} python{python_version}: committed {digest}, registry has {live}'


def test_every_uv_site_points_at_the_bump_command(generated_project):
    """Each uv pin carries a comment naming the command that moves them all.

    Five places hold the same version; editing one by hand is how they drift apart.
    """
    project, _ = generated_project
    content = (project / 'pyproject.toml').read_text(encoding='utf-8')
    for anchor in ('"uv==', 'requires = ["uv_build', 'required-version = "==', 'base-image = "'):
        index = content.index(anchor)
        # The pointer should be in the comment block immediately above the pin.
        preceding = content[:index].rsplit('\n\n', 1)[-1]
        assert 'develop.bump-uv' in preceding, f'no bump-uv pointer above {anchor!r}'


def test_override_variable_name_matches_the_generation_hook():
    """The harness and `tasks_render.py` agree on the override variable's name.

    They are two separate constants. If they drift the override silently stops working: every
    generated project resolves a fresh uv, the ambient uv no longer satisfies it, and all eight
    matrix cells fail on a version mismatch — a long way from the renamed string.
    """
    render = (REPO_ROOT / 'tasks_render.py').read_text(encoding='utf-8')
    assert f"UV_VERSION_ENV = '{UV_VERSION_ENV}'" in render, (
        f'tasks_render.py does not read {UV_VERSION_ENV}; the harness override would be ignored'
    )


def test_repo_uv_pin_points_at_its_own_command():
    """This repo's pin names `maintain.bump-uv`, which also refreshes the template's digests."""
    content = (REPO_ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    index = content.index('required-version = "==')
    assert 'maintain.bump-uv' in content[:index].rsplit('\n\n', 1)[-1]


def test_lockfile_agrees_with_the_pinned_uv(generated_project):
    """The locked uv matches `[tool.uv] required-version`.

    They are resolved from the same pyproject, so a mismatch would mean the lockfile was
    generated against different pins than the ones that shipped.
    """
    project, _ = generated_project
    data = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    required = data['tool']['uv']['required-version'].removeprefix('==')
    lock_data = tomllib.loads((project / 'uv.lock').read_text(encoding='utf-8'))
    locked = {p['name']: p['version'] for p in lock_data['package']}
    assert locked.get('uv') == required, f'lock pins uv {locked.get("uv")}, pyproject requires {required}'


def test_lock_task_derives_the_uv_version_from_the_project():
    """The copier lock task reads the uv version out of the rendered pyproject.

    Hardcoding it in copier.yml would silently drift from `[tool.uv] required-version`, and
    the generated project pins uv exactly — so a stale value there fails generation outright.
    """
    # Parsed, not grepped: the surrounding comments also mention `uvx uv@`.
    tasks = yaml.safe_load((REPO_ROOT / 'copier.yml').read_text(encoding='utf-8'))['_tasks']
    commands = [task['command'] if isinstance(task, dict) else task for task in tasks]
    lock_task = next(command for command in commands if 'uvx uv@' in command)
    assert 'required-version' in lock_task, 'lock task hardcodes a uv version instead of deriving it'
    assert 'pyproject.toml' in lock_task, 'lock task does not read the version from the rendered project'


def pre_commit_hooks(project):
    """Yield every hook defined in the generated `.pre-commit-config.yaml`."""
    config = yaml.safe_load((project / '.pre-commit-config.yaml').read_text(encoding='utf-8'))
    for repo in config['repos']:
        yield from repo['hooks']


def hook_stages(hook):
    """Return a hook's stages, defaulting to pre-commit as pre-commit itself does."""
    return hook.get('stages') or ['pre-commit']


def invoked_task(hook):
    """Return the workflow task a hook runs, seeing through any `sh -c …` wrapper."""
    match = re.search(r'\./workflow\.cmd\s+([\w.-]+)', hook['entry'])
    return match.group(1) if match else ''


def registry_steps(project):
    """Return ``{step name: scope}`` parsed out of the generated `_CI/tasks/preflight.py`.

    Read as source rather than imported: importing it would pull in invoke and every task
    module behind it, which this suite has no reason to install just to read a declaration.
    """
    source = (project / '_CI' / 'tasks' / 'preflight.py').read_text(encoding='utf-8')
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Assign):
            continue
        if not any(getattr(target, 'id', None) == 'STEPS' for target in node.targets):
            continue
        # Keywords as well as positions, and a failed read fails the assertion rather than
        # raising out of the helper: `Step('ty', scope=WHOLE_PROGRAM)` is the same declaration.
        steps = {}
        for call in node.value.elts:
            supplied = dict(zip(('name', 'scope'), call.args, strict=False))
            supplied.update({word.arg: word.value for word in call.keywords})
            name, scope = supplied.get('name'), supplied.get('scope')
            assert isinstance(name, ast.Constant), f'a step in STEPS declares no literal name: {ast.dump(call)}'
            assert isinstance(scope, ast.Name), f'step {name.value!r} declares no plain scope name'
            steps[name.value] = scope.id
        return steps
    pytest.fail('preflight.py declares no STEPS registry')


def test_no_commit_stage_hook_rewrites_unstaged_tracked_files(generated_project):
    """No `pre-commit`-stage hook runs a task that writes README.md or pyproject.toml.

    `preflight` updates the README badges and ratchets `fail_under`; the `test` aggregator used
    to do the coverage half of that. Run from a commit hook, either one aborted the commit with
    "files were modified by this hook" — after the message was written, for files the author
    never staged. That is what teaches people `--no-verify`, which then disables every hook
    here at once. The bare `preflight` on pre-push is the shape that gets the guarantee without
    the writes, and `preflight.staged` is absent from this set because it writes nothing at
    all: it reports on the files the author staged and names the command that fixes them.
    """
    project, _ = generated_project
    # `build` is deliberately absent: it stopped writing the README when the CI badge moved to
    # the host's own status endpoint, and the SBOM and wheel it does write are gitignored.
    mutating = {'preflight', 'test', 'document', 'quality.pyscn-analyze', 'test.coverage'}
    for hook in pre_commit_hooks(project):
        if 'pre-commit' not in hook_stages(hook):
            continue
        invoked = invoked_task(hook)
        hook_id = hook['id']
        assert invoked not in mutating, f'commit-stage hook {hook_id!r} runs {invoked!r}, which rewrites files'


def test_commit_stage_is_one_invocation_of_the_per_file_steps(generated_project):
    """The commit stage runs the staged bundle in a single `./workflow.cmd` invocation.

    Each invocation costs ~1.3s of interpreter and import startup before a tool runs, so the
    six hooks this replaced spent most of a commit's budget starting up: ~8s of startup to do
    ~2s of checking. One hook pays it once, which is what keeps the stage worth leaving on.
    """
    project, _ = generated_project
    code_hooks = [
        hook for hook in pre_commit_hooks(project) if 'pre-commit' in hook_stages(hook) and invoked_task(hook)
    ]
    invoked = sorted(invoked_task(hook) for hook in code_hooks)
    assert invoked == ['preflight.staged', 'secure.validate-overrides'], (
        f'the commit stage runs {invoked}, so it no longer pays startup exactly once for the code checks'
    )
    staged = next(hook for hook in code_hooks if invoked_task(hook) == 'preflight.staged')
    # No filenames and no wrapper: the task reads the index itself, so this entry is the same
    # command a person would type. Handing over the list needed `sh -c … --paths="$*"`, since
    # Invoke reads a bare second filename as another task name.
    assert staged.get('pass_filenames') is False, 'the hook hands over a file list again'
    assert staged['entry'] == './workflow.cmd preflight.staged', (
        f'the entry is not the bare command: {staged["entry"]!r}'
    )


def test_commit_stage_filter_is_not_narrower_than_the_steps_it_runs(generated_project):
    """The one remaining `files:` filter is the union of the per-file steps' own filters.

    Collapsing six hooks into one left a single `files:` key in front of four tools that do not
    agree on what they check — complexipy is `src/` only, the rest also cover `_CI/tasks/` and
    `tests/`. The per-tool filters therefore live in the registry, and this pattern decides
    only whether the hook *wakes*: narrower than the widest step, and staging a file that step
    cares about would leave the hook skipped and the file unchecked.
    """
    project, _ = generated_project
    source = (project / '_CI' / 'tasks' / 'configuration.py').read_text(encoding='utf-8')
    widest = re.search(r"CODE_FILES = re\.compile\(r'([^']+)'\)", source)
    assert widest, 'configuration.py no longer declares CODE_FILES'
    staged = next(hook for hook in pre_commit_hooks(project) if invoked_task(hook) == 'preflight.staged')
    assert staged['files'] == widest.group(1), (
        f"hook filter {staged['files']!r} does not match the registry's widest per-file filter {widest.group(1)!r}"
    )


def test_whole_program_steps_are_never_scoped_to_a_diff(generated_project):
    """ty, pyscn and pytest are declared whole-program, and so never run at commit stage.

    ty: a changed signature fails in the *callers*, which a narrowed run never looks at.
    pyscn: dead code and duplicate blocks are relationships between files.
    tox: a passing changed test says nothing about the ones it broke, on any interpreter.
    build: a wheel is built from the whole tree or not at all.

    Their cost also scales with the size of the project rather than of the change, which is
    what would have made commits slower and slower as the project grew.
    """
    project, _ = generated_project
    steps = registry_steps(project)
    for name in ('ty', 'commitizen', 'pyscn', 'tox', 'build', 'artifacts'):
        assert steps.get(name) == 'WHOLE_PROGRAM', f'{name} is declared {steps.get(name)!r}, not whole-program'
    commit_stage = {invoked_task(hook) for hook in pre_commit_hooks(project) if 'pre-commit' in hook_stages(hook)}
    assert 'preflight' not in commit_stage, 'the whole-program bundle runs on every commit'


def test_path_taking_tasks_accept_a_paths_argument(generated_project):
    """The tasks the hooks scope actually take `--paths`, and fall back to the project paths."""
    project, _ = generated_project
    lint_py = (project / '_CI' / 'tasks' / 'lint.py').read_text(encoding='utf-8')
    format_py = (project / '_CI' / 'tasks' / 'format_.py').read_text(encoding='utf-8')
    for name, source in (('lint.py', lint_py), ('format_.py', format_py)):
        # A hardcoded `@run(f'… {PATHS}')` cannot be narrowed: it is baked at import time.
        assert '@run(' not in source, f'{name} still builds its command at import time'
    for signature in ('def ruff_lint(context: Context, paths: str', 'def pylint(context: Context, paths: str'):
        assert signature in lint_py, f'missing {signature!r}'
    assert 'def format_(context: Context, paths: str' in format_py, 'the format aggregator cannot forward paths'
    assert 'paths or PATHS' in lint_py, 'lint tasks do not fall back to the project-wide paths'


def test_whole_program_gate_runs_on_pre_push_without_writing(generated_project):
    """The whole-program bundle gates pushes, not commits, and writes nothing tracked.

    It needs no flag to be safe: `preflight` verifies by default and `--write` is opt-in, which
    is the point of that inversion — the hook, the pipeline, and the command you type to
    reproduce a failure are all the same string.
    """
    project, _ = generated_project
    hooks = {hook['id']: hook for hook in pre_commit_hooks(project)}
    gate = hooks['preflight']
    assert gate['stages'] == ['pre-push'], f'preflight hook stages are {gate["stages"]}'
    assert invoked_task(gate) == 'preflight', f'preflight hook runs {gate["entry"]!r}'
    assert '--write' not in gate['entry'], f'the pre-push hook would rewrite tracked files: {gate["entry"]!r}'
    # No `files:` either. `preflight` verifies README.md and pyproject.toml, so a filter over
    # source paths would skip the gate on a push carrying only those — which is exactly what
    # the recovery loop produces: `--write`, then commit the badges. CI would still run it.
    assert 'files' not in gate, f'the pre-push gate is narrowed and can be skipped: {gate.get("files")!r}'
    assert gate.get('pass_filenames') is False, 'the whole-program gate was narrowed to the pushed files'
    installed = yaml.safe_load((project / '.pre-commit-config.yaml').read_text(encoding='utf-8'))
    assert 'pre-push' in installed['default_install_hook_types'], 'pre-push hooks would never be installed'


def test_the_coverage_floor_is_enforced_where_it_was_measured(generated_project):
    """`fail_under` is enforced once, over the combined data, and nowhere else.

    The ratchet sets the floor from coverage combined across the matrix, and no single env can
    reach a union figure — a `sys.version_info` branch has one arm unreachable per interpreter
    by construction. pytest-cov enforcing the same floor per env therefore deadlocks a project:
    the ratchet bumps to the union, every env then fails below it, and the ratchet only moves
    up. Reproduced end to end before this: 100% combined, 84.62% per env, no way out but
    editing `fail_under` by hand.

    So every per-interpreter reporter passes `--fail-under=0`, and `combine_coverage`'s
    `coverage json` over the combined data is the single enforcement point.
    """
    project, _ = generated_project
    data = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    addopts = data['tool']['pytest']['ini_options']['addopts']
    assert '--cov' in addopts
    assert '--cov-fail-under=0' in addopts, 'pytest-cov enforces a union floor per interpreter'
    assert 'fail_under' in data['tool']['coverage']['report']

    test_py = (project / '_CI' / 'tasks' / 'test.py').read_text(encoding='utf-8')
    reporters = test_py.split("@logged('test.coverage')", 1)[1].split('\n@', 1)[0]
    for command in ('coverage report', 'coverage json', 'coverage html'):
        line = next(line for line in reporters.splitlines() if command in line)
        assert '--fail-under=0' in line, f'{command} in test.coverage gates on a union floor'

    combine = test_py.split('def combine_coverage', 1)[1].split('\n@', 1)[0]
    enforcing = next(line for line in combine.splitlines() if 'coverage json' in line)
    assert '--fail-under' not in enforcing, 'the one enforcement point stopped enforcing'
    test_py = (project / '_CI' / 'tasks' / 'test.py').read_text(encoding='utf-8')
    aggregator = test_py.split("@logged('test')", 1)[1]
    assert 'run_steps(pytest)' in aggregator, 'the aggregator no longer delegates to the same pytest task'
    preflight_py = (project / '_CI' / 'tasks' / 'preflight.py').read_text(encoding='utf-8')
    assert 'tox' in registry_steps(project), 'the registry no longer runs the matrix'
    imported_from_test = preflight_py.split('from .test import', 1)[1].split('\n', 1)[0]
    assert 'tox' in imported_from_test, (
        'the registry no longer runs the shared tox task, so the floor it enforces can drift'
    )


def test_the_gate_offers_no_way_to_run_less_than_ci(generated_project):
    """`preflight` takes no flag that trims what it runs, because CI runs this same command.

    A `--quick` that dropped the matrix would be a documented way to make local and CI
    disagree, and the obvious thing to reach for in a hurry. The knob that shortens the matrix
    is `env_list`, which shortens it for CI too and so cannot open a gap. The two flags it does
    take add rather than remove: `--write` updates the derived files, and `--audit-dependencies`
    runs a step no gate runs anywhere.
    """
    project, _ = generated_project
    preflight_py = (project / '_CI' / 'tasks' / 'preflight.py').read_text(encoding='utf-8')
    signature = preflight_py.split('def preflight(', 1)[1].split(')', 1)[0]
    parameters = {part.split(':')[0].strip() for part in signature.split(',')}
    assert parameters == {'context', 'write', 'audit_dependencies'}, (
        f'preflight grew a parameter that can change what it runs: {parameters}'
    )


def test_no_ci_job_reruns_what_the_gate_already_covers(generated_project):
    """CI has one job for the checks, and it is the gate.

    Separate lint, test and build jobs re-ran, in a different shape, work `preflight`
    already covers — which is how a green push comes to meet a red pipeline: two lists of
    checks, one of them out of step. The cost of folding them in is the wall-clock their
    parallelism bought, not diagnosis; `run_steps` still reports every failure in one pass.
    """
    project, cell = generated_project
    duplicated = ('./workflow.cmd lint', './workflow.cmd test', './workflow.cmd build')
    if cell['git_hosting_service'] == 'github':
        pipeline = (project / '.github' / 'workflows' / 'continuous-integration.yaml').read_text(encoding='utf-8')
        jobs = set(yaml.safe_load(pipeline)['jobs'])
        assert jobs == {'build-deps-image', 'preflight'}, f'the pipeline runs {jobs}'
    else:
        pipeline = (project / '.gitlab-ci.yml').read_text(encoding='utf-8')
        jobs = {name for name in yaml.safe_load(pipeline) if not name.startswith(('stages', 'variables'))}
        assert jobs == {'build-deps-image', 'preflight', 'secure', 'publish'}, f'the pipeline runs {jobs}'
    # The task name, not the whole line: `startswith` also forbade a future
    # `test.list-combos`, exact-match let `./workflow.cmd test --args=…` through, and
    # `lstrip('- ')` strips any run of those two characters rather than one list marker.
    forbidden = {command.split()[-1] for command in duplicated}
    for line in pipeline.splitlines():
        if './workflow.cmd' not in line:
            continue
        # After the comment is stripped, a line that only mentioned the launcher in prose has
        # nothing left to check.
        command = re.sub(r'^\s*-\s*', '', line.split('#', 1)[0]).strip()
        if './workflow.cmd' not in command:
            continue
        invoked = command.split('./workflow.cmd', 1)[1].split()
        task = invoked[0] if invoked else ''
        assert task not in forbidden, f'{command!r} re-runs what preflight covers'


def test_ci_runs_the_same_gate_as_the_pre_push_hook(generated_project):
    """CI's preflight job runs the identical command the pre-push hook does.

    This is the property that stops local and remote from disagreeing: a badge that is stale in
    the pipeline would have failed the push, so the pipeline is a backstop rather than the
    place you first hear about it. CI cannot commit a refresh either way — the checkout is
    credential-less and the token is read-only — so failing with the fix command is all it can
    usefully do.
    """
    project, cell = generated_project
    gate = next(hook for hook in pre_commit_hooks(project) if hook['id'] == 'preflight')
    command = gate['entry']
    if cell['git_hosting_service'] == 'github':
        workflow = yaml.safe_load(
            (project / '.github' / 'workflows' / 'continuous-integration.yaml').read_text(encoding='utf-8')
        )
        job = workflow['jobs']['preflight']
        commands = [step.get('run') for step in job['steps']]
        assert job['permissions']['contents'] == 'read', 'the preflight job can write to the repository'
    else:
        pipeline = yaml.safe_load((project / '.gitlab-ci.yml').read_text(encoding='utf-8'))
        commands = pipeline['preflight']['script']
    assert command in commands, f'no CI job runs {command!r}; it runs {commands}'


def test_task_output_stays_in_order_when_redirected(generated_project):
    """The streams are line-buffered, so a log read after the fact attributes output correctly.

    Python block-buffers stdout when it is not a terminal — which is every CI log and every
    `> run.log` — while a subprocess invoke spawns writes to the same descriptor immediately.
    Our own lines therefore arrived in chunks *after* the command they introduce, so the
    echoed command sat below its own output and a task's prints appeared under the previous
    task's command. `Wrote SBOM to …` reading as though `uv run coverage json` had produced it
    is what that looked like, and the SBOM tasks have no command of their own to echo, so
    nothing contradicted the impression.
    """
    project, _ = generated_project
    shared = (project / '_CI' / 'tasks' / 'shared.py').read_text(encoding='utf-8')
    assert 'line_buffering=True' in shared, 'the streams are block-buffered again when redirected'


def test_a_failing_run_writes_no_derived_values(generated_project):
    """Once a check has failed, the steps that write derived files are skipped.

    Every step otherwise runs even after one fails, so a single run reports everything that is
    wrong. That is right for reporting and wrong for writing: a badge computed from a tree
    whose checks just failed is a claim the tree does not support. Before this, `preflight`
    would print "Updated build badge to passing" on a run that went on to fail, and write a
    grade-A pyscn badge over a project whose tests were red — the aggregator it replaced
    short-circuited instead, so this restores a property the template already had.

    Skipped rather than reordered, so a late failure cannot retroactively undo an earlier
    write, and `secure.audit` being last means an advisory does not stop a badge from updating.
    """
    project, _ = generated_project
    source = (project / '_CI' / 'tasks' / 'preflight.py').read_text(encoding='utf-8')
    body = source.split('def run_scope', 1)[1]
    assert 'if failed and derived' in body, 'a failing run can still write derived values'
    assert 'derived = step.write is not None' in source, 'the plan no longer marks which steps produce derived files'
    # The writers have to be last for the skip to cover them; `artifacts` is the final
    # non-network step, and `build`'s badge precedes it.
    steps = list(registry_steps(project))
    assert steps[-1] == 'audit', f'audit is no longer last, so its failure would skip the writers: {steps}'
    assert steps[-2] == 'artifacts', f'artifacts is not the last checked step: {steps}'


def test_no_automated_run_edits_source(generated_project):
    """Nothing in the registry can write source — there is no step that could.

    The commit hook used to apply formatting. That made the automated entry points behave
    differently from the command a person types, and it rewrote the *worktree* while git was
    mid-commit, which suits a partially staged file badly: the formatter rewrites the whole
    file, hunks deliberately left out of the index included. Reporting and naming
    `./workflow.cmd format` costs one command and owns neither problem.

    So the property is now absolute rather than conditional, and this asserts the absence of
    the machinery rather than its correct use: no step declares a source-writing variant, and
    the concept of "fixing" is gone from the module.
    """
    project, _ = generated_project
    source = (project / '_CI' / 'tasks' / 'preflight.py').read_text(encoding='utf-8')
    assert 'fixes_source' not in source, 'a step can write source again'
    assert 'ruff_format' not in source, 'the registry reaches the formatter again'

    # Every write variant in the registry produces a derived file, which is what `--write` is
    # for; `plan_scope` marks exactly those so a failing run can skip them.
    assert 'derived = step.write is not None' in source, 'the plan no longer marks which steps produce derived files'

    # And the hook asks for no fixing, because there is nothing to ask for.
    hook = next(h for h in pre_commit_hooks(project) if invoked_task(h) == 'preflight.staged')
    assert '--fix' not in hook['entry'], f'the commit hook rewrites files again: {hook["entry"]!r}'


def test_running_the_hooks_by_hand_matches_what_git_will_do(generated_project):
    """`develop.pre-commit` runs the hooks exactly as git will, with nothing to widen.

    It passed `--all-files` unconditionally, so the command behaved differently from the hook it
    is named after. The flag then survived as an option, which was worse: the staged bundle
    passes no filenames and reads the index instead, so `pre-commit run --all-files` printed
    "Nothing staged" and exited 0 — a whole-tree check that checked nothing. `preflight` is the
    command that covers every file.
    """
    project, _ = generated_project
    develop = (project / '_CI' / 'tasks' / 'develop.py').read_text(encoding='utf-8')
    body = develop.split("@logged('develop.pre-commit')", 1)[1].split('@task', 1)[0]
    assert "'uv run pre-commit run'" in body, 'the default no longer runs the hooks on staged files'
    # Past the docstring, which explains the flag's absence.
    code = body.split('"""', 2)[2]
    assert '--all-files' not in code, 'a widening flag is back, and it still cannot widen'


def test_the_staged_bundle_defaults_to_what_is_staged(generated_project):
    """`preflight.staged` with no paths checks the index, not the whole project.

    It used to fall back to every project path, so typing the command by hand swept everything
    — the opposite of what its name promises. The hook passes no filenames either: it invokes
    the bare command, so what the hook checks and what you check are the same list, read from
    the same place.
    """
    project, _ = generated_project
    source = (project / '_CI' / 'tasks' / 'preflight.py').read_text(encoding='utf-8')
    body = source.split("@logged('preflight.staged')", 1)[1].split('@task', 1)[0]
    assert 'paths or staged_files(context)' in body, 'an explicit --paths no longer wins'
    assert 'Nothing staged' in body, 'an empty index is not reported'

    # One reader, in `shared.py`, because `format --staged` asks the same question. A space in a
    # staged path has to fail loudly: `--paths` is space-separated the whole way down, so such a
    # path would otherwise split into fragments that match no step's filter and be dropped,
    # leaving the hook to pass because it checked nothing at all.
    shared = (project / '_CI' / 'tasks' / 'shared.py').read_text(encoding='utf-8')
    reader = shared.split('def staged_files', 1)[1].split('\ndef ', 1)[0]
    assert 'git diff --cached --name-only' in reader, 'the staged bundle no longer reads the index'
    assert 'splitlines()' in reader, 'the index is split on whitespace, so a path with a space breaks up'
    assert 'unsupported' in reader, 'a staged path containing a space is not refused'
    assert '--diff-filter=ACMR' in reader, 'a staged deletion is handed to a tool as a path'


def test_the_gate_renders_no_report_it_does_not_read(generated_project):
    """`preflight` produces the JSON its derived values need, and no browsable report.

    The rule, applied the same way to both tools that offer one. pyscn allows a single output
    format per run, so an HTML report there costs a whole second analysis; coverage renders one
    from data it already has, for a fraction of a second. Different prices, same answer —
    nothing in a hook or a pipeline opens an HTML report, and a gate that produces artefacts
    for an absent reader is a gate doing work nobody asked for. Two tools behaving alike in the
    pipeline is worth more than the fraction of a second.

    The reports are not lost, they are moved to where someone is actually looking:
    `quality.pyscn-analyze` produces the pyscn HTML and opens it, and `test.coverage` renders
    the coverage HTML from whatever the last run measured.
    """
    project, _ = generated_project
    tasks = project / '_CI' / 'tasks'
    gate_pyscn = (tasks / 'quality.py').read_text(encoding='utf-8').split('def pyscn_json_report', 1)[1]
    gate_pyscn = gate_pyscn.split('\n@', 1)[0]
    assert 'ANALYZE_JSON' in gate_pyscn, 'the gate no longer produces the JSON the badge reads'
    assert 'ANALYZE_HTML' not in gate_pyscn, 'the gate produces a pyscn HTML report nothing reads'

    test_py = (tasks / 'test.py').read_text(encoding='utf-8')
    gate_coverage = test_py.split('def combine_coverage', 1)[1].split('\n@', 1)[0]
    assert 'coverage json' in gate_coverage, 'the gate no longer produces the JSON the badge reads'
    assert 'coverage html' not in gate_coverage, 'the gate renders a coverage HTML report nothing reads'

    on_demand = test_py.split("@logged('test.coverage')", 1)[1].split('\n@task', 1)[0]
    assert 'coverage html' in on_demand, 'nothing renders the combined coverage report any more'


def test_pyscn_never_opens_a_browser_by_itself(generated_project):
    """Every pyscn run that writes HTML passes `--no-open`.

    pyscn launches a browser as soon as it writes an HTML report — verified with a stub
    `xdg-open`, which fires once for a bare `analyze` and not at all with `--no-open`. That
    made `quality.pyscn-analyze` open the report twice, once by itself and once from its own
    deliberate `open_target`, and made `pyscn_analyze_only` — "without opening the report" —
    open one anyway. It also had a tool reaching for a browser on a CI runner, where
    `is_ci()` exists precisely to prevent that.

    Whether a report is worth opening is the task's call, not the tool's.
    """
    project, _ = generated_project
    quality_py = (project / '_CI' / 'tasks' / 'quality.py').read_text(encoding='utf-8')
    # Command strings only — prose about `pyscn analyze` is not an invocation of it.
    html_runs = [line for line in quality_py.splitlines() if 'uv run pyscn analyze' in line and '--json' not in line]
    assert html_runs, 'no pyscn invocation produces an HTML report any more'
    for line in html_runs:
        assert '--no-open' in line, f'{line.strip()!r} lets pyscn open a browser on its own'


def test_the_docs_build_is_in_the_gate(generated_project):
    """`properdocs build --strict` runs on every push, not first at release time.

    A broken cross-reference or a page missing from the nav fails `--strict`, and publishing
    happens on a release tag. Without this step the first run that sees a bad link is the
    release pipeline, after the tag is pushed — the one moment there is no cheap way back.
    """
    project, _ = generated_project
    assert registry_steps(project).get('docs') == 'WHOLE_PROGRAM', 'the docs build is in no gate'
    document = (project / '_CI' / 'tasks' / 'document.py').read_text(encoding='utf-8')
    assert '--strict' in document, 'the docs build tolerates a broken link'


def test_a_report_a_reader_would_misread_is_cleared_first(generated_project):
    """Reports from a previous run do not survive into this one, pyscn's included.

    pyscn timestamps every report, so nothing overwrites anything and `reports/` grows for as
    long as the project runs its gate. Clearing also decides what an early failure means: with
    the directory empty the badge reports that it has no grade to read, instead of certifying
    one measured against a tree that has since changed. The per-env coverage reports go the
    same way, and for one more reason — named after an env, one from a dropped `env_list`
    entry would sit in `reports/` looking like a result from this run.
    """
    project, _ = generated_project
    quality = (project / '_CI' / 'tasks' / 'quality.py').read_text(encoding='utf-8')
    for name in ('pyscn_analyze', 'pyscn_analyze_only', 'pyscn_json_report'):
        body = quality.split(f'def {name}', 1)[1].split('\ndef ', 1)[0]
        assert 'clear_pyscn_reports()' in body, f'{name} can read a report from a previous run'
    test_py = (project / '_CI' / 'tasks' / 'test.py').read_text(encoding='utf-8')
    erase = test_py.split('def erase_coverage_data', 1)[1].split('\ndef ', 1)[0]
    assert "Path('reports').glob('coverage.*.json')" in erase, 'a retired env keeps its report'


def test_a_derived_value_that_cannot_be_written_fails_the_write(generated_project):
    """`preflight --write` exits non-zero when a value survives the writing.

    A reason survives `--write` only when the value could not be computed at all — its report
    missing, or unreadable. "Wrote nothing, exited 0" is the shape that lets a stale badge
    reach main through the command meant to refresh it, so both modes fail on it and only the
    hint about which command to run differs.
    """
    project, _ = generated_project
    source = (project / '_CI' / 'tasks' / 'preflight.py').read_text(encoding='utf-8')
    body = source.split('def artifacts', 1)[1].split('\nSTEPS', 1)[0]
    tail = body.split('for reason in reasons:', 1)[1]
    assert 'if not write:' in tail, 'both modes print the same hint'
    fix_hint, exit_call = tail.index('FIX_COMMAND'), tail.index('raise SystemExit(1)')
    assert fix_hint < exit_call, 'the hint comes after the exit, so nobody reads it'
    assert tail.split('raise SystemExit(1)')[0].count('if ') == 1, 'the exit is conditional again'


def test_a_badge_the_reader_removed_is_reported_not_assumed(generated_project):
    """A pattern that matches nothing says so, rather than reading as up to date.

    `re.sub` cannot tell "already correct" from "not there": both leave the content
    unchanged. So deleting or renaming a badge silently retired the check that guarded it,
    and the gate went on passing with one fewer thing to verify. Removing a badge stays the
    reader's decision — this workflow does not put it back — but it is said out loud.
    """
    project, _ = generated_project
    shared = (project / '_CI' / 'tasks' / 'shared.py').read_text(encoding='utf-8')
    body = shared.split('def apply_badge', 1)[1].split('\ndef ', 1)[0]
    assert 're.search(pattern' in body, 'a missing badge is indistinguishable from a current one'
    assert body.index('re.search(pattern') < body.index('re.sub('), 'the check comes after the substitution'


def test_the_gate_verifies_the_import_order_format_writes(generated_project):
    """Ruff `I` is selected wherever `format` fixes it, including under `_CI/`.

    `format` runs `ruff check --select I --fix` over `src/`, `_CI/tasks/` and `tests/`, while
    the gate only ran `ruff format --check`. Under `_CI/` ruff resolves `_CI/pyproject.toml`,
    which selected the defaults — so import order drifted there unwatched and `format` swept
    the correction into whatever commit came next, on files a `copier update` owns.
    """
    project, _ = generated_project
    ci_config = tomllib.loads((project / '_CI' / 'pyproject.toml').read_text(encoding='utf-8'))
    assert 'I' in ci_config['tool']['ruff']['lint']['select'], 'nothing checks the import order under _CI/'
    root = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    selected = root['tool']['ruff']['lint']['select']
    assert 'ALL' in selected or 'I' in selected, 'nothing checks the import order under src/'


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


def test_the_commit_message_check_is_bounded_to_this_push(generated_project):
    """`lint.commitizen` reads the commits a push adds, not every commit ever made.

    `cz check --rev-range HEAD` reads all reachable history, so one message that predates the
    convention fails every run from then on — and the only way past it is `SKIP=preflight`,
    which drops the whole gate. It is unfixable by design, too: rewriting published history is
    worse than the lint it satisfies. A push answers for the commits it adds.

    The shapes each candidate covers are asserted by
    `test_the_commit_message_check_sees_the_tip_in_every_checkout_shape`, which builds the
    repositories and reads the resolved range. This one only pins the declaration: greps of a
    function for its own literals are how the version of this check that shipped a no-op passed.
    """
    project, _ = generated_project
    lint = (project / '_CI' / 'tasks' / 'lint.py').read_text(encoding='utf-8')
    scope = lint.split('def commit_ranges', 1)[1].split('\n@task', 1)[0]
    for revision in ('PRE_COMMIT_FROM_REF', '@{upstream}', 'origin/HEAD', 'HEAD~1..HEAD'):
        assert revision in scope, f'the range no longer considers {revision}'
    body = lint.split("@logged('lint.commitizen')", 1)[1].split('\n@task', 1)[0]
    # Past the docstring, which quotes the unbounded form to explain why it is gone.
    code = body.split('"""', 2)[2]
    assert "--rev-range HEAD'" not in code, 'the check reads all of history again'
    assert 'unpushed_range(context)' in code, 'the check no longer bounds its range'


def test_importing_a_task_module_does_not_cost_a_second(generated_project):
    """The SBOM composer is imported by the tasks that compose one, not at module scope.

    `cyclonedx.validation.json` reaches `jsonschema._format` and a lark grammar built at
    import time: 1.0s, measured, of the 1.2s `_CI/tasks/sbom.py` costs to import. `build`
    imports `secure` imports `sbom`, so every `./workflow.cmd` paid it — `format`, `lint`, the
    commit hook, `--list`. Deferring it took `--list` from 1.37s to 0.15s.
    """
    project, _ = generated_project
    tasks = project / '_CI' / 'tasks'
    secure = (tasks / 'secure.py').read_text(encoding='utf-8')
    module_scope = secure.split('\n@task', 1)[0]
    assert 'from .sbom import' not in module_scope, 'importing secure.py pays for cyclonedx again'
    # Every module, not just `secure.py`: any of them importing `.sbom` at module scope brings
    # the cost back, since `preflight` imports most of them.
    for module in sorted(tasks.glob('*.py')):
        if module.name == 'sbom.py':
            continue
        head = module.read_text(encoding='utf-8').split('\ndef ', 1)[0].split('\n@', 1)[0]
        assert 'from .sbom import' not in head, f'{module.name} imports the SBOM composer at module scope'
        assert 'import cyclonedx' not in head, f'{module.name} imports cyclonedx at module scope'
    sbom = (tasks / 'sbom.py').read_text(encoding='utf-8')
    assert 'from cyclonedx.validation' not in sbom.split('\ndef ', 1)[0], (
        'the JSON validator is imported before anything validates'
    )


def test_the_push_hook_names_every_check_it_runs(generated_project):
    """The `name:` a developer reads on every push lists what the registry actually runs.

    That string is the only description of the gate most people ever see, and it drifted twice
    — `commitizen` and the docs build were both added to `STEPS` while it still said "ty,
    pyscn, test matrix, wheel, derived files". Naming each step here means a new one cannot be
    added without either updating the string or deciding, explicitly, that it needs no name.
    """
    project, _ = generated_project
    # The phrase each step is called in prose. `audit` is deliberately absent: it is in the
    # registry but off by default, being an answer about the advisory database rather than
    # about this tree.
    phrases = {
        'ty': 'ty (types)',
        'commitizen': 'commit messages',
        'docs': 'docs build',
        'pyscn': 'pyscn',
        'tox': 'test matrix',
        'build': 'wheel',
        'artifacts': 'derived files',
    }
    gate = next(hook for hook in pre_commit_hooks(project) if invoked_task(hook) == 'preflight')
    whole_program = [name for name, scope in registry_steps(project).items() if scope == 'WHOLE_PROGRAM']
    unnamed = [name for name in whole_program if name != 'audit' and name not in phrases]
    assert not unnamed, f'steps with no agreed phrase for the hook name: {unnamed}'
    for name in whole_program:
        if name == 'audit':
            assert 'audit' not in gate['name'], 'the hook name promises an audit it does not run'
            continue
        assert phrases[name] in gate['name'], f'{name!r} runs on every push and the hook does not say so'


def test_formatting_what_is_staged_needs_no_shell(generated_project):
    """`format --staged` reads the index itself, and the how-to no longer builds a path list.

    The recipe was `--paths="$(git diff --cached --name-only)"`, which had three failure modes:
    an empty index reformatted the whole tree — the exact hazard the paragraph beneath it warns
    about — staged Markdown failed on ruff's experimental-formatter error, and a staged
    deletion failed on a missing file.
    """
    project, _ = generated_project
    body = (project / '_CI' / 'tasks' / 'format_.py').read_text(encoding='utf-8')
    task_body = body.split("@logged('format')", 1)[1]
    assert 'staged: bool = False' in task_body, 'there is no way to format just what is staged'
    assert 'CODE_FILES.match(path)' in task_body, (
        "the formatter has its own idea of which files are the project's, so the two can drift"
    )
    assert 'No staged Python files' in task_body, 'an empty index falls back to the whole tree'
    how_to = (project / 'docs' / 'developer' / 'how-to' / 'skip-a-check.md').read_text(encoding='utf-8')
    assert 'format --staged' in how_to, 'the how-to does not name the flag'
    assert 'git diff --cached --name-only' not in how_to, 'the how-to still assembles a path list'
    # In the commands, not in the prose: the paragraph beneath them explains what `git add -A`
    # would do, which is the reason the recipe does not use it.
    commands = [
        line.strip() for index, block in enumerate(how_to.split('```')) if index % 2 for line in block.splitlines()
    ]
    assert 'git add -A' not in commands, 'the how-to sweeps the whole tree into the commit again'


def git(repository, *arguments: str, check: bool = True):
    """Run git in `repository` with a fixed identity, so nothing depends on the host config."""
    identity = ('-c', 'user.name=t', '-c', 'user.email=t@example.invalid', '-c', 'commit.gpgsign=false')
    return subprocess.run(
        ['git', *identity, *arguments],
        cwd=str(repository),
        capture_output=True,
        text=True,
        check=check,
    )


def range_resolver(project):
    """Return the generated `unpushed_range`, bound to a context that runs git for real.

    Read out of the generated source rather than imported: importing `_CI.tasks.lint` pulls in
    invoke and every sibling task module behind it. These three functions depend on nothing but
    `os` and the context's `run`, so the smallest honest harness execs them alone.
    """
    source = (project / '_CI' / 'tasks' / 'lint.py').read_text(encoding='utf-8')
    wanted = ('resolves', 'commit_ranges', 'unpushed_range')
    body = [node for node in ast.parse(source).body if getattr(node, 'name', None) in wanted]
    # One dict as globals, not globals-plus-locals: the functions call each other, so they have
    # to land where their own name lookups go.
    namespace = {'os': os, 'Context': object, 'Iterator': list}
    module = ast.Module(body=body, type_ignores=[])
    exec(compile(module, '<lint.py>', 'exec'), namespace)  # noqa: S102
    assert set(wanted) <= set(namespace), f'lint.py no longer defines all of {wanted}'

    class GitContext:
        """The slice of invoke's Context these functions touch: `run` returning stdout and failure."""

        def __init__(self, repository) -> None:
            self.repository = repository

        def run(self, command, *, hide=False, warn=False):  # noqa: ARG002
            done = subprocess.run(  # noqa: S602 — the commands are this test's own git literals
                command, shell=True, cwd=str(self.repository), capture_output=True, text=True, check=False
            )
            return SimpleNamespace(failed=done.returncode != 0, stdout=done.stdout)

    return lambda repository: namespace['unpushed_range'](GitContext(repository))


def commits_in(repository, revision_range):
    """Return the subjects `cz check` would be handed for `revision_range`."""
    if revision_range is None:
        return []
    listed = git(repository, 'log', '--format=%s', revision_range)
    return [line for line in listed.stdout.splitlines() if line]


def test_the_commit_message_check_sees_the_tip_in_every_checkout_shape(generated_project):
    """Whatever the clone looks like, the range covers the commit that just arrived.

    This is the test that was missing. Its string-level predecessor asserted the fallback chain
    and passed while that chain resolved to nothing in GitHub CI: `actions/checkout` fetches one
    commit and runs `checkout -B main refs/remotes/origin/main`, so the branch does track
    `origin/main` and `origin/main` is `HEAD`. The range came out empty, the step reported
    nothing to check, and the run that exists to catch what the hook cannot — a `--no-verify`
    commit, a clone with no hooks — validated no message at all. GitLab's detached checkout took
    a different branch of the same code and did fail, so one check gave two answers by host.

    Also asserted: settled history stays out of the range, which is the deadlock the scoping
    exists to avoid.
    """
    project, cell = generated_project
    # `lint.py` ships identically in every cell, so one cell is enough for a test that builds
    # repositories rather than reading files.
    if cell['label'] != matrix_combos()[0]['label']:
        return
    resolve = range_resolver(project)
    root = project.parent / 'range-shapes'
    root.mkdir(exist_ok=True)

    origin = root / 'origin.git'
    git(root, 'init', '--quiet', '--bare', str(origin))
    upstream = root / 'work'
    upstream.mkdir()
    git(upstream, 'init', '--quiet', '-b', 'main')
    git(upstream, 'commit', '--quiet', '--allow-empty', '-m', 'feat: the first one')
    git(upstream, 'commit', '--quiet', '--allow-empty', '-m', 'WIP unconventional')
    git(upstream, 'remote', 'add', 'origin', str(origin))
    git(upstream, 'push', '--quiet', 'origin', 'main')

    # What `actions/checkout@v6` does: one commit, then a local branch tracking the remote.
    github = root / 'github-runner'
    github.mkdir()
    git(github, 'init', '--quiet', '.')
    git(github, 'remote', 'add', 'origin', str(origin))
    git(
        github,
        '-c',
        'protocol.version=2',
        'fetch',
        '--quiet',
        '--no-tags',
        '--prune',
        '--depth=1',
        'origin',
        '+refs/heads/main*:refs/remotes/origin/main*',
    )
    git(github, 'checkout', '--quiet', '--force', '-B', 'main', 'refs/remotes/origin/main')
    assert git(github, 'rev-parse', '--abbrev-ref', '@{upstream}').stdout.strip() == 'origin/main', (
        'the premise of this test is gone: that checkout no longer sets branch tracking'
    )
    assert 'WIP unconventional' in commits_in(github, resolve(github)), (
        'CI validates no message at all, on the only run that can catch one the hook did not see'
    )

    # What GitLab's runner does: a detached checkout at a shallow depth.
    gitlab = root / 'gitlab-runner'
    gitlab.mkdir()
    git(gitlab, 'init', '--quiet', '.')
    git(gitlab, 'remote', 'add', 'origin', str(origin))
    git(gitlab, 'fetch', '--quiet', '--depth', '20', 'origin', 'main')
    git(gitlab, 'checkout', '--quiet', '--detach', 'FETCH_HEAD')
    assert 'WIP unconventional' in commits_in(gitlab, resolve(gitlab)), 'the detached shape checks nothing'

    # A developer with the message still unpushed.
    git(upstream, 'commit', '--quiet', '--allow-empty', '-m', 'nope: mine to fix')
    assert 'nope: mine to fix' in commits_in(upstream, resolve(upstream)), 'an unpushed message goes unchecked'

    # Once it is pushed and a good commit follows, the old one is nobody's problem.
    git(upstream, 'push', '--quiet', 'origin', 'main')
    git(upstream, 'commit', '--quiet', '--allow-empty', '-m', 'feat: moving on')
    subjects = commits_in(upstream, resolve(upstream))
    assert subjects == ['feat: moving on'], f'the range reaches back into settled history: {subjects}'

    # pre-commit hands a pre-push hook the push's own range, and that wins when it is there.
    base = git(upstream, 'rev-parse', 'HEAD~2').stdout.strip()
    os.environ['PRE_COMMIT_FROM_REF'], os.environ['PRE_COMMIT_TO_REF'] = base, 'HEAD'
    try:
        assert 'nope: mine to fix' in commits_in(upstream, resolve(upstream)), (
            'the range pre-commit supplies loses to an inference about it'
        )
    finally:
        del os.environ['PRE_COMMIT_FROM_REF'], os.environ['PRE_COMMIT_TO_REF']

    # No commits at all is the one case with nothing to say.
    empty = root / 'fresh'
    empty.mkdir()
    git(empty, 'init', '--quiet', '.')
    assert resolve(empty) is None, 'an empty repository resolves a range'


def test_the_docs_build_runs_before_the_matrix(generated_project):
    """`docs` sits ahead of the expensive steps, which is what makes its verdict early.

    `run_scope` runs every step regardless of failure, so the registry's order is the only
    thing that decides how long a verdict takes. The docs build costs 1.3s and the steps after
    it cost twelve, so a broken cross-reference is reported at 1.7s of a 13.8s run — put it
    behind the matrix instead and the same failure takes ten seconds to surface. pylint moved
    behind it for the same reason: five of those twelve seconds are pylint's, and everything
    cheaper that can also fail should have spoken first.
    """
    project, _ = generated_project
    order = list(registry_steps(project))
    for earlier, later in (('docs', 'pyscn'), ('docs', 'tox'), ('docs', 'build'), ('complexipy', 'pylint')):
        assert order.index(earlier) < order.index(later), (
            f'{earlier!r} now runs after {later!r}, so its verdict waits for a slower step'
        )


def test_the_coverage_floor_is_enforced_by_exactly_one_command(generated_project):
    """Every coverage command except the union's own JSON write opts out of `fail_under`.

    `[tool.coverage.report] fail_under` applies to whatever command reads the data, and the
    floor is set from the union across `env_list` — so any command seeing one interpreter's
    data would fail on a bar that data cannot clear. Correctness therefore rests on every call
    site passing `--fail-under=0`, which is a rule about call sites rather than about
    configuration, and this is the walk over them.
    """
    project, _ = generated_project
    test_py = (project / '_CI' / 'tasks' / 'test.py').read_text(encoding='utf-8')
    combine = test_py.split('def combine_coverage', 1)[1].split('\n@', 1)[0]
    union = [line for line in combine.splitlines() if 'coverage json -o' in line and '{COVERAGE_REPORT}' in line]
    enforcing = [line.strip() for line in union if '--fail-under' not in line]
    assert len(enforcing) == 1, f'the floor is enforced by {len(enforcing)} commands, not one: {enforcing}'

    reads = [
        line.strip()
        for line in test_py.splitlines()
        if re.search(r'uv run coverage (report|json|html)', line) and line.strip() not in enforcing
    ]
    assert reads, 'no coverage commands left to check, so this walk has stopped walking'
    for command in reads:
        assert '--fail-under=0' in command, f'{command} is gated by a floor its data cannot clear'

    data = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    addopts = data['tool']['pytest']['ini_options']['addopts']
    assert '--cov-fail-under=0' in addopts, 'pytest-cov enforces the union floor per interpreter again'


def test_matrix_envs_do_not_share_report_paths(generated_project):
    """Every tox env writes its report to its own path, and a plain run renders nothing else.

    `addopts` sends the JSON report to one fixed path, so under `run-parallel` all five envs
    wrote `reports/coverage.json` simultaneously. It stayed invisible while nothing read that
    file; the moment the coverage badge and the `fail_under` ratchet read it, they would be
    reading whichever env finished last, possibly mid-write.

    No HTML from a plain run, per env or otherwise: nothing in a hook or a pipeline opens one,
    and rendering them is most of a scaffold's test run. `test.coverage` and `test.view`
    produce them on demand.
    """
    project, _ = generated_project
    data = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    addopts = data['tool']['pytest']['ini_options']['addopts']
    commands = data['tool']['tox']['env_run_base']['commands']
    specs = [argument for command in commands for argument in command if isinstance(argument, str)]

    overrides = [spec for spec in specs if spec.startswith('--cov-report=json:')]
    assert overrides, 'no per-env override for --cov-report=json:'
    for spec in overrides:
        assert '{envname}' in spec, f'{spec!r} is fixed, so parallel envs clobber each other'

    for flag in ('--cov-report=html:', '--html='):
        rendered = [spec for spec in (*addopts, *specs) if spec.startswith(flag)]
        assert not rendered, f'a plain run renders {flag} for nobody: {rendered}'

    # `-n auto` under `run-parallel` asks for one pool per env, which measured slower on
    # sixteen cores than the same config on four.
    assert 'auto' not in addopts, 'every env spawns a pool sized for the whole machine'
    assert '-n' in addopts, 'the worker count is no longer pinned'


def test_matrix_coverage_is_combined_before_anything_reads_it(generated_project):
    """`test.tox` erases, runs the matrix, then combines into the one report the badge reads.

    Combining takes the union of the lines each interpreter executed, which is the only
    correct reading of a version matrix: version-gated code cannot be fully covered by any
    single env, so reading one env's report understates coverage on exactly the code the
    matrix exists to exercise. The erase is what stops a `.coverage.<env>` left over from an
    env since removed from `env_list` being folded into that union.
    """
    project, _ = generated_project
    test_py = (project / '_CI' / 'tasks' / 'test.py').read_text(encoding='utf-8')
    # Past the closing `"""`, so the docstring's own mention of combine_coverage — which
    # precedes every command — cannot satisfy the ordering assertions below.
    body = test_py.split('def tox_matrix', 1)[1].split('\n@', 1)[0].split('"""')[-1]
    for step in ('erase_coverage_data', 'tox run', 'combine_coverage'):
        assert step in body, f'the matrix no longer runs {step!r}'
    assert body.index('erase_coverage_data') < body.index('tox run'), 'stale coverage data is not cleared first'
    # Not `coverage erase`: it leaves `.coverage.<envname>` in place, so a retired env's data
    # would still be combined into the union that feeds the badge and the ratchet.
    erase = test_py.split('def erase_coverage_data', 1)[1].split('\ndef ', 1)[0]
    assert "Path().glob('.coverage.*')" in erase, 'the per-env data files are no longer cleared'
    assert body.index('tox run') < body.index('combine_coverage'), 'coverage is combined before the matrix runs'
    combine = test_py.split('def combine_coverage', 1)[1].split('\n@task', 1)[0]
    assert 'coverage combine' in combine, 'the per-env data is never merged'
    assert 'coverage json -o {COVERAGE_REPORT}' in combine, 'the union never reaches the report the badge reads'
    # And it gates only when the data under it is the union the floor was measured from.
    # `test.tox --env=py310` combines one env's data: enforcing there failed the command whose
    # whole purpose is looking at one interpreter, on any project with an engaged ratchet.
    assert 'combine_coverage(context, scope=env)' in test_py, 'the combine no longer knows its scope'
    # The two writes, by command line rather than by prose: the comments around them discuss
    # `--fail-under=0` as well.
    writes = [line for line in combine.splitlines() if 'coverage json -o' in line]
    scoped = [line for line in writes if '{scope}' in line]
    union = [line for line in writes if '{COVERAGE_REPORT}' in line]
    assert scoped, "one interpreter's data is written to the union's name"
    assert all('--fail-under=0' in line for line in scoped), 'one interpreter is gated by a floor set from five'
    assert union, 'the union never reaches the report the badge reads'
    assert not any('--fail-under=0' in line for line in union), 'the union run does not enforce the floor either'


def test_only_what_measures_a_derived_value_may_write_it(generated_project):
    """A derived value is written by whatever produced the data behind it — and nothing else.

    Not "only `preflight` writes", which was the earlier rule and too blunt. The coverage badge
    means coverage across every interpreter in `env_list`, so `test.tox` may write it: that is
    exactly what it measured. `test` and `test.coverage` measure one interpreter, so they may
    neither write it nor comment on it — a single-interpreter number is not the badge's
    quantity, and warning about it would be a claim they cannot support. Demonstrated before
    the change: `test` wrote 85% from one interpreter and the gate then rejected it as stale
    against the union's 100%.

    `document` is the same argument for a different reason. Version, Python range and the CI
    badge's URL come from tracked files, so it can vouch for those; coverage and pyscn come
    from reports it does not produce, so it would be stamping in whatever a previous run left.

    Writing stays opt-in via `--write` wherever it is allowed, and the gate verifies all five.
    """
    project, _ = generated_project
    tasks = project / '_CI' / 'tasks'
    test_py = (tasks / 'test.py').read_text(encoding='utf-8')

    # One interpreter: no write, and no comment either.
    for task_name in ("@logged('test')", "@logged('test.coverage')"):
        body = test_py.split(task_name, 1)[1].split('\n@', 1)[0]
        assert 'update_coverage_badge' not in body, f'{task_name} writes the coverage badge again'
        assert 'ratchet_fail_under' not in body, f'{task_name} moves the ratchet again'

    # The matrix: writes under --write, reports otherwise, refuses a narrowed run.
    tox_task = test_py.split("@logged('test.tox')", 1)[1].split('\n@', 1)[0]
    assert 'note(update_coverage_badge(write=write))' in tox_task, 'the matrix no longer owns the badge'
    assert 'note(ratchet_fail_under(write=write))' in tox_task, 'the matrix no longer owns the ratchet'
    assert 'if env and write:' in tox_task, 'a narrowed matrix can still write the badge'

    # The registry runs the non-writing entry point, so a hook and a pipeline write nothing.
    preflight = (tasks / 'preflight.py').read_text(encoding='utf-8')
    assert 'check=tox_matrix' in preflight, 'the gate runs the writing task instead of the matrix'

    # pyscn measured the grade, so it may write the badge — but only when asked.
    quality = (tasks / 'quality.py').read_text(encoding='utf-8')
    for task_name in ('def pyscn_analyze(', 'def pyscn_analyze_only(', 'def pyscn('):
        signature = quality.split(task_name, 1)[1].split(')', 1)[0]
        assert 'write: bool = False' in signature, f'{task_name} writes the pyscn badge unasked'

    # And `document` writes no badge at all: building docs is not changing the README.
    document = (tasks / 'document.py').read_text(encoding='utf-8')
    aggregator = document.split("@logged('document')", 1)[1]
    for absent in ('update_coverage_badge', 'update_pyscn_badge', 'update_package_version_badge'):
        assert absent not in aggregator, f'document writes {absent} unasked'

    # Which leaves no task writing a tracked file unasked: every write is behind `--write` or
    # inside a command named for the mutation it performs.
    release = (tasks / 'release.py').read_text(encoding='utf-8')
    bump = release.split("@logged('release.bump')", 1)[1].split('\n@', 1)[0]
    assert 'update_package_version_badge(version=' in bump, (
        'release.bump lands a README that contradicts the version it released'
    )


def test_the_ci_badge_is_the_hosts_own(generated_project):
    """The CI badge points at the host's status endpoint, and no task records a build status.

    It used to be written locally by `build`, recording whether *that* run passed — which told
    a reader nothing, could claim "passing" on a run that then failed, and on GitLab was never
    written at all: `build.py` matched only the `Build` badge that GitHub projects render, so
    every GitLab project shipped a `pipeline-unknown` badge nothing could update.

    The host renders the current status on every page load, so only the URL is derived, from
    `origin`, and it stops changing once written. A project with no readable `origin` keeps its
    placeholder rather than being reported stale — not pushed anywhere is not the same as wrong.
    """
    project, cell = generated_project
    tasks = project / '_CI' / 'tasks'
    # Asserted against code, not prose: the docstring explains the absence, so matching the
    # word "README" would fail on the explanation itself.
    build_py = (tasks / 'build.py').read_text(encoding='utf-8')
    assert "Path('README.md')" not in build_py, 'build writes the README again'
    assert 'apply_badge' not in build_py, 'build writes a badge again'

    host_module = (tasks / f'{cell["git_hosting_service"]}.py').read_text(encoding='utf-8')
    assert 'def pipeline_badge' in host_module, 'the host module builds no CI badge'
    expected = 'actions/workflows' if cell['git_hosting_service'] == 'github' else 'badges/main/pipeline.svg'
    assert expected in host_module, f'the CI badge does not point at the host: {expected!r} missing'

    document = (tasks / 'document.py').read_text(encoding='utf-8')
    assert 'def update_pipeline_badge' in document, 'nothing points the CI badge anywhere'
    updater = document.split('def update_pipeline_badge', 1)[1].split('\ndef ', 1)[0]
    unknown_remote = updater.split('pipeline_badge(context)', 1)[1].split('return apply_badge', 1)[0]
    assert 'return None' in unknown_remote, 'a project without a remote is reported stale, not left alone'
    # And not verified at all: the value comes from `origin`, the developer's own configuration,
    # so "is it stale?" has no tree-level answer. Verifying it would fail the gate for a
    # contributor whose remote is legitimately a fork, and the fix it named would point
    # upstream's badge at that fork.
    body = updater.split('"""', 2)[2]
    assert body.index('if not write:') < body.index('pipeline_badge(context)'), (
        'the CI badge is compared against a remote the reader may not share'
    )


def test_readme_has_exactly_one_writer(generated_project):
    """Every write to README.md goes through `apply_badge`, so check mode cannot drift.

    A `preflight` that verifies is only trustworthy if it compares against the same substitution the
    writer applies. A second module that rewrote a badge its own way would be invisible to the
    check — the badge would be updated by one code path and verified by another, which is the
    failure this whole shape exists to prevent.
    """
    project, _ = generated_project
    tasks = project / '_CI' / 'tasks'
    for module in sorted(tasks.glob('*.py')):
        source = module.read_text(encoding='utf-8')
        if 'README.md' not in source or module.name == 'shared.py':
            continue
        assert 'write_text' not in source, f'{module.name} writes README.md without going through apply_badge'


def test_derived_values_are_computed_in_both_modes_by_one_function(generated_project):
    """Each derived value has a single updater that takes `write`, rather than a paired checker.

    The generator and the gate being one function is what makes a verifying `preflight` mean
    anything. Splitting them — a writer here, a verifier there — is exactly how a check ends up
    passing on a value the writer would have changed.
    """
    project, _ = generated_project
    tasks = project / '_CI' / 'tasks'
    updaters = {
        'quality.py': ['update_pyscn_badge'],
        'test.py': ['update_coverage_badge', 'ratchet_fail_under'],
        'document.py': ['update_package_version_badge', 'update_python_badge', 'update_pipeline_badge'],
    }
    for filename, names in updaters.items():
        tree = ast.parse((tasks / filename).read_text(encoding='utf-8'))
        functions = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        for name in names:
            assert name in functions, f'{filename} no longer defines {name}'
            kwonly = [argument.arg for argument in functions[name].args.kwonlyargs]
            assert 'write' in kwonly, f'{name} takes no keyword-only `write`, so it cannot verify without writing'


def test_local_task_module_ships_with_a_namespace(generated_project):
    """`_CI/tasks/local.py` ships and exposes a `local` collection ready to add tasks to."""
    project, _ = generated_project
    local = project / '_CI' / 'tasks' / 'local.py'
    assert local.is_file(), 'no project-owned task module ships'
    source = local.read_text(encoding='utf-8')
    assert "Collection('local')" in source, 'local.py defines no namespace for __init__ to pick up'


def test_local_task_module_is_protected_from_updates():
    """`local.py` is in `_skip_if_exists`, without which the seam is pointless.

    The whole reason it exists is that template-owned modules are replaced on
    `copier update`. If it were not skipped it would be overwritten or conflict on every
    update — exactly the problem it is meant to remove.
    """
    config = yaml.safe_load((REPO_ROOT / 'copier.yml').read_text(encoding='utf-8'))
    skipped = config.get('_skip_if_exists') or []
    assert '_CI/tasks/local.py' in skipped, f'local.py is not protected from updates; skipped={skipped}'


def test_local_tasks_need_no_registration(generated_project):
    """`__init__.py` discovers `local.py` itself, so adding a task never edits template files.

    Registration used to mean editing `__init__.py` and its bootstrap loop — both
    template-owned, so every local task cost a merge conflict on every update.
    """
    project, _ = generated_project
    init = (project / '_CI' / 'tasks' / '__init__.py').read_text(encoding='utf-8')
    assert 'LOCAL_MODULE' in init, 'local.py is not referenced by __init__'
    assert 'is_file()' in init, 'local.py is imported unconditionally, so its absence would break'
    assert 'local.namespace' in init, 'the local namespace is never added'
    assert 'modules.append(local)' in init, 'local tasks would not get the bootstrap pre-task'


def test_add_a_workflow_task_directs_people_to_local(generated_project):
    """The how-to points at `local.py` and no longer tells people to edit `__init__.py`.

    The doc previously instructed readers to create a module *and* register it in
    `_CI/tasks/__init__.py`, which guaranteed a conflict on the next update.
    """
    project, _ = generated_project
    how_to = (project / 'docs' / 'developer' / 'how-to' / 'add-a-workflow-task.md').read_text(encoding='utf-8')
    assert 'local.py' in how_to, 'the how-to never mentions the project-owned module'
    assert 'Register it in `_CI/tasks/__init__.py`' not in how_to, 'the how-to still tells people to edit __init__.py'


def test_documented_launcher_matches_the_real_one(generated_project):
    """The architecture doc quotes the launcher that actually ships.

    It previously described `uv run python -m _CI.invoke -- <args>` — a module that has never
    existed — alongside an `@echo off` first line the file does not have. Anyone debugging the
    launcher from that description would be looking for code that isn't there.
    """
    project, _ = generated_project
    launcher = (project / 'workflow.cmd').read_text(encoding='utf-8')
    doc = (project / 'docs' / 'developer' / 'explanation' / 'the-ci-tasks-architecture.md').read_text(encoding='utf-8')
    assert '_CI.invoke' not in doc, 'the doc still cites a nonexistent _CI.invoke module'
    # Every non-shebang line of the real launcher must appear verbatim in the doc.
    for line in (line.strip() for line in launcher.splitlines()):
        if not line or line.startswith('#!'):
            continue
        assert line in doc, f'launcher line not documented: {line!r}'
    # And the dispatch mechanism the two interpreters rely on is explained, not just shown.
    assert 'exec' in doc, 'the doc omits the sh side of the dispatch'
    assert 'label' in doc, 'the doc omits the cmd label trick that makes the dispatch work'


def test_launcher_dispatch_is_intact(generated_project):
    """The launcher execs on the sh line so the cmd line is unreachable from a POSIX shell.

    Without `exec`, sh would fall through and try to run the Windows line as a command.
    """
    project, _ = generated_project
    lines = [line.strip() for line in (project / 'workflow.cmd').read_text(encoding='utf-8').splitlines()]
    posix = next(line for line in lines if line.startswith(': ;'))
    assert 'exec ' in posix, 'sh would fall through to the Windows line'
    assert posix.startswith(': ;'), 'cmd relies on this line reading as a label'
    assert '--search-root _CI' in posix


def test_no_predecessor_template_name_survives(generated_project):
    """Nothing still calls the CI tooling package by the template's former name.

    `_CI/pyproject.toml` named it `backbone-template`, which pip-compile then stamped into
    every `# via …` comment in `vendor.txt` — so the stale name was reproduced on each
    re-vendor.
    """
    project, _ = generated_project
    for relative in ('_CI/pyproject.toml', '_CI/lib/vendor.txt'):
        for root in (project, REPO_ROOT):
            content = (root / relative).read_text(encoding='utf-8')
            assert 'backbone' not in content.lower(), f'{root / relative} still names backbone-template'


def test_vendor_comments_agree_with_the_package_name(generated_project):
    """`vendor.txt`'s `# via <name>` comments match `_CI/pyproject.toml`'s project name.

    pip-compile derives them from that name, so a mismatch means the two would diverge again
    the next time the vendored tree is regenerated.
    """
    project, _ = generated_project
    for root in (project, REPO_ROOT):
        name = re.search(
            r"^name = ['\"]([^'\"]+)['\"]", (root / '_CI' / 'pyproject.toml').read_text(encoding='utf-8'), re.MULTILINE
        ).group(1)
        vendor = (root / '_CI' / 'lib' / 'vendor.txt').read_text(encoding='utf-8')
        # pip-compile indents the `# via …` comment under the requirement it belongs to.
        cited = set(re.findall(r'^\s*#\s+via ([a-z0-9-]+) \(pyproject\.toml\)\s*$', vendor, re.MULTILINE))
        assert cited, f'{root}: no self-referential via comments found in vendor.txt'
        assert cited == {name}, f'{root}: vendor.txt cites {cited}, pyproject declares {name!r}'


def test_sidebar_nav_override_ships(generated_project):
    """The sidebar site-nav theme override ships and is wired into properdocs.yml."""
    project, _ = generated_project
    override = project / 'docs-theme' / 'toc.html'
    assert override.is_file()
    assert 'site_nav_item' in override.read_text(encoding='utf-8')
    config = yaml.safe_load((project / 'properdocs.yml').read_text(encoding='utf-8'))
    assert config['theme']['custom_dir'] == 'docs-theme'


def test_no_hidden_dirs_in_docs(generated_project):
    """No dotfile/dotdir junk ships under docs/ (guards against tool-state directories leaking in)."""
    project, _ = generated_project
    hidden = [
        str(path.relative_to(project / 'docs'))
        for path in (project / 'docs').rglob('*')
        if any(part.startswith('.') for part in path.relative_to(project / 'docs').parts)
    ]
    assert not hidden, f'hidden paths shipped under docs/: {hidden}'


SHIPPED_EXPLANATION_DIR = 'template/docs/developer/explanation'
SHIPPED_RATIONALE_PAGES = {
    'docs/maintaining/explanation/design-principles.md': f'{SHIPPED_EXPLANATION_DIR}/design-principles.md',
    'docs/maintaining/explanation/the-ci-tasks-architecture.md': (
        f'{SHIPPED_EXPLANATION_DIR}/the-ci-tasks-architecture.md'
    ),
    'docs/using/explanation/how-uv-is-used.md': f'{SHIPPED_EXPLANATION_DIR}/how-uv-is-used.md',
    'docs/using/explanation/sbom-and-security-model.md': f'{SHIPPED_EXPLANATION_DIR}/sbom-and-security-model.md.jinja',
    'docs/using/explanation/testing-strategy.md': f'{SHIPPED_EXPLANATION_DIR}/testing-strategy.md',
}


def extract_h2_headings(markdown_text):
    """Return the set of `## ` headings, ignoring jinja-only lines."""
    return {
        line.strip()
        for line in markdown_text.splitlines()
        if line.startswith('## ') and '{%' not in line and '{{' not in line
    }


@pytest.mark.parametrize('canonical_path', sorted(SHIPPED_RATIONALE_PAGES), ids=lambda p: Path(p).stem)
def test_shipped_rationale_pages_match_canonical(canonical_path):
    """Shipped rationale copies carry the canonical marker and stay structurally aligned.

    The drift ratchet promised in docs/maintaining/how-to/sync-shipped-docs.md: each shipped
    copy's ``##`` headings must be a subset of its canonical page's headings, so renaming or
    removing a canonical section forces the shipped copy to follow.
    """
    canonical = (REPO_ROOT / canonical_path).read_text(encoding='utf-8')
    shipped = (REPO_ROOT / SHIPPED_RATIONALE_PAGES[canonical_path]).read_text(encoding='utf-8')
    shipped_path = SHIPPED_RATIONALE_PAGES[canonical_path]
    assert shipped.startswith('<!-- canonical:'), f'{shipped_path} lacks the canonical marker'
    assert canonical_path in shipped.splitlines()[0], 'canonical marker does not name its source page'
    extra = extract_h2_headings(shipped) - extract_h2_headings(canonical)
    assert not extra, f'shipped copy has headings the canonical page lacks: {extra}'


@pytest.mark.parametrize('license_choice', ['Apache-2.0', 'MIT', 'BSD-3-Clause', 'None'])
def test_license_file_matches_choice(template_snapshot, tmp_path_factory, license_choice):
    """Each license choice produces (or skips) a LICENSE file at the project root."""
    workdir = tmp_path_factory.mktemp(f'license-{license_choice}')
    data_file = workdir / 'data.json'
    data_file.write_text(json.dumps({'license': license_choice}), encoding='utf-8')
    project = workdir / PROJECT_SLUG
    subprocess.run(
        [
            'uvx',
            'copier',
            'copy',
            '--defaults',
            '--trust',
            '--data-file',
            str(data_file),
            str(template_snapshot),
            str(project),
        ],
        check=True,
        capture_output=True,
        # Pin the stamped uv version: this test only cares about LICENSE, so there is no
        # reason for it to resolve a release over the network.
        env={**os.environ, **generation_env()},
    )
    if license_choice == 'None':
        assert not (project / 'LICENSE').exists()
    else:
        assert (project / 'LICENSE').exists()


VENDOR_TREES = ('_CI/lib', 'template/_CI/lib')
# Distribution names in vendor.txt do not always match the importable directory.
VENDOR_DIRECTORY_ALIASES = {'pip-tools': 'piptools', 'rpds-py': 'rpds', 'typing-extensions': 'typing_extensions'}


def source_files(vendor):
    """Yield the committed files of a vendored tree, skipping bytecode caches.

    Only one of the two trees is ever executed — this repository runs `_CI/lib/vendor`, while
    the template's copy is only ever copied — so `__pycache__` appears in one and not the
    other. Comparing them would make the result depend on whether anything had run yet, which
    is how this passed locally and failed in CI.
    """
    return [
        path
        for path in vendor.rglob('*')
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc'
    ]


def vendored_packages(lib_directory):
    """Return the importable top-level package directories in a vendored tree."""
    vendor = lib_directory / 'vendor'
    ignored = {'bin', '__pycache__'}
    return {path.name for path in vendor.iterdir() if path.is_dir() and path.name not in ignored}


def manifest_packages(lib_directory):
    """Return the distribution names pinned in a tree's vendor.txt, mapped to directory names."""
    text = (lib_directory / 'vendor.txt').read_text(encoding='utf-8')
    names = {line.split('==')[0].strip() for line in text.splitlines() if re.match(r'^[A-Za-z]', line)}
    return {VENDOR_DIRECTORY_ALIASES.get(name, name.replace('-', '_')) for name in names}


@pytest.mark.parametrize('tree', VENDOR_TREES)
def test_vendored_tree_matches_its_manifest(tree):
    """Every vendored package is pinned in vendor.txt, and every pin is present in the tree.

    The tree is an output of `vendoring sync`, not a place to add or delete files. A package
    present without a pin means someone edited the tree by hand; a pin without a package means
    the tree is stale. Either way it no longer reproduces from its declared input.
    """
    lib = REPO_ROOT / tree
    on_disk, pinned = vendored_packages(lib), manifest_packages(lib)
    assert on_disk == pinned, f'{tree}: unpinned {sorted(on_disk - pinned)}, missing {sorted(pinned - on_disk)}'


@pytest.mark.parametrize('tree', VENDOR_TREES)
def test_vendored_tree_is_pure_python(tree):
    """No compiled extensions in a tree whose entire purpose is running anywhere.

    Vendoring `tomli` produced a `__mypyc.cpython-314-darwin.so`: 427 KiB usable on exactly one
    operating system, architecture and Python version, shipped to every generated project.
    A binary here is portability quietly lost, and nothing else would report it.
    """
    vendor = REPO_ROOT / tree / 'vendor'
    binaries = [str(p.relative_to(vendor)) for p in vendor.rglob('*') if p.suffix in {'.so', '.pyd', '.dylib'}]
    assert not binaries, f'{tree}: platform-specific binaries vendored: {binaries}'


def test_both_vendored_trees_are_identical():
    """This repository and the template ship the same vendored invoke, byte for byte.

    They are two copies of one upstream artefact. Letting them drift means a generated project
    runs different code from the repository that produced it, and the difference would only
    surface as a bug somewhere downstream.
    """
    parent, template = (REPO_ROOT / tree / 'vendor' for tree in VENDOR_TREES)
    parent_files = {p.relative_to(parent): p.read_bytes() for p in source_files(parent)}
    template_files = {p.relative_to(template): p.read_bytes() for p in source_files(template)}
    assert parent_files.keys() == template_files.keys(), (
        f'only in _CI: {sorted(map(str, parent_files.keys() - template_files.keys()))}; '
        f'only in template: {sorted(map(str, template_files.keys() - parent_files.keys()))}'
    )
    differing = sorted(str(name) for name, data in parent_files.items() if template_files[name] != data)
    assert not differing, f'vendored files differ between the two trees: {differing}'


def test_vendored_invoke_records_an_immutable_pin():
    """The vendored tree names the exact upstream commit it came from.

    A tag can be moved; a commit cannot. This is the same reason every action in these
    workflows is pinned by SHA, and it is what lets `maintain.sync-vendor` be re-run to prove
    the committed tree still matches its source.
    """
    pin = tomllib.loads((REPO_ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['tool']['vendored-invoke']
    assert pin['repository'] == 'schubergphilis/vendored_invoke'
    assert re.fullmatch(r'v\d+\.\d+\.\d+', pin['version']), f'version {pin["version"]!r} is not a release tag'
    assert re.fullmatch(r'[0-9a-f]{40}', pin['commit']), f'commit {pin["commit"]!r} is not a full SHA'


def test_generated_projects_get_the_slim_vendor_tree(generated_project):
    """A generated project carries the same slim tree, not a stale copy of the old one."""
    project, _ = generated_project
    vendor = project / '_CI' / 'lib' / 'vendor'
    packages = {p.name for p in vendor.iterdir() if p.is_dir() and p.name != 'bin'}
    assert packages == {'invoke', 'coloredlogs', 'humanfriendly'}, f'unexpected vendored packages: {packages}'
    assert not [p for p in vendor.rglob('*') if p.suffix in {'.so', '.pyd', '.dylib'}]
