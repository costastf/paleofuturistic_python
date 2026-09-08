"""Formatting task definitions."""

from functools import partial
from typing import cast

from invoke import Collection, Context, Task, task

from .configuration import CODE_FILES, PATHS
from .shared import execute, logged, run_steps, staged_files


@task
@logged('format.ruff')
def ruff_format(context: Context, paths: str = '') -> None:
    """Format code and sort imports with ruff.

    Args:
        context: Invoke context.
        paths: Space-separated paths to format. Defaults to the project's standard paths.
    """
    targets = paths or PATHS
    execute(context, f'uv run ruff check --select I --fix {targets}')
    execute(context, f'uv run ruff format {targets}')


@task
@logged('format')
def format_(context: Context, paths: str = '', staged: bool = False) -> None:
    """Run all formatting steps; reports all failures before exiting.

    Args:
        context: Invoke context.
        paths: Space-separated paths to format. Defaults to the project's standard paths.
        staged: Format the Python files staged for commit. For fixing what the commit hook just
            complained about without reformatting files you never opened — the whole-tree
            default would sweep those into the same commit.
    """
    if staged and paths:
        print('--staged and --paths both say what to format. Pass one.')
        raise SystemExit(1)
    if staged:
        # `CODE_FILES`, the same pattern the gate's per-file steps use, so the formatter's
        # domain and the checks' domain cannot drift: a staged `docs/generate.py` is not
        # something bare `format` touches either. That also excludes Markdown, which ruff
        # refuses outright ("Markdown formatting is experimental"). `staged_files` has already
        # dropped what git no longer has a file for.
        paths = ' '.join(path for path in staged_files(context).split() if CODE_FILES.match(path))
        if not paths:
            print('No staged Python files, so nothing to format.')
            return
    run_steps(partial(ruff_format, paths=paths))(context)


namespace = Collection('format')
namespace.add_task(cast(Task, format_), default=True, name='all')
namespace.add_task(cast(Task, ruff_format), name='ruff')
