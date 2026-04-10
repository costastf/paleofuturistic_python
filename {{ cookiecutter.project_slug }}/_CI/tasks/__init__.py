"""CI task definitions for the project workflow."""

import os
import re
from collections.abc import Callable
from datetime import date
from functools import wraps
from typing import cast

from invoke import Collection, Context, Task, task

_PATHS = 'src/ _CI/tasks/ tests/'
_IGNORE_PATTERN = re.compile(
    r'(?P<vulnerability_id>[A-Za-z0-9\-_]+)'
    r'(::(?P<expiration_date>\d{4}-\d{2}-\d{2}))?'
)
_SECURITY_OVERRIDE_ENV = '{{ cookiecutter.project_slug | upper }}_SECURITY_OVERRIDE'


def _exec(context: Context, cmd: str) -> None:
    """Execute a shell command, raising SystemExit(1) on failure."""
    result = context.run(cmd, echo=True, warn=True)
    if result is None or result.failed:
        raise SystemExit(1)


def _run(cmd: str) -> Callable[[Callable[[Context], None]], Callable[[Context], None]]:
    """Decorator: replace the function body with a shell-command invocation."""

    def decorator(fn: Callable[[Context], None]) -> Callable[[Context], None]:
        @wraps(fn)
        def wrapper(context: Context) -> None:
            _exec(context, cmd)

        return wrapper

    return decorator


def _logged(name: str) -> Callable[[Callable[..., None]], Callable[..., None]]:
    """Decorator: print ✅ on success or ❌ on SystemExit failure."""

    def decorator(fn: Callable[..., None]) -> Callable[..., None]:
        @wraps(fn)
        def wrapper(context: Context, *args: object, **kwargs: object) -> None:
            try:
                fn(context, *args, **kwargs)
                print(f'✅ {name} passed 👍')
            except SystemExit:
                print(f'❌ {name} failed 👎')
                raise

        return wrapper

    return decorator


def _run_steps(*steps: Callable[[Context], None]) -> Callable[[Context], None]:
    """Run all steps, accumulating failures (same pattern as lint)."""

    def runner(context: Context) -> None:
        failed = False
        for step in steps:
            try:
                step(context)
            except SystemExit:
                failed = True
        if failed:
            raise SystemExit(1)

    return runner


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
    _run_steps(ruff_lint, pylint, ty)(context)


@task
@_logged('secure.audit')
def audit(context: Context, ignore: str | None = None) -> None:
    """Run pip-audit security scan.

    Args:
        context: Invoke context.
        ignore: Comma-separated vulnerability IDs to ignore, each with an optional
            expiry date (e.g. ``CVE-2024-1234::2025-12-31,GHSA-xxxx-yyyy-zzzz``).
            Entries whose expiry date is in the past are applied anyway.
            Project-level overrides can also be supplied via the
            ``{{ cookiecutter.project_slug | upper }}_SECURITY_OVERRIDE`` environment
            variable, which is merged with any ``--ignore`` argument.
    """
    today = date.today()  # noqa: DTZ011
    env_override = os.environ.get(_SECURITY_OVERRIDE_ENV, '')
    combined = ','.join(filter(None, [ignore, env_override]))
    ignore_args = [
        f'--ignore-vuln {m.group("vulnerability_id")}'
        for m in _IGNORE_PATTERN.finditer(combined)
        if not m.group('expiration_date')
        or date.fromisoformat(m.group('expiration_date')) > today
    ]
    ignore_opts = (' ' + ' '.join(ignore_args)) if ignore_args else ''
    _exec(context, f'uv run pip-audit{ignore_opts}')


@task
@_logged('secure.extract-sbom')
@_run('uv run cyclonedx-py environment --output-file sbom.json')
def extract_sbom(context: Context) -> None:
    """Extract a Software Bill of Materials using CycloneDX into sbom.json."""


@task
@_logged('secure')
def secure(context: Context) -> None:
    """Run all security checks; reports all failures before exiting."""
    _run_steps(audit, extract_sbom)(context)


@task
@_logged('test')
@_run('uv run pytest --strict')
def test(context: Context) -> None:
    """Run pytest."""


@task
@_logged('build.package')
@_run('uv build')
def package(context: Context) -> None:
    """Build the package."""


@task
@_logged('build')
def build(context: Context) -> None:
    """Run security checks and build the package; reports all failures before exiting."""
    _run_steps(secure, package)(context)


@task
@_logged('document')
@_run('uv run mkdocs build')
def document(context: Context) -> None:
    """Build the documentation."""


_secure_ns = Collection('secure')
_secure_ns.add_task(cast(Task, secure), default=True)
_secure_ns.add_task(cast(Task, audit))
_secure_ns.add_task(cast(Task, extract_sbom))

_build_ns = Collection('build')
_build_ns.add_task(cast(Task, build), default=True)
_build_ns.add_task(cast(Task, package))

namespace = Collection(ruff_format, ruff_lint, pylint, ty, lint, test, document)
namespace.add_collection(_secure_ns)
namespace.add_collection(_build_ns)
