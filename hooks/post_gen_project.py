import os
import stat
import sys

min_version = '{{ cookiecutter.min_python_version }}'
max_version = '{{ cookiecutter.max_python_version }}'
if max_version < min_version:
    print(f'ERROR: max_python_version ({max_version}) cannot be less than min_python_version ({min_version}).')
    sys.exit(1)

os.chmod('workflow.cmd', os.stat('workflow.cmd').st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
