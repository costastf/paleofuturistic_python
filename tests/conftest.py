"""Shared fixtures for the template invariants suite."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


# Mirror the sys.path layout the workflow.cmd launcher sets up, so the test suite can import
# `_CI.tasks.*`, which imports the vendored invoke at module load: `_CI/lib/vendor/` for the
# bare `invoke` import, and `_CI/` as the launcher has it.
def find_repo_root() -> Path:
    """Walk up from this file until a directory containing ``_CI/`` is found."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / '_CI').is_dir():
            return candidate
    message = "Could not locate repo root: no '_CI/' found above conftest.py"
    raise RuntimeError(message)


REPO_ROOT = find_repo_root()
sys.path.insert(0, str(REPO_ROOT / '_CI' / 'lib' / 'vendor'))
sys.path.insert(0, str(REPO_ROOT / '_CI'))
sys.path.insert(0, str(REPO_ROOT))

# E402: the sys.path wiring above has to run first — this import is what it exists for.
from _CI.tasks.configuration import (  # noqa: E402
    PROJECT_SLUG,
    combo_context,
    copy_template_snapshot,
    generation_env,
    matrix_combos,
)


@pytest.fixture(scope='session')
def template_snapshot(tmp_path_factory):
    """Copy the template into a plain temp dir so copier sees uncommitted changes too.

    Copier copies happily from a non-git local directory, so no git snapshot is needed. Only
    files git would commit are copied; see `copy_template_snapshot`.
    """
    return copy_template_snapshot(tmp_path_factory.mktemp('template') / 'repo')


@pytest.fixture(scope='session')
def generate(template_snapshot):
    """Run copier over the template snapshot: ``generate(destination, data, check=True)``.

    The one copier invocation every test generates through, so they cannot drift in flags or
    environment. Generation is pinned to the committed uv version, so assertions compare
    against a known value rather than whatever uv released this week, and no test resolves a
    release over the network as a side effect.
    """

    def run(destination, data, *, check=True):
        data_file = destination.parent / 'data.json'
        data_file.write_text(json.dumps(data), encoding='utf-8')
        return subprocess.run(
            [
                'uvx',
                'copier',
                'copy',
                '--defaults',
                '--trust',
                '--data-file',
                str(data_file),
                str(template_snapshot),
                str(destination),
            ],
            check=check,
            capture_output=True,
            env={**os.environ, **generation_env()},
        )

    return run


@pytest.fixture(scope='session', params=matrix_combos(), ids=lambda cell: cell['label'])
def generated_project(request, generate, tmp_path_factory):
    """Generate the template for one matrix cell with copier. Cached per-cell for the session."""
    cell = request.param
    # Name the destination after the slug so `project.name` yields the package slug for tests.
    project = tmp_path_factory.mktemp(cell['label']) / PROJECT_SLUG
    generate(
        project, combo_context(git_hosting_service=cell['git_hosting_service'], integrate_pages=cell['integrate_pages'])
    )
    return project, cell


@pytest.fixture
def uv_release():
    """Import `template/_CI/uv_release.py` from source, fresh for each test.

    The same file both this repo and generated projects use, so there is one implementation to
    test rather than two that could drift.
    """
    path = REPO_ROOT / 'template' / '_CI' / 'uv_release.py'
    spec = importlib.util.spec_from_file_location('uv_release_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
