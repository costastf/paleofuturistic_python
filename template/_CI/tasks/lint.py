"""Linting task definitions."""

import os
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
    """Run pylint across four workers.

    The slowest step of the gate on a scaffold: astroid follows the import graph behind
    `_CI/tasks/`, which is most of the cost and grows with the workflow rather than with your
    code. Four workers cut it from 10.4s to 4.7s on a sixteen-core machine; `-j 0` sizes the
    pool to the machine and came out slower at 5.7s, the same over-subscription `-n auto` shows
    in pytest.

    Args:
        context: Invoke context.
        paths: Space-separated paths to check. Defaults to the project's standard paths.
    """
    execute(context, f'uv run pylint -j 4 {paths or PATHS}')


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


def resolves(context: Context, revision: str) -> bool:
    """Report whether git can resolve ``revision`` in this clone."""
    result = context.run(f'git rev-parse --verify --quiet {revision}', hide=True, warn=True)
    return bool(result and not result.failed)


def unpushed_range(context: Context) -> str | None:
    """Return a commit range to check, or None when the repository holds no commit at all.

    Bounded on purpose. `--rev-range HEAD` reads every reachable commit, so one message that
    predates the convention — a squashed import, history from before this template was applied,
    a `--no-verify` from last year — fails every run from then on, with no way past it but
    `SKIP=preflight`, which drops the whole gate. And it is unfixable by design: rewriting
    published history is worse than the lint it satisfies.

    Candidates in order of how much they know. pre-commit exports
    `PRE_COMMIT_FROM_REF`/`PRE_COMMIT_TO_REF` to pre-push hooks straight from what git handed
    it, which is the push itself rather than an inference about it — right even when the branch
    tracks nothing or pushes somewhere other than its upstream. Then the tracking branch, then
    the remote's default branch.

    An empty candidate falls through to the next rather than ending the search, and the last
    resort is the tip commit. That matters because of where the empty case comes from:
    `actions/checkout` fetches one commit and runs `checkout -B main refs/remotes/origin/main`,
    so in CI the branch *does* track `origin/main` and `origin/main` *is* `HEAD` — the range is
    empty on every push. Returning None there would have the pipeline validate nothing at all,
    on the one run that can catch what the hook cannot: a `--no-verify` commit, or a clone with
    no hooks installed.

    So the tip is always examined by something. Locally that is the commit you just made; in CI
    it is the commit that arrived. A bad message already pushed does keep failing until another
    commit lands on top — bounded to one commit rather than to all of history, which is the
    property that matters.
    """
    if not resolves(context, 'HEAD'):
        return None
    from_ref, to_ref = os.environ.get('PRE_COMMIT_FROM_REF', ''), os.environ.get('PRE_COMMIT_TO_REF', '')
    candidates = []
    if from_ref and to_ref and resolves(context, from_ref) and resolves(context, to_ref):
        candidates.append(f'{from_ref}..{to_ref}')
    candidates.extend(f'{base}..HEAD' for base in ('@{upstream}', 'origin/HEAD') if resolves(context, base))
    for candidate in candidates:
        counted = context.run(f'git rev-list --count {candidate}', hide=True, warn=True)
        if counted is not None and not counted.failed and counted.stdout.strip() not in ('', '0'):
            return candidate
    # The tip alone. `HEAD` is the form for a root commit, where `HEAD~1` does not exist — and
    # a shallow graft is that same shape, its tip having no parent in the clone.
    return 'HEAD~1..HEAD' if resolves(context, 'HEAD^') else 'HEAD'


@task
@logged('lint.commitizen')
def commitizen(context: Context, commit_msg_file: str | None = None) -> None:
    """Lint commit messages using commitizen conventional commits.

    `cz bump` derives the version and the changelog from these messages, so their format is a
    property of the history rather than of any file. The commit-msg hook catches a bad message
    as it is written; a gate run catches one that arrived any other way — an unhooked clone, or
    `--no-verify`.

    Args:
        context: Invoke context.
        commit_msg_file: Path to a commit message file (used by commit-msg hooks).
            When omitted, checks the commits this push would add — see `unpushed_range`.
    """
    if commit_msg_file:
        execute(context, f'uv run cz check --commit-msg-file {commit_msg_file}')
        return
    revision_range = unpushed_range(context)
    if revision_range is None:
        print('No commits yet — nothing to check.')
        return
    execute(context, f'uv run cz check --rev-range {revision_range}')


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
