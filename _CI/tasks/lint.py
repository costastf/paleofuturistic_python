"""Lint task definitions for the parent template repository.

The repository that defines the standard is held to it: ruff, the formatter, pylint, ty,
complexipy and commitizen run here over `_CI/`, `tasks_render.py` and `tests/` under the same
pins and the same rule set a generated project gets, so a change made here is judged the same
way as the code it produces (ADR-0048, ADR-0051, ADR-0052). The pyproject validator is the one
step of a generated project's `lint` not run here: this repository publishes no package.
"""

import os
import re
import shutil
from collections.abc import Callable
from pathlib import Path

from invoke import Context, task

from _CI import PROJECT_ROOT_DIRECTORY, emojize_message

# Ruff resolves the nearest config for each file, however it is invoked, so `_CI/` is judged by
# `_CI/pyproject.toml` here — the same lighter rule set a generated project applies to its own
# tooling — and the rest by the root config. Listing `_CI/` costs no parity; leaving it out
# meant nothing linted it at all.
PATHS = '_CI/__init__.py _CI/tasks/ tasks_render.py tests/'
# With the test group: pylint and ty follow imports, so the modules `tests/` imports have to be
# installed where they run, or every `import pytest` is an error. CI syncs nothing else.
LINT = 'uv run --group lint --group test'
# What a generated project's `lint.complexipy` allows, held here over the same paths the other
# checks read and over the template's own `_CI` modules, named one by one so the vendored tree
# under `template/_CI/lib` stays out. The `.jinja` task modules are read too, with their tags
# stripped into `reports/` first, since complexipy sees only `.py` files (ADR-0051).
COMPLEXITY_BAR = 8
COMPLEXITY_PATHS = f'{PATHS} template/_CI/tasks/ template/_CI/info.py template/_CI/uv_release.py'
JINJA_TASKS = PROJECT_ROOT_DIRECTORY / 'template' / '_CI' / 'tasks'
STRIPPED_TASKS = PROJECT_ROOT_DIRECTORY / 'reports' / 'stripped-tasks'
JINJA_BLOCK = re.compile(r'\{%-?.*?-?%\}')
JINJA_EXPRESSION = re.compile(r'\{\{.*?\}\}')


def run_check(context: Context, command: str, label: str) -> bool:
    """Run one lint command, print a status line, and return whether it passed."""
    result = context.run(f'{LINT} {command}', warn=True)
    passed = not result.failed
    print(emojize_message(f'{label} {"passed" if passed else "failed"}', success=passed))
    return passed


def resolves(context: Context, revision: str) -> bool:
    """Report whether git can resolve ``revision`` in this clone."""
    return not context.run(f'git rev-parse --verify --quiet {revision}', hide=True, warn=True).failed


def has_commits(context: Context, revision_range: str) -> bool:
    """Report whether ``revision_range`` holds at least one commit."""
    counted = context.run(f'git rev-list --count {revision_range}', hide=True, warn=True)
    return not counted.failed and counted.stdout.strip() not in ('', '0')


def range_candidates(context: Context) -> list[str]:
    """Return the ranges that could bound the check, best-informed first, each end resolving in this clone.

    The `lint` job exports `PRE_COMMIT_FROM_REF` and `PRE_COMMIT_TO_REF`, the names pre-commit
    hands a generated project's pre-push hook, so one reader serves the hook there and CI here
    (ADR-0053): a pull request's base and head, or what a push added. Then the tracking
    branch, which is what a push would add; then the remote's default branch, which is
    everything the branch holds over it, pushed or not.
    """
    from_ref, to_ref = os.environ.get('PRE_COMMIT_FROM_REF', ''), os.environ.get('PRE_COMMIT_TO_REF', '')
    candidates = []
    if from_ref and to_ref and resolves(context, from_ref) and resolves(context, to_ref):
        candidates.append(f'{from_ref}..{to_ref}')
    candidates.extend(f'{base}..HEAD' for base in ('@{upstream}', 'origin/HEAD') if resolves(context, base))
    return candidates


def unpushed_range(context: Context) -> str:
    """Return the range `cz check` reads: the first candidate holding a commit, else the tip alone.

    The same bound a generated project's `lint.commitizen` applies (ADR-0024, ADR-0052). An
    empty candidate falls through, since in CI the branch tracks a ref that *is* `HEAD`. The
    tip is `HEAD~1..HEAD` where a parent exists and `HEAD` where it does not, which is a root
    commit or a shallow clone.
    """
    for candidate in range_candidates(context):
        if has_commits(context, candidate):
            return candidate
    return 'HEAD~1..HEAD' if resolves(context, 'HEAD^') else 'HEAD'


def strip_jinja_modules() -> Path:
    """Write every `.jinja` task module with its tags removed under `reports/`, and return the directory.

    A block tag goes and both arms of an `if` stay, so every function the module can render is
    counted; an expression becomes a plain name, since what it renders to is a string the
    complexity does not depend on. The directory is rebuilt each time, so a renamed module
    leaves no stale copy behind to be read.
    """
    shutil.rmtree(STRIPPED_TASKS, ignore_errors=True)
    STRIPPED_TASKS.mkdir(parents=True)
    for path in JINJA_TASKS.glob('*.jinja'):
        name = JINJA_BLOCK.sub('', path.name.removesuffix('.jinja'))
        text = JINJA_EXPRESSION.sub('X', JINJA_BLOCK.sub('', path.read_text(encoding='utf-8')))
        (STRIPPED_TASKS / name).write_text(text, encoding='utf-8')
    return STRIPPED_TASKS


def complexipy_command(context: Context) -> str:  # noqa: ARG001 — built like the commitizen command, which needs it
    """Build the complexity check over the plain modules and the stripped `.jinja` ones."""
    stripped = strip_jinja_modules().relative_to(PROJECT_ROOT_DIRECTORY)
    return f'complexipy --max-complexity-allowed {COMPLEXITY_BAR} {COMPLEXITY_PATHS} {stripped}'


def commitizen_command(context: Context) -> str:
    """Build the commit-message check over the range this clone says a push would add."""
    return f'cz check --rev-range {unpushed_range(context)}'


# Each check as a command, so the aggregate and the single tasks run the same thing. The two
# in `BUILT_CHECKS` are made at run time: one strips the `.jinja` modules first, the other
# reads its range from the clone.
CHECKS = {
    'lint.ruff': f'ruff check {PATHS}',
    'lint.format': f'ruff format --check {PATHS}',
    # Four workers, as a generated project runs it: astroid follows the import graph behind
    # `_CI/tasks/`, and the pool pays for itself from the first module.
    'lint.pylint': f'pylint -j 4 {PATHS}',
    # Whole-program, never narrowed: a signature change surfaces in its callers.
    'lint.ty': f'ty check {PATHS}',
}
BUILT_CHECKS: dict[str, Callable[[Context], str]] = {
    'lint.complexipy': complexipy_command,
    'lint.commitizen': commitizen_command,
}


def command_for(context: Context, label: str) -> str:
    """Return the command behind ``label``, building it only when the label needs that."""
    return CHECKS[label] if label in CHECKS else BUILT_CHECKS[label](context)


def checks(context: Context) -> dict[str, str]:
    """Return every check as ``{label: command}``, the built ones bound to this clone."""
    return {**CHECKS, **{label: build(context) for label, build in BUILT_CHECKS.items()}}


def run_one(context: Context, label: str) -> None:
    """Run one named check and exit non-zero when it fails."""
    if not run_check(context, command_for(context, label), label):
        raise SystemExit(1)


@task(name='ruff')
def ruff(context: Context) -> None:
    """Check the parent repository against the same rule set generated projects use."""
    run_one(context, 'lint.ruff')


@task(name='format')
def format_(context: Context) -> None:
    """Verify formatting without rewriting anything, as the gate does."""
    run_one(context, 'lint.format')


@task(name='pylint')
def pylint(context: Context) -> None:
    """Run pylint under the template's disable list."""
    run_one(context, 'lint.pylint')


@task(name='ty')
def ty(context: Context) -> None:
    """Type-check the parent repository with the vendored invoke on the search path."""
    run_one(context, 'lint.ty')


@task(name='complexipy')
def complexipy(context: Context) -> None:
    """Fail any function above the cognitive complexity bar a generated project is held to."""
    run_one(context, 'lint.complexipy')


@task(name='commitizen')
def commitizen(context: Context) -> None:
    """Check the commit messages a push would add against the conventional format."""
    run_one(context, 'lint.commitizen')


@task(default=True, name='all')
def lint(context: Context) -> None:
    """Run every parent lint check, reporting all failures before exiting."""
    # Every check runs even when an earlier one fails: a single pass should surface every
    # problem rather than making the caller re-run to discover the next one.
    results = [run_check(context, command, label) for label, command in checks(context).items()]
    if not all(results):
        raise SystemExit(1)
    print(emojize_message('All parent lint checks passed'))
