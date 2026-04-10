"""Linting task definitions."""

from typing import cast

from invoke import Collection, Context, Task, task

from .shared import PATHS, logged, run, run_steps


@task
@logged('lint.ruff')
@run(f'uv run ruff check {PATHS}')
def ruff_lint(context: Context) -> None:
    """Run ruff linter."""


@task
@logged('lint.pylint')
@run(f'uv run pylint {PATHS}')
def pylint(context: Context) -> None:
    """Run pylint."""


@task
@logged('lint.ty')
@run(f'uv run ty check {PATHS}')
def ty(context: Context) -> None:
    """Run ty type checker."""


@task
@logged('lint.complexipy')
@run('uv run complexipy src/')
def complexipy(context: Context) -> None:
    """Run complexipy cognitive complexity checker."""


@task
@logged('lint')
def lint(context: Context) -> None:
    """Run all linting steps; reports all failures before exiting."""
    run_steps(ruff_lint, pylint, ty, complexipy)(context)


namespace = Collection('lint')
namespace.add_task(cast(Task, lint), default=True, name='all')
namespace.add_task(cast(Task, ruff_lint), name='ruff')
namespace.add_task(cast(Task, pylint))
namespace.add_task(cast(Task, ty))
namespace.add_task(cast(Task, complexipy))
