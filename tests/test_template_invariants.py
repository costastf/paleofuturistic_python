"""Per-axis invariants over the cartesian product of copier answer combinations.

Each test below receives one generated project per matrix cell via the
``generated_project`` fixture in ``conftest.py``. Adding a new assertion is one
new ``test_*`` function; adding a new combo axis edits ``matrix_combos()`` in
``_CI/tasks/configuration.py`` and both the pytest suite and the Invoke matrix
runner pick it up automatically.
"""

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
from _CI.tasks.configuration import PROJECT_SLUG


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
    """Every consumer of `git remote get-url origin` routes through `strip_credentials`."""
    project, cell = generated_project
    sbom_py = (project / '_CI' / 'tasks' / 'sbom.py').read_text(encoding='utf-8')
    assert 'strip_credentials' in sbom_py, 'sbom.py does not sanitize the origin URL'
    host_py = (project / '_CI' / 'tasks' / f'{cell["git_hosting_service"]}.py').read_text(encoding='utf-8')
    assert 'strip_credentials' in host_py, 'origin_slug() does not sanitize the origin URL'


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
    assert 'sha256sum uv.lock' in deps_job and 'sha256sum Dockerfile.deps' in deps_job
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


def test_security_audit_runs_in_ci(generated_project):
    """The chosen host's pipeline runs `secure.audit`.

    Without this the `.security-overrides` expiry mechanism gates nothing: pip-audit was
    reachable only as a local command, so a dependency with a known CVE shipped green.
    """
    project, cell = generated_project
    if cell['git_hosting_service'] == 'github':
        pipeline = (project / '.github' / 'workflows' / 'continuous-integration.yaml').read_text(encoding='utf-8')
    else:
        pipeline = (project / '.gitlab-ci.yml').read_text(encoding='utf-8')
    assert 'secure.audit' in pipeline, 'no pipeline job runs secure.audit'


def test_scheduled_security_audit_ships_for_github(generated_project):
    """GitHub projects get a scheduled audit, so expiries come due without a push."""
    project, cell = generated_project
    workflow = project / '.github' / 'workflows' / 'security-audit.yaml'
    if cell['git_hosting_service'] != 'github':
        assert not workflow.exists()
        return
    content = workflow.read_text(encoding='utf-8')
    assert 'schedule:' in content and 'cron:' in content
    assert 'workflow_dispatch:' in content, 'no way to trigger the audit on demand'
    assert 'secure.audit' in content
    config = yaml.safe_load(content)
    # Least privilege: the audit only reads the repo; only the image build may publish.
    assert config['permissions'] == {'contents': 'read'}
    assert config['jobs']['secure']['permissions'] == {'contents': 'read', 'packages': 'read'}


def test_qa_steps_include_the_security_audit():
    """`secure.audit` is in QA_STEPS, so every matrix cell audits its generated project.

    The matrix runner already exports `<PROJECT>_SECURITY_OVERRIDE` for this step; until
    it was listed here that plumbing fed nothing.
    """
    from _CI.tasks.configuration import QA_STEPS

    assert 'secure.audit' in QA_STEPS
    # Fail fast: audit before the slow tox matrix.
    assert QA_STEPS.index('secure.audit') < QA_STEPS.index('test.tox')


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


def test_untracked_suppression_sources_require_an_expiry(generated_project):
    """`--ignore` and the env var must carry an expiry; `.security-overrides` need not.

    Those two leave no trace in the repo, so a permanent entry there could mute a finding
    with no code change to review.
    """
    project, _ = generated_project
    secure_py = (project / '_CI' / 'tasks' / 'secure.py').read_text(encoding='utf-8')
    audit_source = secure_py.split("@logged('secure.audit')", 1)[1].split('\n@task', 1)[0]
    cli = next(line for line in audit_source.splitlines() if "'--ignore'" in line)
    env = next(line for line in audit_source.splitlines() if 'SECURITY_OVERRIDE_ENV' in line and 'parse_' in line)
    assert 'require_expiry=True' in cli, '--ignore does not require an expiry'
    assert 'require_expiry=True' in env, 'the env var does not require an expiry'
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

    The Pages deploy is the deliberate exception: `properdocs gh-deploy` pushes to the
    `gh-pages` branch and needs the credential to survive the checkout.
    """
    project, cell = generated_project
    if cell['git_hosting_service'] != 'github':
        pytest.skip('GitHub-only workflows')
    for name, config in github_workflows(project):
        for job_name, job in config['jobs'].items():
            for step in job.get('steps') or []:
                if not str(step.get('uses', '')).startswith('actions/checkout@'):
                    continue
                persists = (step.get('with') or {}).get('persist-credentials')
                if name == 'pages.yaml':
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
            # may mutate anything. `id-token: write` is exempt everywhere: it mints an
            # OIDC token for PyPI Trusted Publishing and grants no access to repo resources.
            if job_name not in ('build-deps-image', 'deploy'):
                writes = [
                    scope for scope, level in declared.items() if level == 'write' and scope != 'id-token'
                ]
                assert not writes, f'{name}:{job_name} asks for write scopes {writes}'


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

    def __init__(self, stdout_for=None):
        self.commands = []
        self.stdout_for = stdout_for or {}

    def run(self, cmd, **_kwargs):
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
    assert ran[1] == 'cmd.exe /c start "" "\\\\wsl.localhost\\Ubuntu\\home\\me\\site\\index.html"'
    assert executed == []


def test_open_target_degrades_when_wsl_interop_is_disabled(generated_project):
    """A distro with interop off gets a message, not a traceback or a failed task."""
    project, _ = generated_project
    ran, executed = opener(project, 'wsl', interop=False)
    assert ran == [] and executed == []


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
    assert abs((date.today() - stamped).days) <= 1, f'quarantine date {stamped} was not stamped at generation'


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
    assert set(images) == {'base-image'}, f'unused image references reintroduced: {sorted(set(images) - {"base-image"})}'


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


def test_lockfile_agrees_with_the_pinned_uv(generated_project):
    """The locked uv matches `[tool.uv] required-version`.

    They are resolved from the same pyproject, so a mismatch would mean the lockfile was
    generated against different pins than the ones that shipped.
    """
    project, _ = generated_project
    data = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    required = data['tool']['uv']['required-version'].removeprefix('==')
    locked = {p['name']: p['version'] for p in tomllib.loads((project / 'uv.lock').read_text(encoding='utf-8'))['package']}
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


def test_no_commit_stage_hook_rewrites_tracked_files(generated_project):
    """No `pre-commit`-stage hook runs a task that writes README.md or pyproject.toml.

    The `test` aggregator updates the coverage badge and ratchets `fail_under`. Run from a
    commit hook, pre-commit aborted the commit with "files were modified by this hook" —
    after the message was written, for files the author never staged. That is what teaches
    people `--no-verify`, which then disables every hook here at once.
    """
    project, _ = generated_project
    mutating = {'test', 'document', 'build', 'quality.pyscn-analyze', 'test.coverage'}
    for hook in pre_commit_hooks(project):
        if 'pre-commit' not in (hook.get('stages') or ['pre-commit']):
            continue
        invoked = hook['entry'].removeprefix('./workflow.cmd').strip()
        assert invoked not in mutating, f'commit-stage hook {hook["id"]!r} runs {invoked!r}, which rewrites tracked files'


def test_per_file_hooks_check_only_staged_files(generated_project):
    """The per-file tools receive the staged files instead of sweeping the whole project.

    Each wraps the task in `sh -c … --paths="$*"`: pre-commit appends filenames as separate
    arguments, and Invoke would read the second one as another task name, so they have to be
    collapsed into one option value.
    """
    project, _ = generated_project
    hooks = {hook['id']: hook for hook in pre_commit_hooks(project)}
    for hook_id in ('format', 'ruff', 'pylint', 'complexipy'):
        hook = hooks[hook_id]
        assert hook.get('pass_filenames') is True, f'{hook_id} does not receive the staged files'
        assert '--paths="$*"' in hook['entry'], f'{hook_id} does not collapse filenames into --paths'


def test_whole_program_checks_are_not_scoped_to_staged_files(generated_project):
    """ty and pyscn keep seeing the whole project, because a per-file view answers wrongly.

    ty: a changed signature fails in the *callers*, which a narrowed run never looks at.
    pyscn: dead code and duplicate blocks are relationships between files.
    """
    project, _ = generated_project
    hooks = {hook['id']: hook for hook in pre_commit_hooks(project)}
    for hook_id in ('ty', 'pyscn'):
        hook = hooks[hook_id]
        assert hook.get('pass_filenames') is False, f'{hook_id} was narrowed to staged files'
        assert '--paths' not in hook['entry'], f'{hook_id} was narrowed to staged files'


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


def test_suite_runs_on_pre_push(generated_project):
    """The test suite gates pushes, not commits, and uses the non-mutating task."""
    project, _ = generated_project
    hooks = {hook['id']: hook for hook in pre_commit_hooks(project)}
    test_hook = hooks['test']
    assert test_hook['stages'] == ['pre-push'], f'test hook stages are {test_hook["stages"]}'
    assert test_hook['entry'].endswith('test.pytest'), f'test hook runs {test_hook["entry"]!r}'
    installed = yaml.safe_load((project / '.pre-commit-config.yaml').read_text(encoding='utf-8'))
    assert 'pre-push' in installed['default_install_hook_types'], 'pre-push hooks would never be installed'


def test_pre_push_gate_enforces_the_same_coverage_floor(generated_project):
    """`test.pytest` and the `test` aggregator share one pytest invocation, so the floor holds.

    Coverage is enforced by pytest-cov from `[tool.coverage.report] fail_under`, driven by the
    `--cov` flags in `addopts`. Moving the hook to `test.pytest` therefore drops the badge and
    ratchet writes without weakening the gate.
    """
    project, _ = generated_project
    data = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    assert '--cov' in data['tool']['pytest']['ini_options']['addopts']
    assert 'fail_under' in data['tool']['coverage']['report']
    test_py = (project / '_CI' / 'tasks' / 'test.py').read_text(encoding='utf-8')
    aggregator = test_py.split("@logged('test')", 1)[1]
    assert 'run_steps(pytest)' in aggregator, 'the aggregator no longer delegates to the same pytest task'


def test_local_task_module_ships_with_a_namespace(generated_project):
    """`_CI/tasks/local.py` ships and exposes a `local` collection ready to add tasks to."""
    project, _ = generated_project
    local = project / '_CI' / 'tasks' / 'local.py'
    assert local.is_file(), 'no project-owned task module ships'
    source = local.read_text(encoding='utf-8')
    assert "Collection('local')" in source, 'local.py defines no namespace for __init__ to pick up'


def test_local_task_module_is_protected_from_updates(generated_project):
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
    assert 'LOCAL_MODULE' in init and 'is_file()' in init, 'local.py is not conditionally discovered'
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
    doc = (project / 'docs' / 'developer' / 'explanation' / 'the-ci-tasks-architecture.md').read_text(
        encoding='utf-8'
    )
    assert '_CI.invoke' not in doc, 'the doc still cites a nonexistent _CI.invoke module'
    # Every non-shebang line of the real launcher must appear verbatim in the doc.
    for line in (line.strip() for line in launcher.splitlines()):
        if not line or line.startswith('#!'):
            continue
        assert line in doc, f'launcher line not documented: {line!r}'
    # And the dispatch mechanism the two interpreters rely on is explained, not just shown.
    assert 'exec' in doc and 'label' in doc, 'the doc shows the launcher without explaining how it dispatches'


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


SHIPPED_RATIONALE_PAGES = {
    'docs/maintaining/explanation/design-principles.md': 'template/docs/developer/explanation/design-principles.md',
    'docs/maintaining/explanation/the-ci-tasks-architecture.md': 'template/docs/developer/explanation/the-ci-tasks-architecture.md',
    'docs/using/explanation/how-uv-is-used.md': 'template/docs/developer/explanation/how-uv-is-used.md',
    'docs/using/explanation/sbom-and-security-model.md': 'template/docs/developer/explanation/sbom-and-security-model.md.jinja',
    'docs/using/explanation/testing-strategy.md': 'template/docs/developer/explanation/testing-strategy.md',
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
    assert shipped.startswith('<!-- canonical:'), f'{SHIPPED_RATIONALE_PAGES[canonical_path]} lacks the canonical marker'
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
    )
    if license_choice == 'None':
        assert not (project / 'LICENSE').exists()
    else:
        assert (project / 'LICENSE').exists()
