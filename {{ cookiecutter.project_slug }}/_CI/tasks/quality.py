"""Quality task definitions."""

from pathlib import Path
from typing import cast

from invoke import Collection, Context, Task, task

from .shared import exec_, logged, run, run_steps

_PYSCN_REPORTS_DIR = Path('.pyscn/reports')


def _latest_pyscn_report() -> Path:
    """Return the most recently created pyscn HTML report."""
    return max(_PYSCN_REPORTS_DIR.glob('analyze_*.html'), key=lambda p: p.stat().st_mtime)


@task
@logged('quality.pyscn-analyze')
def pyscn_analyze(context: Context) -> None:
    """Run pyscn comprehensive analysis with HTML report."""
    exec_(context, 'uv run pyscn analyze src/')
    exec_(context, f'open {_latest_pyscn_report()}')


@task
@logged('quality.pyscn-check')
@run('uv run pyscn check src/')
def pyscn_check(context: Context) -> None:
    """Run pyscn CI-friendly quality gate."""


@logged('quality.pyscn-analyze')
def _pyscn_analyze_only(context: Context) -> None:
    """Run pyscn analyze without opening the report."""
    exec_(context, 'uv run pyscn analyze src/')


@task
@logged('quality.pyscn')
def pyscn(context: Context) -> None:
    """Run all pyscn steps; reports all failures before exiting."""
    run_steps(_pyscn_analyze_only, pyscn_check)(context)


@task
@logged('quality')
def quality(context: Context) -> None:
    """Run all quality steps; reports all failures before exiting."""
    run_steps(pyscn)(context)


namespace = Collection('quality')
namespace.add_task(cast(Task, quality), default=True, name='all')
namespace.add_task(cast(Task, pyscn))
namespace.add_task(cast(Task, pyscn_analyze), name='pyscn-analyze')
namespace.add_task(cast(Task, pyscn_check), name='pyscn-check')
