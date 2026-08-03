"""Per-axis invariants over the cartesian product of copier answer combinations.

Each test below receives one generated project per matrix cell via the
``generated_project`` fixture in ``conftest.py``. Adding a new assertion is one
new ``test_*`` function; adding a new combo axis edits ``matrix_combos()`` in
``_CI/tasks/configuration.py`` and both the pytest suite and the Invoke matrix
runner pick it up automatically.
"""

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


DEVELOPER_NAV_START = '# developer-docs:start'
DEVELOPER_NAV_END = '# developer-docs:end'


def strip_developer_nav(config_text):
    """Mirror ``properdocs_config_without_developer_docs()`` from the generated document task.

    Kept in lockstep with ``template/_CI/tasks/document.py.jinja``: the sentinel slice is the
    fragile part of the ``--no-developer-docs`` flag, so the invariants below exercise it here
    rather than bootstrapping a generated project's virtualenv to import the real helper.
    """
    lines = config_text.splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if DEVELOPER_NAV_START in line)
    end = next(i for i, line in enumerate(lines) if DEVELOPER_NAV_END in line)
    return ''.join(lines[:start] + lines[end + 1 :]) + '\nexclude_docs: |\n  developer/*\n'


def test_developer_nav_markers_bracket_the_developer_block(generated_project):
    """The `developer-docs` sentinels ship in order and fence exactly the Developer nav section."""
    project, _ = generated_project
    lines = (project / 'properdocs.yml').read_text(encoding='utf-8').splitlines()
    starts = [i for i, line in enumerate(lines) if DEVELOPER_NAV_START in line]
    ends = [i for i, line in enumerate(lines) if DEVELOPER_NAV_END in line]
    assert len(starts) == 1, f'expected exactly one {DEVELOPER_NAV_START} marker, found {len(starts)}'
    assert len(ends) == 1, f'expected exactly one {DEVELOPER_NAV_END} marker, found {len(ends)}'
    assert starts[0] < ends[0], 'developer-docs markers are out of order'
    fenced = lines[starts[0] + 1 : ends[0]]
    assert fenced[0].strip() == '- Developer:', 'start marker does not immediately precede the Developer nav entry'
    outside = lines[: starts[0]] + lines[ends[0] + 1 :]
    assert not [line for line in outside if 'developer/' in line], 'developer/ pages referenced outside the markers'


def test_developer_docs_can_be_excluded_from_the_build(generated_project):
    """Stripping the sentinel block yields a valid config with no Developer nav and every page resolving.

    This is the config the `--no-developer-docs` flag pipes into `properdocs … -f -`.
    """
    project, _ = generated_project
    original = (project / 'properdocs.yml').read_text(encoding='utf-8')
    config = yaml.safe_load(strip_developer_nav(original))
    pages = collect_nav_pages(config['nav'])
    assert pages, 'stripped nav is empty'
    assert not [page for page in pages if page.startswith('developer/')], 'Developer pages survived the strip'
    assert 'Developer' not in {key for entry in config['nav'] if isinstance(entry, dict) for key in entry}
    assert config['exclude_docs'].strip() == 'developer/*'
    missing = [page for page in pages if not (project / 'docs' / page).is_file()]
    assert not missing, f'nav entries without a file: {missing}'
    # The default build must still see the Developer section, so the strip has to be opt-in only.
    assert 'developer/index.md' in collect_nav_pages(yaml.safe_load(original)['nav'])


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
