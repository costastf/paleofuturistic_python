"""Security task definitions."""

import os
from datetime import date
from typing import cast

from invoke import Collection, Context, Task, task

from .configuration import IGNORE_PATTERN, SECURITY_OVERRIDE_ENV, SECURITY_OVERRIDES_FILE
{%- if cookiecutter.integrate_dependency_track %}
from .configuration import OWASP_DTRACK_SETTINGS, PROJECT_NAME
{%- endif %}
from .shared import execute, logged


def validate_override_entry(entry: str, source: str) -> None:
    """Abort with a clear message if `entry` is not a valid suppression.

    Format: ``<VULN_ID>[::YYYY-MM-DD]`` — the vulnerability id must match the
    project-wide ``IGNORE_PATTERN``, and the expiry, when present, must be a
    real calendar date. ``source`` is prepended to the error for context
    (e.g. ``.security-overrides:7``).

    Raises:
        SystemExit: with exit code 1 if the entry is malformed.
    """
    expected = (
        '<VULN_ID>[::YYYY-MM-DD] — e.g. CVE-2024-1234::2026-12-31 (expires, '
        'forces re-review on the date) or plain CVE-2024-1234 (permanent '
        'suppression, the audit will never flag this vulnerability again — '
        'prefer an expiry when you can)'
    )
    match = IGNORE_PATTERN.fullmatch(entry)
    if not match:
        print(f'{source}: invalid entry {entry!r}; expected {expected}')
        raise SystemExit(1)
    expiry = match.group('expiration_date')
    if not expiry:
        return
    try:
        date.fromisoformat(expiry)
    except ValueError as exc:
        print(f'{source}: invalid expiry {expiry!r}: {exc}; expected YYYY-MM-DD (or omit for a permanent suppression)')
        raise SystemExit(1) from None


def load_overrides_file() -> str:
    """Return comma-joined entries from `.security-overrides`, stripping `#` comments and blanks."""
    if not SECURITY_OVERRIDES_FILE.exists():
        return ''
    entries: list[str] = []
    for lineno, raw in enumerate(SECURITY_OVERRIDES_FILE.read_text(encoding='utf-8').splitlines(), start=1):
        entry = raw.split('#', 1)[0].strip()
        if not entry:
            continue
        validate_override_entry(entry, f'{SECURITY_OVERRIDES_FILE}:{lineno}')
        entries.append(entry)
    return ','.join(entries)


@task
@logged('secure.audit')
def audit(context: Context, ignore: str | None = None) -> None:
    """Run pip-audit security scan.

    Suppressions are sourced, in precedence order, from ``--ignore``, the
    ``{{ cookiecutter.project_slug | upper }}_SECURITY_OVERRIDE`` environment
    variable, and a ``.security-overrides`` file at the project root. All three
    are merged and deduplicated. Each entry is a vulnerability ID with an
    optional expiry (``CVE-2024-1234::2026-12-31``); entries whose expiry has
    passed are dropped so the audit fails until the suppression is reviewed.

    Args:
        context: Invoke context.
        ignore: Comma-separated vulnerability IDs to ignore.
    """
    today = date.today()  # noqa: DTZ011
    env_override = os.environ.get(SECURITY_OVERRIDE_ENV, '')
    file_override = load_overrides_file()
    combined = ','.join(filter(None, [ignore, env_override, file_override]))
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


{%- if cookiecutter.integrate_dependency_track %}


@task
@logged('secure.sbom-upload')
def sbom_upload(context: Context) -> None:
    """Extract and upload SBOM to OWASP Dependency Track.

    Requires the OWASP_DTRACK_URL and OWASP_DTRACK_API_KEY environment variables to be set.
    """
    missing = [v for v in OWASP_DTRACK_SETTINGS if not os.environ.get(v)]
    if missing:
        print(f'Missing required environment variables: {", ".join(missing)}')
        print('Set them to enable SBOM uploads to Dependency Track.')
        raise SystemExit(1)
    sbom_extract(context, write=True)
    result = context.run('uv run cz version -p', hide=True)
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
{%- endif %}


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
{%- if cookiecutter.integrate_dependency_track %}
namespace.add_task(cast(Task, sbom_upload))
{%- endif %}
