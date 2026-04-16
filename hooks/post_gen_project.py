import os
import shutil
import stat
import sys
from datetime import date, datetime
from pathlib import Path

min_version = '{{ cookiecutter.min_python_version }}'
max_version = '{{ cookiecutter.max_python_version }}'
if max_version < min_version:
    print(f'ERROR: max_python_version ({max_version}) cannot be less than min_python_version ({min_version}).')
    sys.exit(1)

license_choice = '{{ cookiecutter.license }}'
author = '{{ cookiecutter.full_name }}'
email = '{{ cookiecutter.email }}'
project_slug = '{{ cookiecutter.project_slug }}'
licenses_dir = Path('licenses')
year = str(date.today().year)
release_date = datetime.now().strftime('%d-%m-%Y')

# Copy selected license to project root.
if license_choice != 'None':
    shutil.copy2(licenses_dir / license_choice, 'LICENSE')

# Read the short license header if applicable.
license_header = ''
header_file = licenses_dir / f'{license_choice}.header'
if license_choice != 'None' and header_file.exists():
    license_header = header_file.read_text(encoding='utf-8').format(year=year, author=author)

# Clean up the licenses directory.
shutil.rmtree(licenses_dir)


def _strip_leading_docstring(text: str) -> str:
    """Remove a leading module docstring from Python source."""
    import re
    return re.sub(r'\A\s*("""[^"]*"""|\'\'\'[^\']*\'\'\')\s*\n?', '', text)


def prepend_header(filepath: Path, *, with_logging: bool = False) -> None:
    """Prepend the standard file header to a Python source file."""
    filename = filepath.name
    content = _strip_leading_docstring(filepath.read_text(encoding='utf-8')).strip()
    header_lines = []
    if license_header:
        header_lines.append(license_header.rstrip())
    header_lines.append(f'"""{project_slug}."""')
    header_lines.append('')
    if with_logging:
        header_lines.append('import logging')
        header_lines.append('')
    header_lines.append(f"__author__ = '{author} <{email}>'")
    header_lines.append("__docformat__ = 'google'")
    header_lines.append(f"__date__ = '{release_date}'")
    header_lines.append(f"__copyright__ = 'Copyright {year}, {author}'")
    header_lines.append(f"__credits__ = ['{author}']")
    header_lines.append(f"__license__ = '{license_choice}'")
    header_lines.append(f"__maintainer__ = '{author}'")
    header_lines.append(f"__email__ = '<{email}>'")
    header_lines.append("__status__ = 'Development'")
    header_lines.append('')
    if with_logging:
        header_lines.append(f"LOGGER_BASENAME = '{project_slug}'")
        header_lines.append('LOGGER = logging.getLogger(LOGGER_BASENAME)')
        header_lines.append('LOGGER.addHandler(logging.NullHandler())')
        header_lines.append('')
    header = '\n'.join(header_lines)
    if content:
        result = header + '\n' + content + '\n'
    else:
        result = header.rstrip() + '\n'
    filepath.write_text(result, encoding='utf-8')


# Add headers to all Python files in src/ and tests/.
main_module = Path('src') / project_slug / f'{project_slug}.py'
for directory in (Path('src'), Path('tests')):
    for py_file in directory.rglob('*.py'):
        prepend_header(py_file, with_logging=(py_file == main_module))

os.chmod('workflow.cmd', os.stat('workflow.cmd').st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
