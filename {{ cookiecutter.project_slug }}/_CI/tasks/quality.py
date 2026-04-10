"""Quality task definitions."""

from typing import cast

from invoke import Collection, Context, Task, task

from .shared import logged, run, run_steps


@task
@logged('quality.pyscn.analyze')
@run('uv run pyscn analyze src/')
def pyscn_analyze(context: Context) -> None:
    """Run pyscn comprehensive analysis with HTML report."""


@task
@logged('quality.pyscn.check')
@run('uv run pyscn check src/')
def pyscn_check(context: Context) -> None:
    """Run pyscn CI-friendly quality gate."""


@task
@logged('quality.pyscn')
def pyscn(context: Context) -> None:
    """Run all pyscn steps; reports all failures before exiting."""
    run_steps(pyscn_analyze, pyscn_check)(context)


@task
@logged('quality')
def quality(context: Context) -> None:
    """Run all quality steps; reports all failures before exiting."""
    run_steps(pyscn)(context)


_pyscn_ns = Collection('pyscn')
_pyscn_ns.add_task(cast(Task, pyscn), default=True, name='all')
_pyscn_ns.add_task(cast(Task, pyscn_analyze), name='analyze')
_pyscn_ns.add_task(cast(Task, pyscn_check), name='check')

namespace = Collection('quality')
namespace.add_task(cast(Task, quality), default=True, name='all')
namespace.add_collection(_pyscn_ns)
