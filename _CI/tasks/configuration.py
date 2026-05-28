"""Centralized constants for CI task definitions."""

import json
import shutil

from _CI import PROJECT_ROOT_DIRECTORY

PROJECT_SLUG = 'paleofuturistic_python_project'
IGNORE_PATTERNS = shutil.ignore_patterns('.git', '.venv', '__pycache__', '*.pyc', '.cruft.json')
QA_STEPS = ('format', 'lint', 'test.tox', 'build', 'document')
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


def version_sort_key(version: str) -> tuple[int, ...]:
    """Sort key for dotted version strings so 3.10 sorts above 3.9."""
    return tuple(int(part) for part in version.split('.'))


def base_context() -> dict:
    """Widest supported cookiecutter context, derived from cookiecutter.json."""
    cookiecutter_path = PROJECT_ROOT_DIRECTORY / 'cookiecutter.json'
    cookiecutter_data = json.loads(cookiecutter_path.read_text(encoding='utf-8'))
    known_versions = sorted(cookiecutter_data['_known_python_versions'], key=version_sort_key)
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
