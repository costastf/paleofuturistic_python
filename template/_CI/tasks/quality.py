"""Quality task definitions."""

import json
from pathlib import Path
from typing import cast

from invoke import Collection, Context, Task, task

from .configuration import PYSCN_REPORTS_DIR
from .shared import apply_badge, execute, is_ci, logged, note, open_target, run, run_steps

GRADE_COLORS = {'A': 'brightgreen', 'B': 'green', 'C': 'yellow', 'D': 'orange', 'F': 'red'}
# `--no-open` because pyscn opens the HTML report in a browser itself as soon as it writes
# one. Left to its own devices it opened the report twice from `pyscn-analyze` — once by
# itself and once from the deliberate `open_target` below — and opened it at all from
# `pyscn_analyze_only`, whose whole point is not to. Which report gets opened, and whether
# opening one is wanted here at all, is this module's decision to make; `is_ci()` is part of
# it, and a tool reaching for a browser on a CI runner is not.
ANALYZE_HTML = 'uv run pyscn analyze --html --no-open src/'
ANALYZE_JSON = 'uv run pyscn analyze --json src/'
# Deliberately *not* `--quiet`, despite its help promising "Suppress output unless issues
# found". It suppresses the issues too: with it, a failure reports only "Found 1 quality
# issue(s)", while without it the same run names the finding —
# `src/pkg/mod.py:21:1: tangled is too complex (16 > 15)`. The two lines it prints on a passing
# run are the price of that one line on a failing one.
CHECK = 'uv run pyscn check src/'
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
    """Run pyscn comprehensive analysis with HTML report, and open it."""
    execute(context, ANALYZE_HTML)
    execute(context, ANALYZE_JSON)
    note(update_pyscn_badge())
    if not is_ci():
        open_target(context, str(latest_pyscn_report()))


@task
@logged('quality.pyscn-check')
@run(CHECK)
def pyscn_check(context: Context) -> None:
    """Run pyscn's CI-friendly quality gate.

    Not the same judgment as the badge, which is worth knowing. This applies hard per-dimension
    thresholds — a function over the complexity limit, critical dead code, a dependency cycle —
    and fails. `analyze` computes a lenient aggregate health score and never fails: a module
    with a 16-branch function still grades A while this rejects it. So the two invocations in
    `preflight` are not a duplicate; one produces the grade the badge shows, the other decides
    whether the tree passes.
    """


@logged('quality.pyscn-analyze')
def pyscn_analyze_only(context: Context) -> None:
    """Run pyscn analyze without opening the report.

    Two analyses, because pyscn refuses more than one output format per run — ``--html
    --json`` together fails with "only one output format flag can be specified". So each
    format costs its own full analysis, and each prints its own summary table. That is the
    price of wanting both reports; ``pyscn_json_report`` is the path for callers that only
    need one.
    """
    execute(context, ANALYZE_HTML)
    execute(context, ANALYZE_JSON)
    note(update_pyscn_badge())


@logged('quality.pyscn-analyze')
def pyscn_json_report(context: Context) -> None:
    """Produce just the JSON report, which is all the badge is derived from.

    The gate's path. An HTML report exists to be looked at, and nothing in `preflight` or a
    hook looks at one — so paying for a second full analysis to produce it, and printing a
    second identical summary table, bought nothing. `quality.pyscn-analyze` is where the
    HTML report is wanted, because that task opens it.

    The badge is deliberately not written here: `preflight` owns every write to a tracked
    file so that check mode can verify all of them together.
    """
    execute(context, ANALYZE_JSON)


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
