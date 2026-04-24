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


def combo_context(dep_track: bool) -> dict:
    """Matrix cell context: widest Python range plus the dep-track boolean under test."""
    return {**base_context(), 'integrate_dependency_track': dep_track}


def combo_label(dep_track: bool) -> str:
    """Stable short label for log files and CI job names."""
    return 'dep1' if dep_track else 'dep0'


def matrix_combos() -> list[dict]:
    """All combos the matrix should exercise."""
    return [
        {'label': combo_label(dep_track), 'integrate_dependency_track': dep_track}
        for dep_track in (False, True)
    ]
