"""Lint task definitions for the parent template repository.

The repository that defines the standard is held to it: ruff, the formatter, pylint, ty,
complexipy and commitizen run here over `_CI/`, `tasks_render.py` and `tests/` under the same
pins and the same rule set a generated project gets, so a change made here is judged the same
way as the code it produces (ADR-0048, ADR-0051, ADR-0052). The pyproject validator is the one
step of a generated project's `lint` not run here: this repository publishes no package.
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
# What a generated project's `lint.complexipy` allows, held here over the same paths the other
# checks read and over the template's own `_CI` modules, named one by one so the vendored tree
# under `template/_CI/lib` stays out. The `.jinja` modules are not read: complexipy sees only
# `.py` files, and the generated gate reads `src/` alone.
COMPLEXITY_BAR = 8
COMPLEXITY_PATHS = f'{PATHS} template/_CI/tasks/ template/_CI/info.py template/_CI/uv_release.py'


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


def unpushed_range(context: Context) -> str:
    """Return the range `cz check` reads: what a push would add, else the tip commit alone.

    The same bound a generated project's `lint.commitizen` applies (ADR-0024), without the
    pre-commit refs: this repository installs no hooks. The tracking branch first, then the
    remote's default branch; an empty range falls through, since in CI the branch tracks a ref
    that *is* `HEAD`. The tip is `HEAD~1..HEAD` where a parent exists and `HEAD` where it does
    not, which is a root commit or a shallow clone (ADR-0052).
    """
    for base in ('@{upstream}', 'origin/HEAD'):
        candidate = f'{base}..HEAD'
        if resolves(context, base) and has_commits(context, candidate):
            return candidate
    return 'HEAD~1..HEAD' if resolves(context, 'HEAD^') else 'HEAD'


# Each check as a command, so the aggregate and the single tasks run the same thing. The
# commit-message check joins in `checks`, since its range is read from the clone at run time.
CHECKS = {
    'lint.ruff': f'ruff check {PATHS}',
    'lint.format': f'ruff format --check {PATHS}',
    # Four workers, as a generated project runs it: astroid follows the import graph behind
    # `_CI/tasks/`, and the pool pays for itself from the first module.
    'lint.pylint': f'pylint -j 4 {PATHS}',
    # Whole-program, never narrowed: a signature change surfaces in its callers.
    'lint.ty': f'ty check {PATHS}',
    'lint.complexipy': f'complexipy --max-complexity-allowed {COMPLEXITY_BAR} {COMPLEXITY_PATHS}',
}


def checks(context: Context) -> dict[str, str]:
    """Return every check as ``{label: command}``, the commit-message check bound to this clone."""
    return {**CHECKS, 'lint.commitizen': f'cz check --rev-range {unpushed_range(context)}'}


def run_one(context: Context, label: str) -> None:
    """Run one named check and exit non-zero when it fails."""
    if not run_check(context, checks(context)[label], label):
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
