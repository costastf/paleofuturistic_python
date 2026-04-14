"""Centralized constants for CI task definitions."""

import re
from pathlib import Path

PATHS = 'src/ _CI/tasks/ tests/'
SECURITY_OVERRIDE_ENV = '{{ cookiecutter.project_slug | upper }}_SECURITY_OVERRIDE'

PYSCN_REPORTS_DIR = Path('.pyscn/reports')

IGNORE_PATTERN = re.compile(
    r'(?P<vulnerability_id>[A-Za-z0-9\-_]+)'
    r'(::(?P<expiration_date>\d{4}-\d{2}-\d{2}))?'
)

IMAGE_NAME = '{{ cookiecutter.project_slug }}-deps'
ACT_IMAGE_NAME = '{{ cookiecutter.project_slug }}-act'
QA_WORKFLOW = '.github/workflows/continuous-integration.yaml'

PROJECT_NAME = '{{ cookiecutter.project_slug }}'

OWASP_DTRACK_SETTINGS = ('OWASP_DTRACK_URL', 'OWASP_DTRACK_API_KEY')

SENTINEL = Path('.bootstrapped')
