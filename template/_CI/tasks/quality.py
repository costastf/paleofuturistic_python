"""Quality task definitions."""

import json
from pathlib import Path
from typing import cast

from invoke import Collection, Context, Task, task

from .configuration import PYSCN_REPORTS_DIR
from .shared import apply_badge, execute, is_ci, logged, note, open_target, run, run_steps

GRADE_COLORS = {'A': 'brightgreen', 'B': 'green', 'C': 'yellow', 'D': 'orange', 'F': 'red'}
BADGE_PATTERN = r'(\[!\[pyscn quality\]\(https://img\.shields\.io/badge/pyscn-)[^)]+(\))'


def latest_pyscn_report() -> Path:
    """Return the most recently created pyscn HTML report."""
    return max(PYSCN_REPORTS_DIR.glob('analyze_*.html'), key=lambda p: p.stat().st_mtime)


def latest_pyscn_json() -> Path:
    """Return the most recently created pyscn JSON report."""
    return max(PYSCN_REPORTS_DIR.glob('analyze_*.json'), key=lambda p: p.stat().st_mtime)


def update_pyscn_badge(*, write: bool = True) -> str | None:
    """Bring the README's pyscn badge in line with the grade in the latest report.

    The grade comes from ``pyscn analyze --json``, not from ``pyscn check``: the gate reports
    pass or fail and writes no report at all, so it has no grade to offer. Anything that wants
    this badge current has to run the analysis first — which is why ``preflight`` does, and why
    a missing report is reported here rather than passed over in silence.

    Args:
        write: Update README.md. When False, report what would change and touch nothing.

    Returns:
        None when the badge is already right, else a one-line reason it is not.
    """
    try:
        report = json.loads(latest_pyscn_json().read_text(encoding='utf-8'))
        grade = report['summary']['grade']
    except (ValueError, KeyError, FileNotFoundError):
        return f'no pyscn report in {PYSCN_REPORTS_DIR}/ — run ./workflow.cmd quality.pyscn-analyze'
    color = GRADE_COLORS.get(grade, 'lightgrey')
    return apply_badge(
        Path('README.md'),
        BADGE_PATTERN,
        rf'\g<1>{grade}-{color}\2',
        label='pyscn badge',
        detail=f'grade {grade}',
        write=write,
    )


@task
@logged('quality.pyscn-analyze')
def pyscn_analyze(context: Context) -> None:
    """Run pyscn comprehensive analysis with HTML report."""
    execute(context, 'uv run pyscn analyze src/')
    execute(context, 'uv run pyscn analyze --json src/')
    note(update_pyscn_badge())
    if not is_ci():
        open_target(context, str(latest_pyscn_report()))


@task
@logged('quality.pyscn-check')
@run('uv run pyscn check src/')
def pyscn_check(context: Context) -> None:
    """Run pyscn CI-friendly quality gate."""


@logged('quality.pyscn-analyze')
def pyscn_analyze_only(context: Context, *, badge: bool = True) -> None:
    """Run pyscn analyze without opening the report.

    Args:
        context: Invoke context.
        badge: Update the README badge from the fresh report. ``preflight`` passes False:
            it owns every write to a tracked file, so that all of them can be verified
            together in check mode instead of one task at a time.
    """
    execute(context, 'uv run pyscn analyze src/')
    execute(context, 'uv run pyscn analyze --json src/')
    if badge:
        note(update_pyscn_badge())


@task
@logged('quality.pyscn')
def pyscn(context: Context) -> None:
    """Run all pyscn steps; reports all failures before exiting."""
    run_steps(pyscn_analyze_only, pyscn_check)(context)


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
