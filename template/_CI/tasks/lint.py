"""Linting task definitions."""

from typing import cast

from invoke import Collection, Context, Task, task

from .configuration import PATHS
from .shared import execute, logged, run_steps


@task
@logged('lint.ruff')
def ruff_lint(context: Context, paths: str = '') -> None:
    """Run ruff linter.

    Args:
        context: Invoke context.
        paths: Space-separated paths to check. Defaults to the project's standard paths.
    """
    execute(context, f'uv run ruff check {paths or PATHS}')


@task
@logged('lint.format')
def format_check(context: Context, paths: str = '') -> None:
    """Report code that is not correctly formatted, without modifying any files.

    Args:
        context: Invoke context.
        paths: Space-separated paths to check. Defaults to the project's standard paths.
    """
    execute(context, f'uv run ruff format --check {paths or PATHS}')


@task
@logged('lint.pylint')
def pylint(context: Context, paths: str = '') -> None:
    """Run pylint.

    Args:
        context: Invoke context.
        paths: Space-separated paths to check. Defaults to the project's standard paths.
    """
    execute(context, f'uv run pylint {paths or PATHS}')


@task
@logged('lint.ty')
def ty(context: Context, paths: str = '') -> None:
    """Run ty type checker.

    Type checking is whole-program: a signature change in one module surfaces as an error in
    its callers, so narrowing the input hides exactly the errors that matter most. The
    pre-commit hook deliberately does not pass changed files here — pass ``paths`` yourself
    only when you want a narrower answer on purpose.

    Args:
        context: Invoke context.
        paths: Space-separated paths to check. Defaults to the project's standard paths.
    """
    execute(context, f'uv run ty check {paths or PATHS}')


@task
@logged('lint.complexipy')
def complexipy(context: Context, paths: str = '') -> None:
    """Run complexipy cognitive complexity checker.

    Args:
        context: Invoke context.
        paths: Space-separated paths to check. Defaults to ``src/``.
    """
    execute(context, f'uv run complexipy {paths or "src/"}')


@task
@logged('lint.commitizen')
def commitizen(context: Context, commit_msg_file: str | None = None) -> None:
    """Lint commit messages using commitizen conventional commits.

    Args:
        context: Invoke context.
        commit_msg_file: Path to a commit message file (used by commit-msg hooks).
            When omitted, checks the last committed message.
    """
    if commit_msg_file:
        execute(context, f'uv run cz check --commit-msg-file {commit_msg_file}')
    elif context.run('git rev-parse HEAD', hide=True, warn=True):
        execute(context, 'uv run cz check --rev-range HEAD')
    else:
        print('No commits yet — skipping commitizen check.')


@task
@logged('lint')
def lint(context: Context) -> None:
    """Run every linting step over the whole project; reports all failures before exiting."""
    run_steps(ruff_lint, format_check, pylint, ty, complexipy, commitizen)(context)


namespace = Collection('lint')
namespace.add_task(cast(Task, lint), default=True, name='all')
namespace.add_task(cast(Task, ruff_lint), name='ruff')
namespace.add_task(cast(Task, format_check), name='format-check')
namespace.add_task(cast(Task, pylint))
namespace.add_task(cast(Task, ty))
namespace.add_task(cast(Task, complexipy))
namespace.add_task(cast(Task, commitizen))
