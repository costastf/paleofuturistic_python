import os
import shutil
import stat
import sys
from pathlib import Path

min_version = '{{ cookiecutter.min_python_version }}'
max_version = '{{ cookiecutter.max_python_version }}'
if max_version < min_version:
    print(f'ERROR: max_python_version ({max_version}) cannot be less than min_python_version ({min_version}).')
    sys.exit(1)

license_choice = '{{ cookiecutter.license }}'
licenses_dir = Path('licenses')
if license_choice != 'None':
    shutil.copy2(licenses_dir / license_choice, 'LICENSE')
shutil.rmtree(licenses_dir)

os.chmod('workflow.cmd', os.stat('workflow.cmd').st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
