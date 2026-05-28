import os
import re
import shutil
import stat
import sys
from datetime import date, datetime
from pathlib import Path

MIN_VERSION = '{{ cookiecutter.min_python_version }}'
MAX_VERSION = '{{ cookiecutter.max_python_version }}'
KNOWN_VERSIONS = {{ cookiecutter._known_python_versions }}
LICENSE_CHOICE = '{{ cookiecutter.license }}'
AUTHOR = '{{ cookiecutter.full_name }}'
EMAIL = '{{ cookiecutter.email }}'
PROJECT_SLUG = '{{ cookiecutter.project_slug }}'
GIT_HOSTING_SERVICE = '{{ cookiecutter.git_hosting_service }}'
INTEGRATE_PAGES = '{{ cookiecutter.integrate_pages }}' == 'True'

LICENSES_DIR = Path('licenses')
PAGES_WORKFLOW = Path('.github/workflows/pages.yaml')
WORKFLOW_CMD = Path('workflow.cmd')
HOST_ARTIFACTS = {
    'github': (Path('.github'), Path('_CI/tasks/github.py')),
    'gitlab': (Path('.gitlab-ci.yml'), Path('_CI/tasks/gitlab.py')),
}

YEAR = str(date.today().year)
RELEASE_DATE = datetime.now().strftime('%d-%m-%Y')


def version_tuple(version: str) -> tuple[int, ...]:
    """Return a sortable int-tuple for a dotted Python version string."""
    return tuple(int(part) for part in version.split('.'))


def fail(message: str) -> None:
    """Print `message` and exit non-zero so cookiecutter aborts generation."""
    print(message)
    sys.exit(1)


def validate_python_versions() -> None:
    """Sanity-check the cookiecutter python-version inputs."""
    try:
        min_tuple = version_tuple(MIN_VERSION)
        max_tuple = version_tuple(MAX_VERSION)
    except ValueError:
        fail(f'ERROR: min/max python versions must be dotted integers; got {MIN_VERSION!r} and {MAX_VERSION!r}.')
    if max_tuple < min_tuple:
        fail(f'ERROR: max_python_version ({MAX_VERSION}) cannot be less than min_python_version ({MIN_VERSION}).')
    for label, chosen in (('min_python_version', MIN_VERSION), ('max_python_version', MAX_VERSION)):
        if chosen not in KNOWN_VERSIONS:
            fail(f'ERROR: {label} ({chosen}) is not declared in _known_python_versions ({KNOWN_VERSIONS}).')
    if min_tuple[0] != max_tuple[0]:
        fail(
            f'ERROR: min_python_version ({MIN_VERSION}) and max_python_version ({MAX_VERSION}) '
            'must share the same major version; cross-major ranges are not supported.'
        )


def install_license() -> str:
    """Copy the chosen LICENSE into place and return the short header text (empty if no header)."""
    header = ''
    if LICENSE_CHOICE != 'None':
        shutil.copy2(LICENSES_DIR / LICENSE_CHOICE, 'LICENSE')
        header_file = LICENSES_DIR / f'{LICENSE_CHOICE}.header'
        if header_file.exists():
            header = header_file.read_text(encoding='utf-8').format(year=YEAR, author=AUTHOR)
    shutil.rmtree(LICENSES_DIR)
    return header


def prune_unchosen_host_artifacts() -> None:
    """Remove the scaffolding for the git hosting service the user did not pick."""
    unchosen = 'gitlab' if GIT_HOSTING_SERVICE == 'github' else 'github'
    for path in HOST_ARTIFACTS[unchosen]:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


def prune_pages_workflow_if_disabled() -> None:
    """Drop pages.yaml unless the user opted in *and* picked a host with Pages scaffolding."""
    if PAGES_WORKFLOW.exists() and not (INTEGRATE_PAGES and GIT_HOSTING_SERVICE == 'github'):
        PAGES_WORKFLOW.unlink()


def strip_leading_docstring(text: str) -> str:
    """Remove a leading module docstring from Python source."""
    return re.sub(r'\A\s*("""[^"]*"""|\'\'\'[^\']*\'\'\')\s*\n?', '', text)


def build_header(license_header: str, *, with_logging: bool) -> str:
    """Compose the dunder-metadata header to prepend to a Python source file."""
    lines = []
    if license_header:
        lines.append(license_header.rstrip())
    lines.append(f'"""{PROJECT_SLUG}."""')
    lines.append('')
    if with_logging:
        lines.append('import logging')
        lines.append('')
    lines.append(f"__author__ = '{AUTHOR} <{EMAIL}>'")
    lines.append("__docformat__ = 'google'")
    lines.append(f"__date__ = '{RELEASE_DATE}'")
    lines.append(f"__copyright__ = 'Copyright {YEAR}, {AUTHOR}'")
    lines.append(f"__credits__ = ['{AUTHOR}']")
    lines.append(f"__license__ = '{LICENSE_CHOICE}'")
    lines.append(f"__maintainer__ = '{AUTHOR}'")
    lines.append(f"__email__ = '<{EMAIL}>'")
    lines.append("__status__ = 'Development'")
    lines.append('')
    if with_logging:
        lines.append(f"LOGGER_BASENAME = '{PROJECT_SLUG}'")
        lines.append('LOGGER = logging.getLogger(LOGGER_BASENAME)')
        lines.append('LOGGER.addHandler(logging.NullHandler())')
        lines.append('')
        lines.append('')
    return '\n'.join(lines)


def prepend_header(filepath: Path, license_header: str, *, with_logging: bool = False) -> None:
    """Replace the leading module docstring of `filepath` with the standard header."""
    content = strip_leading_docstring(filepath.read_text(encoding='utf-8')).strip()
    header = build_header(license_header, with_logging=with_logging)
    result = f'{header}\n{content}\n' if content else f'{header.rstrip()}\n'
    filepath.write_text(result, encoding='utf-8')


def apply_headers_to_python_files(license_header: str) -> None:
    """Prepend the standard header to every .py file under src/ and tests/."""
    main_module = Path('src') / PROJECT_SLUG / f'{PROJECT_SLUG}.py'
    for directory in (Path('src'), Path('tests')):
        for py_file in directory.rglob('*.py'):
            prepend_header(py_file, license_header, with_logging=(py_file == main_module))


def make_workflow_cmd_executable() -> None:
    """Set the executable bit on workflow.cmd so the Unix launcher works."""
    mode = os.stat(WORKFLOW_CMD).st_mode
    os.chmod(WORKFLOW_CMD, mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def main() -> None:
    validate_python_versions()
    license_header = install_license()
    prune_unchosen_host_artifacts()
    prune_pages_workflow_if_disabled()
    apply_headers_to_python_files(license_header)
    make_workflow_cmd_executable()


main()
