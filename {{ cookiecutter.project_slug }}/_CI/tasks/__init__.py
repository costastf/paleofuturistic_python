"""CI task definitions for the project workflow."""

from collections.abc import Callable
from functools import wraps

from invoke import Collection, Context, task

_PATHS = 'src/ _CI/tasks/ tests/'


def _run(cmd: str) -> Callable[[Callable[[Context], None]], Callable[[Context], None]]:
    """Decorator: replace the function body with a shell-command invocation."""

    def decorator(fn: Callable[[Context], None]) -> Callable[[Context], None]:
        @wraps(fn)
        def wrapper(context: Context) -> None:
            result = context.run(cmd, echo=True, warn=True)
            if result is None or result.failed:
                raise SystemExit(1)

        return wrapper

    return decorator


def _logged(name: str) -> Callable[[Callable[[Context], None]], Callable[[Context], None]]:
    """Decorator: print ✅ on success or ❌ on SystemExit failure."""

    def decorator(fn: Callable[[Context], None]) -> Callable[[Context], None]:
        @wraps(fn)
        def wrapper(context: Context) -> None:
            try:
                fn(context)
                print(f'✅ {name} passed 👍')
            except SystemExit:
                print(f'❌ {name} failed 👎')
                raise

        return wrapper

    return decorator


@task
@_logged('ruff-format')
@_run(f'uv run ruff format --diff {_PATHS}')
def ruff_format(context: Context) -> None:
    """Check code formatting with ruff."""


@task
@_logged('ruff-lint')
@_run(f'uv run ruff check {_PATHS}')
def ruff_lint(context: Context) -> None:
    """Run ruff linter."""


@task
@_logged('pylint')
@_run(f'uv run pylint {_PATHS}')
def pylint(context: Context) -> None:
    """Run pylint."""


@task
@_logged('ty')
@_run(f'uv run ty check {_PATHS}')
def ty(context: Context) -> None:
    """Run ty type checker."""


@task
@_logged('lint')
def lint(context: Context) -> None:
    """Run all linting steps; reports all failures before exiting."""
    failed = False
    linting_steps = (ruff_lint, pylint, ty)
    for step in linting_steps:
        try:
            step(context)
        except SystemExit:
            failed = True
    if failed:
        raise SystemExit(1)


@task
@_logged('secure')
@_run('uv run pip-audit')
def audit(context: Context) -> None:
    """Run pip-audit security scan."""


@task
@_logged('secure.extract-sbom')
@_run('uv run cyclonedx-py environment')
def extract_sbom(context: Context) -> None:
    """Extract a Software Bill of Materials using CycloneDX."""


@task
@_logged('test')
@_run('uv run pytest --strict')
def test(context: Context) -> None:
    """Run pytest."""


@task
@_logged('build')
@_run('uv build')
def build(context: Context) -> None:
    """Build the package."""


@task
@_logged('document')
@_run('uv run mkdocs build')
def document(context: Context) -> None:
    """Build the documentation."""


_secure_ns = Collection('secure')
_secure_ns.add_task(audit, default=True)  # type: ignore[invalid-argument-type]
_secure_ns.add_task(extract_sbom)  # type: ignore[invalid-argument-type]

namespace = Collection(ruff_format, ruff_lint, pylint, ty, lint, test, build, document)
namespace.add_collection(_secure_ns)
