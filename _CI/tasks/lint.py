"""Lint task definitions for the parent template repository.

The repository that defines the standard was not held to it: nothing linted `tasks_render.py`
or `tests/` until this existed, while every generated project shipped a full lint gate. The
rule set in the root `pyproject.toml` mirrors the one generated projects get, so a change made
here is judged the same way as the code it produces.

Only ruff runs so far. pylint, ty and complexipy are part of a generated project's `lint` and
are not wired up here yet.
"""

from invoke import Context, task

from _CI import emojize_message

# Ruff resolves the nearest config for each file, however it is invoked, so `_CI/` is judged by
# `_CI/pyproject.toml` here — the same lighter rule set a generated project applies to its own
# tooling — and the rest by the root config. Listing `_CI/` costs no parity; leaving it out
# meant nothing linted it at all.
PATHS = '_CI/__init__.py _CI/tasks/ tasks_render.py tests/'
RUFF = 'uv run --group lint ruff'


def run_ruff(context: Context, args: str, label: str) -> bool:
    """Run one ruff invocation, print a status line, and return whether it passed."""
    result = context.run(f'{RUFF} {args}', warn=True)
    passed = not result.failed
    print(emojize_message(f'{label} {"passed" if passed else "failed"}', success=passed))
    return passed


@task(name='ruff')
def ruff(context: Context) -> None:
    """Check the parent repository against the same rule set generated projects use."""
    if not run_ruff(context, f'check {PATHS}', 'lint.ruff'):
        raise SystemExit(1)


@task(name='format')
def format_(context: Context) -> None:
    """Verify formatting without rewriting anything, as the gate does."""
    if not run_ruff(context, f'format --check {PATHS}', 'lint.format'):
        raise SystemExit(1)


@task(default=True, name='all')
def lint(context: Context) -> None:
    """Run every parent lint check, reporting all failures before exiting."""
    # Both run even when the first fails: a single pass should surface every problem rather
    # than making the caller re-run to discover the next one.
    results = [
        run_ruff(context, f'check {PATHS}', 'lint.ruff'),
        run_ruff(context, f'format --check {PATHS}', 'lint.format'),
    ]
    if not all(results):
        raise SystemExit(1)
    print(emojize_message('All parent lint checks passed'))
