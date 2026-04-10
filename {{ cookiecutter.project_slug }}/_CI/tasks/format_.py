"""Formatting task definitions."""

from typing import cast

from invoke import Collection, Context, Task, task

from . import _PATHS, _logged, _run, _run_steps


@task
@_logged('format.ruff')
@_run(f'uv run ruff format --diff {_PATHS}')
def ruff_format(context: Context) -> None:
    """Check code formatting with ruff."""


@task
@_logged('format')
def format_(context: Context) -> None:
    """Run all formatting steps; reports all failures before exiting."""
    _run_steps(ruff_format)(context)


namespace = Collection('format')
namespace.add_task(cast(Task, format_), default=True)
namespace.add_task(cast(Task, ruff_format), name='ruff')
