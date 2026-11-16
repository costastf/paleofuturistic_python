"""Stdlib-only readers for the `pyproject.toml` values the tasks need before anything is installed.

`base_image()` feeds the deps-image build and its content-addressed tag, `python_version()` the
uv image digest `develop.bump-uv` resolves. Kept outside `_CI/tasks/` because nothing here
imports invoke, so it can be read by code that runs before the environment exists.
"""

import re
import tomllib
from pathlib import Path

ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / '_CI').is_dir())
PYPROJECT = ROOT / 'pyproject.toml'


def load() -> dict:
    """Return the parsed `pyproject.toml`."""
    return tomllib.loads(PYPROJECT.read_text(encoding='utf-8'))


def python_version() -> str:
    """Return the minimum Python version `requires-python` declares, e.g. `3.11`.

    Raises:
        KeyError: if `requires-python` is absent or not a `>=` bound.

    """
    requires = load()['project']['requires-python']
    match = re.search(r'>=\s*(\d+\.\d+)', requires)
    if not match:
        msg = f'cannot parse requires-python: {requires!r}'
        raise KeyError(msg)
    return match.group(1)


def base_image() -> str:
    """Return the `[tool.docker-versions] base-image` reference `Dockerfile.deps` builds on."""
    return load()['tool']['docker-versions']['base-image']
