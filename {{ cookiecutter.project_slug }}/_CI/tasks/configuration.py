"""Centralized constants for CI task definitions."""

import re
from pathlib import Path

PATHS = 'src/ _CI/tasks/ tests/'
SECURITY_OVERRIDE_ENV = '{{ cookiecutter.project_slug | upper }}_SECURITY_OVERRIDE'
SECURITY_OVERRIDES_FILE = Path('.security-overrides')

PYSCN_REPORTS_DIR = Path('reports')

IGNORE_PATTERN = re.compile(
    r'(?P<vulnerability_id>[A-Za-z0-9\-_]+)'
    r'(::(?P<expiration_date>\d{4}-\d{2}-\d{2}))?'
)

IMAGE_NAME = '{{ cookiecutter.project_slug }}-deps'
ACT_IMAGE_NAME = '{{ cookiecutter.project_slug }}-act'
QA_WORKFLOW = '.github/workflows/continuous-integration.yaml'

PROJECT_NAME = '{{ cookiecutter.project_slug }}'

{%- if cookiecutter.integrate_dependency_track %}
OWASP_DTRACK_SETTINGS = ('OWASP_DTRACK_URL', 'OWASP_DTRACK_API_KEY')
{%- endif %}
UV_PUBLISH_SETTINGS = ('UV_PUBLISH_URL', 'UV_PUBLISH_PASSWORD', 'UV_PUBLISH_USERNAME')
# Presence of both signals PyPI Trusted Publishing (OIDC) — `uv publish`
# exchanges them for a short-lived token, so the legacy UV_PUBLISH_* creds
# become unnecessary. See release.publish for the branching logic.
OIDC_ENV_VARS = ('ACTIONS_ID_TOKEN_REQUEST_URL', 'ACTIONS_ID_TOKEN_REQUEST_TOKEN')

SENTINEL = Path('_CI/.bootstrapped')
