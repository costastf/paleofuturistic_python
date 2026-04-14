"""Security task definitions."""

import os
from datetime import date
from typing import cast

from invoke import Collection, Context, Task, task

from .configuration import IGNORE_PATTERN, PROJECT_NAME, SECURITY_OVERRIDE_ENV
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
@logged('secure.sbom-extract')
def sbom_extract(context: Context, write: bool = False) -> None:
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
@logged('secure.sbom-upload')
def sbom_upload(context: Context) -> None:
    """Extract and upload SBOM to OWASP Dependency Track.

    Requires the OWASP_DTRACK_API_KEY environment variable to be set.
    """
    api_key = os.environ.get('OWASP_DTRACK_API_KEY')
    if not api_key:
        print('OWASP_DTRACK_API_KEY environment variable is not set.')
        print('Set it to your Dependency Track API key to enable SBOM uploads.')
        raise SystemExit(1)
    sbom_extract(context, write=True)
    result = context.run('uv run cz version', hide=True)
    if result is None or result.failed:
        print('Could not determine project version.')
        raise SystemExit(1)
    version = result.stdout.strip()
    execute(
        context,
        f'uv run owasp-dtrack-cli test '
        f'--project-name {PROJECT_NAME} '
        f'--project-version {version} '
        f'--auto-create sbom.json',
    )


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
        sbom_extract(context, write=True)
    except SystemExit:
        failed = True
    if failed:
        raise SystemExit(1)


namespace = Collection('secure')
namespace.add_task(cast(Task, secure), default=True, name='all')
namespace.add_task(cast(Task, audit))
namespace.add_task(cast(Task, sbom_extract))
namespace.add_task(cast(Task, sbom_upload))
