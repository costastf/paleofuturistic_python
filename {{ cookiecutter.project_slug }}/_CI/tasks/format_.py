"""Formatting task definitions."""

from typing import cast

from invoke import Collection, Context, Task, task

from .shared import PATHS, logged, run, run_steps


@task
@logged('format.ruff')
@run(f'uv run ruff format --diff {PATHS}')
def ruff_format(context: Context) -> None:
    """Check code formatting with ruff."""


@task
@logged('format')
def format_(context: Context) -> None:
    """Run all formatting steps; reports all failures before exiting."""
    run_steps(ruff_format)(context)


namespace = Collection('format')
namespace.add_task(cast(Task, format_), default=True, name='format')
namespace.add_task(cast(Task, ruff_format), name='ruff')
