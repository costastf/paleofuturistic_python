"""Formatting task definitions."""

from functools import partial
from typing import cast

from invoke import Collection, Context, Task, task

from .configuration import PATHS
from .shared import execute, logged, run_steps


@task
@logged('format.ruff')
def ruff_format(context: Context, paths: str = '') -> None:
    """Format code and sort imports with ruff.

    Args:
        context: Invoke context.
        paths: Space-separated paths to format. Defaults to the project's standard paths.
    """
    targets = paths or PATHS
    execute(context, f'uv run ruff check --select I --fix {targets}')
    execute(context, f'uv run ruff format {targets}')


@task
@logged('format')
def format_(context: Context, paths: str = '') -> None:
    """Run all formatting steps; reports all failures before exiting.

    Args:
        context: Invoke context.
        paths: Space-separated paths to format. Defaults to the project's standard paths.
    """
    run_steps(partial(ruff_format, paths=paths))(context)


namespace = Collection('format')
namespace.add_task(cast(Task, format_), default=True, name='all')
namespace.add_task(cast(Task, ruff_format), name='ruff')
