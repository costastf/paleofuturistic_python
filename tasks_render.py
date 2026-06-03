"""Copy-time render task for the copier template.

Runs once, after copier writes the project (cwd is the generated project root), via the
``_tasks`` hook in ``copier.yml`` gated to ``_copier_operation == 'copy'``. It performs the
steps that cannot be expressed declaratively:

* install the chosen LICENSE (substituting author/year tokens) and drop the staging dir,
* prepend the SPDX + dunder-metadata header to every ``.py`` under ``src/`` and ``tests/``,
* ensure ``workflow.cmd`` keeps its executable bit.

Version validation moved to the ``copier.yml`` validator; host/pages pruning moved to
conditional file/directory names. Copier passes the answers this task needs as CLI args.
"""

import argparse
import os
import re
import stat
from datetime import date, datetime
from pathlib import Path

LICENSES_DIR = Path('licenses')
WORKFLOW_CMD = Path('workflow.cmd')

YEAR = str(date.today().year)
RELEASE_DATE = datetime.now().strftime('%d-%m-%Y')


def install_license(license_choice: str, author: str) -> str:
    """Copy the chosen LICENSE into place and return the short header text (empty if none)."""
    header = ''
    if license_choice != 'None':
        body = (LICENSES_DIR / license_choice).read_text(encoding='utf-8')
        body = body.replace('{year}', YEAR).replace('{author}', author)
        Path('LICENSE').write_text(body, encoding='utf-8')
        header_file = LICENSES_DIR / f'{license_choice}.header'
        if header_file.exists():
            header = header_file.read_text(encoding='utf-8').replace('{year}', YEAR).replace('{author}', author)
    if LICENSES_DIR.exists():
        for path in sorted(LICENSES_DIR.iterdir(), reverse=True):
            path.unlink()
        LICENSES_DIR.rmdir()
    return header


def strip_leading_docstring(text: str) -> str:
    """Remove a leading module docstring from Python source."""
    return re.sub(r'\A\s*("""[^"]*"""|\'\'\'[^\']*\'\'\')\s*\n?', '', text)


def build_header(license_header, project_slug, author, email, license_choice, *, with_logging):
    """Compose the dunder-metadata header to prepend to a Python source file."""
    lines = []
    if license_header:
        lines.append(license_header.rstrip())
    lines.append(f'"""{project_slug}."""')
    lines.append('')
    if with_logging:
        lines.append('import logging')
        lines.append('')
    lines.append(f"__author__ = '{author} <{email}>'")
    lines.append("__docformat__ = 'google'")
    lines.append(f"__date__ = '{RELEASE_DATE}'")
    lines.append(f"__copyright__ = 'Copyright {YEAR}, {author}'")
    lines.append(f"__credits__ = ['{author}']")
    lines.append(f"__license__ = '{license_choice}'")
    lines.append(f"__maintainer__ = '{author}'")
    lines.append(f"__email__ = '<{email}>'")
    lines.append("__status__ = 'Development'")
    lines.append('')
    if with_logging:
        lines.append(f"LOGGER_BASENAME = '{project_slug}'")
        lines.append('LOGGER = logging.getLogger(LOGGER_BASENAME)')
        lines.append('LOGGER.addHandler(logging.NullHandler())')
        lines.append('')
        lines.append('')
    return '\n'.join(lines)


def prepend_header(filepath, license_header, project_slug, author, email, license_choice, *, with_logging=False):
    """Replace the leading module docstring of `filepath` with the standard header."""
    content = strip_leading_docstring(filepath.read_text(encoding='utf-8')).strip()
    header = build_header(license_header, project_slug, author, email, license_choice, with_logging=with_logging)
    result = f'{header}\n{content}\n' if content else f'{header.rstrip()}\n'
    filepath.write_text(result, encoding='utf-8')


def apply_headers_to_python_files(license_header, project_slug, author, email, license_choice):
    """Prepend the standard header to every .py file under src/ and tests/."""
    main_module = Path('src') / project_slug / f'{project_slug}.py'
    for directory in (Path('src'), Path('tests')):
        for py_file in directory.rglob('*.py'):
            prepend_header(
                py_file,
                license_header,
                project_slug,
                author,
                email,
                license_choice,
                with_logging=(py_file == main_module),
            )


def make_workflow_cmd_executable():
    """Set the executable bit on workflow.cmd so the Unix launcher works."""
    if WORKFLOW_CMD.exists():
        mode = os.stat(WORKFLOW_CMD).st_mode
        os.chmod(WORKFLOW_CMD, mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--license', required=True)
    parser.add_argument('--author', required=True)
    parser.add_argument('--email', required=True)
    parser.add_argument('--project-slug', required=True)
    args = parser.parse_args()

    license_header = install_license(args.license, args.author)
    apply_headers_to_python_files(license_header, args.project_slug, args.author, args.email, args.license)
    make_workflow_cmd_executable()


if __name__ == '__main__':
    main()
