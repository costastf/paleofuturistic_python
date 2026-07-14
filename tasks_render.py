"""Copy-time render task for the copier template.

Runs once, after copier writes the project (cwd is the generated project root), via the
``_tasks`` hook in ``copier.yml`` gated to ``_copier_operation == 'copy'``. It performs the
steps that cannot be expressed declaratively:

* install the chosen LICENSE (substituting author/year tokens) and drop the staging dir,
* ensure ``workflow.cmd`` keeps its executable bit.

Version validation moved to the ``copier.yml`` validator; host/pages pruning moved to
conditional file/directory names. Copier passes the answers this task needs as CLI args.
"""

import argparse
import os
import stat
from datetime import date
from pathlib import Path

LICENSES_DIR = Path('licenses')
WORKFLOW_CMD = Path('workflow.cmd')

YEAR = str(date.today().year)


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
    make_workflow_cmd_executable()


if __name__ == '__main__':
    main()
