"""Quality task definitions."""

from typing import cast

from invoke import Collection, Context, Task, task

from .shared import logged, run, run_steps


@task
@logged('quality.pyscn')
@run('uv run pyscn src/')
def pyscn(context: Context) -> None:
    """Run pyscn source code analysis."""


@task
@logged('quality')
def quality(context: Context) -> None:
    """Run all quality steps; reports all failures before exiting."""
    run_steps(pyscn)(context)


namespace = Collection('quality')
namespace.add_task(cast(Task, quality), default=True, name='all')
namespace.add_task(cast(Task, pyscn))
