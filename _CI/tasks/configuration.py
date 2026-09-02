"""Centralized constants for CI task definitions."""

import re
import shutil

import yaml

from _CI import PROJECT_ROOT_DIRECTORY

TEMPLATE_PYPROJECT = PROJECT_ROOT_DIRECTORY / 'template' / 'pyproject.toml.jinja'

# Generation normally stamps the newest uv release that has cleared its cool-down, so a new
# project starts current. That would break the template's own tests: CI installs the uv the
# template pins, then generates projects and runs `uv sync` with it, and a freshly stamped
# `required-version` the ambient uv cannot satisfy fails every matrix cell. Setting this to the
# committed pin makes generation deterministic and keeps it matching the installed uv.
UV_VERSION_ENV = 'TEMPLATE_UV_VERSION'

PROJECT_SLUG = 'paleofuturistic_python_project'
IGNORE_PATTERNS = shutil.ignore_patterns('.git', '.venv', '__pycache__', '*.pyc', '.copier-answers.yml')
# `secure.audit` runs right after the static checks and before the slow tox matrix, so a
# vulnerable dependency fails fast. It is also the step the `<PROJECT>_SECURITY_OVERRIDE`
# plumbing below exists to serve — until it was listed here, that env var was set for
# nothing and the `.security-overrides` expiry mechanism gated no automated run at all.
# The same collapse the generated project's own pipeline went through, for the same reason:
# `preflight` covers format, lint, ty, pyscn, the tox matrix, the wheel and the derived files,
# so listing those separately re-ran the work in a different shape and gave the matrix two
# lists of checks to keep in step. What is left is what `preflight` deliberately does not do —
# the dependency audit, whose answer depends on the advisory database rather than on the
# generated tree, and the docs build.
#
# The audit runs first: it is the cheapest way to fail, and there is no sense spending a
# five-interpreter matrix on a cell that a vulnerable pin already condemns.
QA_STEPS = ('secure.audit', 'preflight', 'document')
TEMPLATE_SECURITY_OVERRIDE_ENV = 'TEMPLATE_SECURITY_OVERRIDE'
SECURITY_OVERRIDES_FILE = PROJECT_ROOT_DIRECTORY / '.security-overrides'


def read_template_overrides():
    """Return comma-joined entries from the parent `.security-overrides` file.

    Entries are validated and parsed by the inner template's `secure.audit`
    task when the merged string is forwarded via `<PROJECT>_SECURITY_OVERRIDE`,
    so the parent only needs to strip `#` comments and blank lines.
    """
    if not SECURITY_OVERRIDES_FILE.exists():
        return ''
    entries = []
    for raw in SECURITY_OVERRIDES_FILE.read_text(encoding='utf-8').splitlines():
        entry = raw.split('#', 1)[0].strip()
        if entry:
            entries.append(entry)
    return ','.join(entries)


def template_uv_version() -> str:
    """Return the uv version the template currently pins.

    Read from the template source rather than hardcoded, so it follows `maintain.bump-uv`
    automatically. Used to pin what generation stamps during the template's own tests.

    Raises:
        RuntimeError: If the template has no exact `required-version` to read.
    """
    match = re.search(
        r'^required-version = "==([^"]+)"$', TEMPLATE_PYPROJECT.read_text(encoding='utf-8'), re.MULTILINE
    )
    if not match:
        msg = f'no exact [tool.uv] required-version found in {TEMPLATE_PYPROJECT}'
        raise RuntimeError(msg)
    return match.group(1)


def generation_env() -> dict:
    """Environment for invoking copier in tests: pins the uv version generation stamps."""
    return {UV_VERSION_ENV: template_uv_version()}


def version_sort_key(version: str) -> tuple[int, ...]:
    """Sort key for dotted version strings so 3.10 sorts above 3.9."""
    return tuple(int(part) for part in version.split('.'))


def base_context() -> dict:
    """Widest supported context, derived from copier.yml's python-version choices."""
    copier_data = yaml.safe_load((PROJECT_ROOT_DIRECTORY / 'copier.yml').read_text(encoding='utf-8'))
    known_versions = sorted(copier_data['min_python_version']['choices'], key=version_sort_key)
    return {'min_python_version': known_versions[0], 'max_python_version': known_versions[-1]}


def combo_context(*, git_hosting_service: str, integrate_dependency_track: bool, integrate_pages: bool) -> dict:
    """Matrix-cell context: widest Python range plus the three binary template knobs."""
    return {
        **base_context(),
        'git_hosting_service': git_hosting_service,
        'integrate_dependency_track': integrate_dependency_track,
        'integrate_pages': integrate_pages,
    }


def combo_label(*, git_hosting_service: str, integrate_dependency_track: bool, integrate_pages: bool) -> str:
    """Stable short label for log files and CI job names: e.g. ``gh-dep1-pages0``."""
    host_short = 'gh' if git_hosting_service == 'github' else 'gl'
    return f'{host_short}-dep{int(integrate_dependency_track)}-pages{int(integrate_pages)}'


def matrix_combos() -> list[dict]:
    """Cartesian product over git_hosting_service x integrate_dependency_track x integrate_pages."""
    return [
        {
            'label': combo_label(
                git_hosting_service=host,
                integrate_dependency_track=dep_track,
                integrate_pages=pages,
            ),
            'git_hosting_service': host,
            'integrate_dependency_track': dep_track,
            'integrate_pages': pages,
        }
        for host in ('github', 'gitlab')
        for dep_track in (False, True)
        for pages in (False, True)
    ]
