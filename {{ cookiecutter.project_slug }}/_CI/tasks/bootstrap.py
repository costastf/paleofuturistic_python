"""Bootstrap task definitions for initial development environment setup."""

import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from invoke import Collection, Context, Task, task

from .configuration import SENTINEL
from .shared import execute, is_ci, logged


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


def install_pre_commit(context: Context) -> None:
    """Install and activate pre-commit hooks."""
    execute(context, 'uv run pre-commit install')


# Register steps here — add new ones as needed
STEPS: list[BootstrapStep] = [
    BootstrapStep(
        name='pre-commit hooks',
        action=install_pre_commit,
        prompt='Install pre-commit hooks? [y/N] ',
        ci_behavior='skip',
    ),
]


def run_steps(context: Context) -> None:
    """Execute all registered bootstrap steps, respecting CI and TTY context."""
    non_interactive = is_ci() or not sys.stdin.isatty()
    for step in STEPS:
        if non_interactive:
            if step.ci_behavior == 'run':
                print(f'  Running {step.name}...')
                step.action(context)
            else:
                print(f'  Skipping {step.name} (non-interactive mode)')
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
    if SENTINEL.exists() and not force:
        return
    run_steps(context)
    SENTINEL.touch()


namespace = Collection('bootstrap')
namespace.add_task(cast(Task, bootstrap), default=True, name='all')
