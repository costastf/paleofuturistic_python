"""Security task definitions."""

import os
from datetime import date
from typing import cast

from invoke import Collection, Context, Task, task

from .configuration import IGNORE_PATTERN, SECURITY_OVERRIDE_ENV
from .shared import execute, logged


@task
@logged('secure.audit')
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
    env_override = os.environ.get(SECURITY_OVERRIDE_ENV, '')
    combined = ','.join(filter(None, [ignore, env_override]))
    ignore_args = [
        f'--ignore-vuln {m.group("vulnerability_id")}'
        for m in IGNORE_PATTERN.finditer(combined)
        if not m.group('expiration_date') or date.fromisoformat(m.group('expiration_date')) > today
    ]
    ignore_opts = (' ' + ' '.join(ignore_args)) if ignore_args else ''
    execute(context, f'uv run pip-audit{ignore_opts}')


@task
@logged('secure.extract-sbom')
def extract_sbom(context: Context, write: bool = False) -> None:
    """Extract a Software Bill of Materials using CycloneDX.

    By default prints the SBOM to stdout. With --write, writes to sbom.json.

    Args:
        context: Invoke context.
        write: Write SBOM to sbom.json instead of printing to stdout.
    """
    if write:
        execute(context, 'uv run cyclonedx-py environment --output-file sbom.json')
    else:
        execute(context, 'uv run cyclonedx-py environment')


@task
@logged('secure')
def secure(context: Context) -> None:
    """Run all security checks; reports all failures before exiting."""
    failed = False
    try:
        audit(context)
    except SystemExit:
        failed = True
    try:
        extract_sbom(context, write=True)
    except SystemExit:
        failed = True
    if failed:
        raise SystemExit(1)


namespace = Collection('secure')
namespace.add_task(cast(Task, secure), default=True, name='all')
namespace.add_task(cast(Task, audit))
namespace.add_task(cast(Task, extract_sbom))
