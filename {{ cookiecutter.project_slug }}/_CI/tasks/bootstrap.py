"""Bootstrap task definitions for initial development environment setup."""

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from invoke import Collection, Context, Task, task

from .shared import exec_, logged

_SENTINEL = Path('.bootstrapped')


def _is_ci() -> bool:
    """Detect CI environment (GitHub Actions, GitLab CI, etc.)."""
    return os.environ.get('CI', '').lower() == 'true'


@dataclass
class BootstrapStep:
    """A single bootstrap step with CI-aware execution behavior.

    Attributes:
        name: Display name for the step.
        action: Callable that performs the step.
        prompt: Question to ask locally. If empty, the step always runs.
        ci_behavior: What to do in CI — 'run' (auto-execute) or 'skip' (silently skip).
    """

    name: str
    action: Callable[[Context], None]
    prompt: str = ''
    ci_behavior: str = 'skip'


def _install_pre_commit(context: Context) -> None:
    exec_(context, 'uv run pre-commit install')


# Register steps here — add new ones as needed
_STEPS: list[BootstrapStep] = [
    BootstrapStep(
        name='pre-commit hooks',
        action=_install_pre_commit,
        prompt='Install pre-commit hooks? [y/N] ',
        ci_behavior='skip',
    ),
]


def _run_steps(context: Context) -> None:
    ci = _is_ci()
    for step in _STEPS:
        if ci:
            if step.ci_behavior == 'run':
                print(f'  Running {step.name}...')
                step.action(context)
            else:
                print(f'  Skipping {step.name} (CI mode)')
        elif step.prompt:
            if input(step.prompt).strip().lower() in ('y', 'yes'):
                step.action(context)
        else:
            step.action(context)


@task
@logged('bootstrap')
def bootstrap(context: Context, force: bool = False) -> None:
    """Set up the development environment (runs once).

    Args:
        context: Invoke context.
        force: Force re-bootstrap even if already done.
    """
    if _SENTINEL.exists() and not force:
        return
    _run_steps(context)
    _SENTINEL.touch()


namespace = Collection('bootstrap')
namespace.add_task(cast(Task, bootstrap), default=True, name='all')
