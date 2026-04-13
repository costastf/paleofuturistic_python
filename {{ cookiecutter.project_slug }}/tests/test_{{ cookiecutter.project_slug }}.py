"""Smoke tests for {{ cookiecutter.project_slug }}."""

from {{ cookiecutter.project_slug }} import hello


def test_sanity() -> None:
    """Sanity check."""
    assert True


def test_integration() -> None:
    """Integration test for hello function."""
    assert hello() == 'Hello you from {{ cookiecutter.project_slug }}!'
