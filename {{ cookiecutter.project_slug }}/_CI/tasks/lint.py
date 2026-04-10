"""Linting task definitions."""

from typing import cast

from invoke import Collection, Context, Task, task

from . import _PATHS, _logged, _run, _run_steps


@task
@_logged('lint.ruff')
@_run(f'uv run ruff check {_PATHS}')
def ruff_lint(context: Context) -> None:
    """Run ruff linter."""


@task
@_logged('lint.pylint')
@_run(f'uv run pylint {_PATHS}')
def pylint(context: Context) -> None:
    """Run pylint."""


@task
@_logged('lint.ty')
@_run(f'uv run ty check {_PATHS}')
def ty(context: Context) -> None:
    """Run ty type checker."""


@task
@_logged('lint.complexipy')
@_run('uv run complexipy src/')
def complexipy(context: Context) -> None:
    """Run complexipy cognitive complexity checker."""


@task
@_logged('lint')
def lint(context: Context) -> None:
    """Run all linting steps; reports all failures before exiting."""
    _run_steps(ruff_lint, pylint, ty, complexipy)(context)


namespace = Collection('lint')
namespace.add_task(cast(Task, lint), default=True)
namespace.add_task(cast(Task, ruff_lint), name='ruff')
namespace.add_task(cast(Task, pylint))
namespace.add_task(cast(Task, ty))
namespace.add_task(cast(Task, complexipy))
