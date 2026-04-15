"""Test task definitions."""

from typing import cast

from invoke import Collection, Context, Task, task

from .shared import execute, logged, open_command, run, run_steps


@task
@logged('test.pytest')
@run('uv run pytest')
def pytest(context: Context) -> None:
    """Run pytest."""


@task
@logged('test.coverage')
@run('uv run coverage report')
def coverage(context: Context) -> None:
    """Show test coverage report in terminal."""


@task
@logged('test.view')
def view(context: Context) -> None:
    """Open HTML test report in browser."""
    execute(context, f'{open_command()} reports/tests.html')


@task
@logged('test')
def test(context: Context) -> None:
    """Run all test steps; reports all failures before exiting."""
    run_steps(pytest)(context)


namespace = Collection('test')
namespace.add_task(cast(Task, test), default=True, name='all')
namespace.add_task(cast(Task, pytest))
namespace.add_task(cast(Task, coverage))
namespace.add_task(cast(Task, view))
