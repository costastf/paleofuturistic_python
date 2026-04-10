"""Test task definitions."""

from typing import cast

from invoke import Collection, Context, Task, task

from . import _logged, _run, _run_steps


@task
@_logged('test.pytest')
@_run('uv run pytest --strict')
def pytest(context: Context) -> None:
    """Run pytest."""


@task
@_logged('test')
def test(context: Context) -> None:
    """Run all test steps; reports all failures before exiting."""
    _run_steps(pytest)(context)


namespace = Collection('test')
namespace.add_task(cast(Task, test), default=True)
namespace.add_task(cast(Task, pytest))
