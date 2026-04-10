"""Test task definitions."""

from typing import cast

from invoke import Collection, Context, Task, task

from .shared import logged, run, run_steps


@task
@logged('test.pytest')
@run('uv run pytest --strict')
def pytest(context: Context) -> None:
    """Run pytest."""


@task
@logged('test')
def test(context: Context) -> None:
    """Run all test steps; reports all failures before exiting."""
    run_steps(pytest)(context)


namespace = Collection('test')
namespace.add_task(cast(Task, test), default=True)
namespace.add_task(cast(Task, pytest))
