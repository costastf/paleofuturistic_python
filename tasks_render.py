"""Copy-time render task for the copier template.

Runs once, after copier writes the project (cwd is the generated project root), via the
``_tasks`` hook in ``copier.yml`` gated to ``_copier_operation == 'copy'``. It performs the
steps that cannot be expressed declaratively:

* install the chosen LICENSE (substituting author/year tokens) and drop the staging dir,
* stamp today's date as the dependency-quarantine boundary,
* ensure ``workflow.cmd`` keeps its executable bit.

Version validation moved to the ``copier.yml`` validator; host/pages pruning moved to
conditional file/directory names. Copier passes the answers this task needs as CLI args.
"""

import argparse
import os
import re
import stat
from datetime import date
from pathlib import Path

LICENSES_DIR = Path('licenses')
WORKFLOW_CMD = Path('workflow.cmd')
PYPROJECT = Path('pyproject.toml')

TODAY = date.today()  # noqa: DTZ011
YEAR = str(TODAY.year)

EXCLUDE_NEWER_PATTERN = re.compile(r'^exclude-newer = "[^"]*"$', re.MULTILINE)


def install_license(license_choice: str, author: str) -> None:
    """Copy the chosen LICENSE into place and drop the licenses/ staging directory."""
    if license_choice != 'None':
        body = (LICENSES_DIR / license_choice).read_text(encoding='utf-8')
        body = body.replace('{year}', YEAR).replace('{author}', author)
        Path('LICENSE').write_text(body, encoding='utf-8')
    if LICENSES_DIR.exists():
        for path in sorted(LICENSES_DIR.iterdir(), reverse=True):
            path.unlink()
        LICENSES_DIR.rmdir()


def stamp_dependency_quarantine_date() -> None:
    """Set ``[tool.uv] exclude-newer`` to today, fixing this project's resolution boundary.

    An absolute date is what stops a resolution changing under a project that has not
    changed. But a date baked into the template would hand every new project a boundary
    receding further into the past the longer the template goes unbumped — a project
    generated a year from now would start out pinned to year-old packages. Stamping it here
    gives each project a boundary that is current on its first day and frozen from then on,
    moving only when its owner moves it deliberately.

    Jinja cannot express this: copier exposes no clock, and ``jinja2-time`` would add a
    barely-maintained extension to the generation path for one substitution.
    """
    if not PYPROJECT.exists():
        return
    content = PYPROJECT.read_text(encoding='utf-8')
    updated, replaced = EXCLUDE_NEWER_PATTERN.subn(f'exclude-newer = "{TODAY.isoformat()}"', content)
    if replaced:
        PYPROJECT.write_text(updated, encoding='utf-8')


def make_workflow_cmd_executable():
    """Set the executable bit on workflow.cmd so the Unix launcher works."""
    if WORKFLOW_CMD.exists():
        mode = os.stat(WORKFLOW_CMD).st_mode
        os.chmod(WORKFLOW_CMD, mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--license', required=True)
    parser.add_argument('--author', required=True)
    args = parser.parse_args()

    install_license(args.license, args.author)
    # Must precede the `uv lock` task in copier.yml, which resolves against this boundary.
    stamp_dependency_quarantine_date()
    make_workflow_cmd_executable()


if __name__ == '__main__':
    main()
