"""Maintenance tasks for the template repository itself."""

import importlib.util
import re

from invoke import task

from _CI import PROJECT_ROOT_DIRECTORY, emojize_message

TEMPLATE_PYPROJECT = PROJECT_ROOT_DIRECTORY / 'template' / 'pyproject.toml.jinja'
REPO_PYPROJECT = PROJECT_ROOT_DIRECTORY / 'pyproject.toml'
COPIER_YML = PROJECT_ROOT_DIRECTORY / 'copier.yml'

# The resolver ships inside the template so generated projects get it too; this repo loads the
# same file rather than keeping a second copy that could drift from it.
UV_RELEASE_MODULE = PROJECT_ROOT_DIRECTORY / 'template' / '_CI' / 'uv_release.py'


def load_uv_release():
    """Import `template/_CI/uv_release.py` by path.

    It is stdlib-only by design, so importing it outside a generated project is safe.
    """
    spec = importlib.util.spec_from_file_location('uv_release', UV_RELEASE_MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def supported_python_versions() -> list[str]:
    """Return the Python versions the template offers, from copier.yml's choices.

    Read rather than hardcoded so adding a Python version to `copier.yml` automatically
    extends the set of image digests this bumps.
    """
    import yaml

    data = yaml.safe_load(COPIER_YML.read_text(encoding='utf-8'))
    return list(data['min_python_version']['choices'])


def rewrite_template(text: str, version: str, digests: dict[str, str]) -> str:
    """Return the template's Jinja source with every uv pin and every image digest moved.

    The template's shape differs from a generated project's: its `base-image` line interpolates
    `{{ min_python_version }}` and looks up a Jinja map holding one digest per supported Python,
    so all of them move at once rather than the single digest a real project carries.

    Raises:
        RuntimeError: If any substitution matches nothing, rather than writing a half-bumped file.
    """
    substitutions = [
        ('test-group pin', r'"uv==[^"]+"', f'"uv=={version}"'),
        ('uv_build bound', r'(requires = \["uv_build>=[^,]+,<=)[^"]+(")', rf'\g<1>{version}\g<2>'),
        ('required-version', r'^required-version = "==[^"]+"$', f'required-version = "=={version}"'),
        (
            'base-image tag',
            r'^(base-image = "[^:]+:)[^"]*?(-python\{\{ min_python_version \}\}-trixie-slim)',
            rf'\g<1>{version}\g<2>',
        ),
    ]
    for python_version, digest in digests.items():
        substitutions.append(
            (
                f'digest for Python {python_version}',
                rf"^(\s*'{re.escape(python_version)}': ')sha256:[0-9a-f]+(',)$",
                rf'\g<1>{digest}\g<2>',
            )
        )

    updated = text
    for label, pattern, replacement in substitutions:
        updated, count = re.subn(pattern, replacement, updated, flags=re.MULTILINE)
        if not count:
            msg = f'no {label} found in {TEMPLATE_PYPROJECT.name}; refusing to write a half-bumped template'
            raise RuntimeError(msg)
    return updated


def rewrite_repo_pin(text: str, version: str) -> str:
    """Return this repo's own pyproject with its `required-version` moved.

    This is the version CI installs before generating anything, and the floor a generated
    project falls back to when PyPI is unreachable, so it tracks the template's pin.

    Raises:
        RuntimeError: If the pin is not found.
    """
    updated, count = re.subn(
        r'^required-version = "==[^"]+"$', f'required-version = "=={version}"', text, flags=re.MULTILINE
    )
    if not count:
        msg = f'no required-version found in {REPO_PYPROJECT.name}'
        raise RuntimeError(msg)
    return updated


@task(name='bump-uv')
def bump_uv(context, version=''):  # noqa: ARG001
    """Move every uv pin in the template and this repo to the newest week-old release.

    Ten values change together: four version literals plus the base image tag in the template,
    one digest per supported Python version, and this repo's own pin. A tag carrying a digest
    resolves to the digest, so a bumped tag beside a stale digest would silently keep building
    the old image — which is why they are never written separately.

    Args:
        context: Invoke context.
        version: Pin this version instead of resolving one, skipping the cool-down.
    """
    uv_release = load_uv_release()
    template_text = TEMPLATE_PYPROJECT.read_text(encoding='utf-8')

    try:
        pinned = uv_release.current_pin(template_text)
        if version:
            target, age = version, 'requested explicitly'
        else:
            target, released = uv_release.latest_eligible()
            age = f'released {uv_release.describe_age(released)}'
        if uv_release.version_key(target) <= uv_release.version_key(pinned):
            print(emojize_message(f'uv {pinned} is already at or ahead of {target} ({age}); nothing to do.'))
            return
        if not uv_release.has_uv_build(target):
            print(emojize_message(f'uv-build {target} does not exist; refusing a version that cannot build.', success=False))
            raise SystemExit(1)
        digests = {python: uv_release.image_digest(target, python) for python in supported_python_versions()}
    except uv_release.UvReleaseError as exc:
        print(emojize_message(f'Could not bump uv: {exc}', success=False))
        raise SystemExit(1) from None

    try:
        updated_template = rewrite_template(template_text, target, digests)
        updated_repo = rewrite_repo_pin(REPO_PYPROJECT.read_text(encoding='utf-8'), target)
    except RuntimeError as exc:
        print(emojize_message(str(exc), success=False))
        raise SystemExit(1) from None

    # Both files are rendered before either is written, so a failure above leaves the tree clean.
    TEMPLATE_PYPROJECT.write_text(updated_template, encoding='utf-8')
    REPO_PYPROJECT.write_text(updated_repo, encoding='utf-8')

    print(emojize_message(f'uv {pinned} → {target} ({age})'))
    print(f'  {len(digests)} image digests refreshed: {", ".join(sorted(digests))}')
    if uv_release.crosses_minor(pinned, target):
        print(f'  NOTE: this crosses a minor version ({pinned} → {target}). uv is pre-1.0, so read its')
        print('        changelog before merging — minor releases are allowed to break behaviour.')
    print('  run `./workflow.cmd test.matrix` before committing: it is the only thing that')
    print('  proves generated projects still work on the new version.')
