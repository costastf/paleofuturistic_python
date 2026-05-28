"""Documentation task definitions for the parent template's ProperDocs site."""

import os
import tomllib
import webbrowser

from invoke import task

from _CI import PROJECT_ROOT_DIRECTORY, emojize_message

SITE_INDEX = PROJECT_ROOT_DIRECTORY / 'site' / 'index.html'


def docs_versions() -> tuple[str, str]:
    """Return (properdocs, properdocs-theme-mkdocs) version pins from pyproject.toml."""
    data = tomllib.loads((PROJECT_ROOT_DIRECTORY / 'pyproject.toml').read_text(encoding='utf-8'))
    pd = data['tool']['properdocs']
    return pd['version'], pd['theme-mkdocs-version']


def properdocs_command(args: str) -> str:
    """Compose a `uvx properdocs …` invocation using the pinned versions."""
    properdocs_version, theme_version = docs_versions()
    return (
        f'uvx --from properdocs=={properdocs_version} '
        f'--with properdocs-theme-mkdocs=={theme_version} '
        f'properdocs {args}'
    )


def is_ci() -> bool:
    """Return True when running in a CI environment."""
    return bool(os.environ.get('CI'))


def run_properdocs(context, args: str, label: str) -> None:
    """Run a properdocs subcommand and emit a pass/fail status line."""
    result = context.run(properdocs_command(args), warn=True)
    if result is None or result.failed:
        print(emojize_message(f'{label} failed', success=False))
        raise SystemExit(1)
    print(emojize_message(f'{label} succeeded'))


@task
def build(context):
    """Build the parent template's documentation site via ProperDocs."""
    run_properdocs(context, 'build --strict', 'Document build')


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
def deploy_github(context):
    """Build the docs and push them to the gh-pages branch for GitHub Pages."""
    run_properdocs(context, 'gh-deploy --force', 'Document gh-deploy')


@task
def document(context):
    """Build the parent docs and open them in the default browser."""
    build(context)
    view(context)
