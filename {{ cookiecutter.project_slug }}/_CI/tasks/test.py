"""Test task definitions."""

import json
import re
from pathlib import Path
from typing import cast

from invoke import Collection, Context, Task, task

from .shared import execute, logged, open_command, run, run_steps

_COVERAGE_REPORT = Path('reports/coverage.json')


def _coverage_color(pct: float) -> str:
    """Return a badge color for a coverage percentage."""
    if pct >= 90:
        return 'brightgreen'
    if pct >= 80:
        return 'green'
    if pct >= 70:
        return 'yellow'
    if pct >= 60:
        return 'orange'
    return 'red'


def _update_coverage_badge() -> None:
    """Update the coverage badge in README.md from the latest coverage report."""
    readme = Path('README.md')
    if not readme.exists() or not _COVERAGE_REPORT.exists():
        return
    try:
        report = json.loads(_COVERAGE_REPORT.read_text(encoding='utf-8'))
        pct = round(report['totals']['percent_covered'])
    except (ValueError, KeyError):
        return
    color = _coverage_color(pct)
    content = readme.read_text(encoding='utf-8')
    updated = re.sub(
        r'(\[!\[Coverage\]\(https://img\.shields\.io/badge/coverage-)[^)]+(\))',
        rf'\g<1>{pct}%25-{color}\2',
        content,
    )
    if updated != content:
        readme.write_text(updated, encoding='utf-8')
        print(f'Updated coverage badge to {pct}%.')


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
    """Run tests and open HTML test and coverage reports in browser."""
    test(context)
    execute(context, f'{open_command()} reports/tests.html')
    execute(context, f'{open_command()} reports/coverage/index.html')


@task
@logged('test')
def test(context: Context) -> None:
    """Run all test steps; reports all failures before exiting."""
    run_steps(pytest)(context)
    _update_coverage_badge()


namespace = Collection('test')
namespace.add_task(cast(Task, test), default=True, name='all')
namespace.add_task(cast(Task, pytest))
namespace.add_task(cast(Task, coverage))
namespace.add_task(cast(Task, view))
