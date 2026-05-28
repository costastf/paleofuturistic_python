"""Shared fixtures for the template invariants suite."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Mirror the sys.path layout the workflow.cmd launcher sets up so the test
# suite can import _CI.tasks.* (which pulls vendored libs at module load).
# The vendored libs cross-reference each other via ``lib.vendor.<x>``, so we
# need both ``_CI/`` and ``_CI/lib/vendor/`` on the path.
def find_repo_root() -> Path:
    """Walk up from this file until a directory containing ``_CI/`` is found."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / '_CI').is_dir():
            return candidate
    raise RuntimeError("Could not locate repo root: no '_CI/' found above conftest.py")


REPO_ROOT = find_repo_root()
sys.path.insert(0, str(REPO_ROOT / '_CI' / 'lib' / 'vendor'))
sys.path.insert(0, str(REPO_ROOT / '_CI'))
sys.path.insert(0, str(REPO_ROOT))

from _CI.tasks.configuration import IGNORE_PATTERNS, PROJECT_SLUG, combo_context, matrix_combos


@pytest.fixture(scope='session')
def template_snapshot(tmp_path_factory):
    """Snapshot the parent template into a temp git repo so cruft sees every current file."""
    snapshot = tmp_path_factory.mktemp('template') / 'repo'
    shutil.copytree(REPO_ROOT, snapshot, ignore=IGNORE_PATTERNS)
    for cmd in (
        ['git', 'init', '-b', 'main'],
        ['git', 'add', '-A'],
        ['git', 'add', '-f', '{{ cookiecutter.project_slug }}/_CI/lib/'],
        [
            'git',
            '-c', 'commit.gpgsign=false',
            '-c', 'user.name=ci',
            '-c', 'user.email=ci@localhost',
            'commit',
            '-m', 'snapshot',
            '--author=ci <ci@localhost>',
        ],
    ):
        subprocess.run(cmd, cwd=snapshot, check=True, capture_output=True)
    return snapshot


@pytest.fixture(scope='session', params=matrix_combos(), ids=lambda cell: cell['label'])
def generated_project(request, template_snapshot, tmp_path_factory):
    """Generate the template for one matrix cell. Cached per-cell for the session."""
    cell = request.param
    output_dir = tmp_path_factory.mktemp(cell['label'])
    extra = combo_context(
        git_hosting_service=cell['git_hosting_service'],
        integrate_dependency_track=cell['integrate_dependency_track'],
        integrate_pages=cell['integrate_pages'],
    )
    subprocess.run(
        [
            'uvx',
            'cruft',
            'create',
            '--no-input',
            '--output-dir',
            str(output_dir),
            '--extra-context',
            json.dumps(extra),
            str(template_snapshot),
        ],
        check=True,
        capture_output=True,
    )
    return output_dir / PROJECT_SLUG, cell
