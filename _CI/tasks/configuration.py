"""Centralized constants for CI task definitions."""

import shutil

PROJECT_SLUG = 'paleofuturistic_python_project'
IGNORE_PATTERNS = shutil.ignore_patterns('.git', '.venv', '__pycache__', '*.pyc', '.cruft.json')
QA_STEPS = ('format', 'lint', 'test', 'build', 'document')
