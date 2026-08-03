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
import subprocess
import tomllib
from pathlib import Path

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
