"""Stdlib-only readers for the `pyproject.toml` values the tasks need before anything is installed.

`info.base-image` feeds the deps-image build and its content-addressed tag, `info.python-version`
the uv image digest `develop.bump-uv` resolves. Kept outside `_CI/tasks/` because nothing here
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


def python_version(cfg: dict) -> str:
    """Return the minimum Python version `requires-python` declares, e.g. `3.11`.

    Raises:
        KeyError: if `requires-python` is absent or not a `>=` bound.

    """
    requires = cfg['project']['requires-python']
    match = re.search(r'>=\s*(\d+\.\d+)', requires)
    if not match:
        msg = f'cannot parse requires-python: {requires!r}'
        raise KeyError(msg)
    return match.group(1)


def base_image(cfg: dict) -> str:
    """Return the `[tool.docker-versions] base-image` reference `Dockerfile.deps` builds on."""
    return cfg['tool']['docker-versions']['base-image']


DISPATCH = {
    'info.base-image': base_image,
    'info.python-version': python_version,
}


def read(command: str) -> str:
    """Return the value for a full `info.<key>` command.

    Raises:
        KeyError: if the command is unknown or the backing pyproject key is missing.

    """
    if command not in DISPATCH:
        raise KeyError(command)
    return DISPATCH[command](load())
