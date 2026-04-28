"""Shared test fixtures for {{ cookiecutter.project_slug }}."""

from pathlib import Path

import pytest


@pytest.fixture
def project_root() -> Path:
    """Return the project root directory."""
    return next(
        parent for parent in Path(__file__).resolve().parents if (parent / '_CI').is_dir()
    )


@pytest.fixture
def test_data(project_root: Path) -> Path:  # pylint: disable=redefined-outer-name
    """Return the test data directory, creating it if needed."""
    data_dir = project_root / 'tests' / 'data'
    data_dir.mkdir(exist_ok=True)
    return data_dir
