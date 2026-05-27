"""Documentation task definitions for the parent template's ProperDocs site."""

import os
import webbrowser

from invoke import task

from _CI import PROJECT_ROOT_DIRECTORY, emojize_message

DOC_BUILD_CMD = (
    'uvx --from properdocs==1.6.7 '
    '--with properdocs-theme-mkdocs==1.6.7 '
    'properdocs build --strict'
)
SITE_INDEX = PROJECT_ROOT_DIRECTORY / 'site' / 'index.html'


def is_ci() -> bool:
    """Return True when running in a CI environment."""
    return bool(os.environ.get('CI'))


@task
def build(context):
    """Build the parent template's documentation site via ProperDocs."""
    result = context.run(DOC_BUILD_CMD, warn=True)
    if result is None or result.failed:
        print(emojize_message('Document build failed', success=False))
        raise SystemExit(1)
    print(emojize_message('Document build succeeded'))


@task
def view(context):  # noqa: ARG001
    """Open the built parent docs in the default browser. Skipped in CI."""
    if is_ci():
        return
    if not SITE_INDEX.exists():
        print(emojize_message(f'No site to view at {SITE_INDEX}; run build first.', success=False))
        raise SystemExit(1)
    webbrowser.open(SITE_INDEX.as_uri())


@task
def document(context):
    """Build the parent docs and open them in the default browser."""
    build(context)
    view(context)
