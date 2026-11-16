"""Lint task definitions for the parent template repository.

The repository that defines the standard is held to it: ruff, the formatter, pylint and ty
run here over `_CI/`, `tasks_render.py` and `tests/` under the same pins and the same rule
set a generated project gets, so a change made here is judged the same way as the code it
produces (ADR-0048). complexipy and the pyproject validator are the two steps of a generated
project's `lint` not run here.
"""

from invoke import Context, task

from _CI import emojize_message

# Ruff resolves the nearest config for each file, however it is invoked, so `_CI/` is judged by
# `_CI/pyproject.toml` here — the same lighter rule set a generated project applies to its own
# tooling — and the rest by the root config. Listing `_CI/` costs no parity; leaving it out
# meant nothing linted it at all.
PATHS = '_CI/__init__.py _CI/tasks/ tasks_render.py tests/'
# With the test group: pylint and ty follow imports, so the modules `tests/` imports have to be
# installed where they run, or every `import pytest` is an error. CI syncs nothing else.
LINT = 'uv run --group lint --group test'


def run_check(context: Context, command: str, label: str) -> bool:
    """Run one lint command, print a status line, and return whether it passed."""
    result = context.run(f'{LINT} {command}', warn=True)
    passed = not result.failed
    print(emojize_message(f'{label} {"passed" if passed else "failed"}', success=passed))
    return passed


# Each check as a command, so the aggregate and the single tasks run the same thing.
CHECKS = {
    'lint.ruff': f'ruff check {PATHS}',
    'lint.format': f'ruff format --check {PATHS}',
    # Four workers, as a generated project runs it: astroid follows the import graph behind
    # `_CI/tasks/`, and the pool pays for itself from the first module.
    'lint.pylint': f'pylint -j 4 {PATHS}',
    # Whole-program, never narrowed: a signature change surfaces in its callers.
    'lint.ty': f'ty check {PATHS}',
}


def run_one(context: Context, label: str) -> None:
    """Run one named check and exit non-zero when it fails."""
    if not run_check(context, CHECKS[label], label):
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


@task(default=True, name='all')
def lint(context: Context) -> None:
    """Run every parent lint check, reporting all failures before exiting."""
    # Every check runs even when an earlier one fails: a single pass should surface every
    # problem rather than making the caller re-run to discover the next one.
    results = [run_check(context, command, label) for label, command in CHECKS.items()]
    if not all(results):
        raise SystemExit(1)
    print(emojize_message('All parent lint checks passed'))
