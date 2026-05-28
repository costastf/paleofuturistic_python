"""Per-axis invariants over the cartesian product of cookiecutter combinations.

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

import pytest

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


@pytest.mark.parametrize('license_choice', ['Apache-2.0', 'MIT', 'BSD-3-Clause', 'None'])
def test_license_file_matches_choice(template_snapshot, tmp_path_factory, license_choice):
    """Each license choice produces (or skips) a LICENSE file at the project root."""
    output_dir = tmp_path_factory.mktemp(f'license-{license_choice}')
    subprocess.run(
        [
            'uvx',
            'cruft',
            'create',
            '--no-input',
            '--output-dir',
            str(output_dir),
            '--extra-context',
            json.dumps({'license': license_choice}),
            str(template_snapshot),
        ],
        check=True,
        capture_output=True,
    )
    project = output_dir / PROJECT_SLUG
    if license_choice == 'None':
        assert not (project / 'LICENSE').exists()
    else:
        assert (project / 'LICENSE').exists()
