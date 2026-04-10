"""Security task definitions."""

import os
import re
from datetime import date
from typing import cast

from invoke import Collection, Context, Task, task

from .shared import SECURITY_OVERRIDE_ENV, exec_, logged, run, run_steps

_IGNORE_PATTERN = re.compile(
    r'(?P<vulnerability_id>[A-Za-z0-9\-_]+)'
    r'(::(?P<expiration_date>\d{4}-\d{2}-\d{2}))?'
)


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
        for m in _IGNORE_PATTERN.finditer(combined)
        if not m.group('expiration_date')
        or date.fromisoformat(m.group('expiration_date')) > today
    ]
    ignore_opts = (' ' + ' '.join(ignore_args)) if ignore_args else ''
    exec_(context, f'uv run pip-audit{ignore_opts}')


@task
@logged('secure.extract-sbom')
@run('uv run cyclonedx-py environment --output-file sbom.json')
def extract_sbom(context: Context) -> None:
    """Extract a Software Bill of Materials using CycloneDX into sbom.json."""


@task
@logged('secure')
def secure(context: Context) -> None:
    """Run all security checks; reports all failures before exiting."""
    run_steps(audit, extract_sbom)(context)


namespace = Collection('secure')
namespace.add_task(cast(Task, secure), default=True, name='all')
namespace.add_task(cast(Task, audit))
namespace.add_task(cast(Task, extract_sbom))
