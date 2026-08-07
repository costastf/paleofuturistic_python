"""Maintenance tasks for the template repository itself."""

import importlib.util
import re
import shutil
import tarfile
import tempfile
import tomllib
import urllib.request
from pathlib import Path

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


VENDOR_DESTINATIONS = (
    PROJECT_ROOT_DIRECTORY / '_CI' / 'lib',
    PROJECT_ROOT_DIRECTORY / 'template' / '_CI' / 'lib',
)
# Copied verbatim out of the upstream archive. `vendor.txt` records what was resolved and
# `path_inject.patch` is what makes the launcher importable, so a tree without them cannot be
# rebuilt or explained.
VENDOR_ARTEFACTS = ('vendor', 'vendor.txt', 'patches/path_inject.patch')


def vendored_invoke_pin() -> dict:
    """Return the `[tool.vendored-invoke]` table, or abort if it is missing or incomplete."""
    data = tomllib.loads(REPO_PYPROJECT.read_text(encoding='utf-8'))
    pin = data.get('tool', {}).get('vendored-invoke', {})
    missing = [key for key in ('repository', 'version', 'commit') if not pin.get(key)]
    if missing:
        print(emojize_message(f'[tool.vendored-invoke] is missing {", ".join(missing)}.', success=False))
        raise SystemExit(1)
    return pin


def extract_vendor_tree(archive: Path, destination: Path) -> int:
    """Replace `destination`'s vendored artefacts with the ones inside `archive`. Return file count."""
    with tarfile.open(archive) as tar:
        # GitHub archives nest everything under a single `<repo>-<sha>/` directory.
        root = tar.getnames()[0].split('/')[0]
        with tempfile.TemporaryDirectory() as unpacked:
            # `filter='data'` refuses absolute paths, `..` traversal and device nodes. It is the
            # default from 3.14, but this repo also runs on 3.12.
            tar.extractall(unpacked, filter='data')
            source = Path(unpacked) / root / '_CI' / 'lib'
            for artefact in VENDOR_ARTEFACTS:
                target = destination / artefact
                if target.is_dir():
                    shutil.rmtree(target)
                elif target.exists():
                    target.unlink()
                target.parent.mkdir(parents=True, exist_ok=True)
                origin = source / artefact
                if origin.is_dir():
                    # `copytree` keeps the mode bits, which matters: bin/invoke must stay
                    # executable or every `./workflow.cmd` invocation exits 126.
                    shutil.copytree(origin, target)
                else:
                    shutil.copy2(origin, target)
            retarget_manifest(destination, upstream_name=project_name(Path(unpacked) / root / '_CI'))
    return sum(1 for path in (destination / 'vendor').rglob('*') if path.is_file())


def project_name(ci_directory: Path) -> str:
    """Return the `[project] name` of a `_CI/pyproject.toml`."""
    return tomllib.loads((ci_directory / 'pyproject.toml').read_text(encoding='utf-8'))['project']['name']


def retarget_manifest(destination: Path, upstream_name: str) -> None:
    """Rewrite vendor.txt's `# via <package>` attribution to name the local CI package.

    `uv pip compile` stamps the resolving project's name into every `# via` comment, so a
    manifest copied verbatim credits upstream's package — reintroducing a name this repository
    deliberately retired, and which an invariant still guards. Only the attribution is
    rewritten: re-resolving locally could pick different versions from the tree that was
    actually copied, and then the manifest would no longer describe it.
    """
    manifest = destination / 'vendor.txt'
    local_name = project_name(destination.parent)
    text = manifest.read_text(encoding='utf-8')
    if upstream_name != local_name:
        manifest.write_text(text.replace(upstream_name, local_name), encoding='utf-8')


@task(name='sync-vendor')
def sync_vendor(context):
    """Refresh both vendored invoke trees from the pinned upstream commit.

    The tree is built by schubergphilis/vendored_invoke and copied in verbatim — editing it
    here would silently detach it from the source it is supposed to mirror. Both copies move
    together so a generated project never gets a different tree from this repository.

    Refuses to run on a dirty working tree: the whole point is being able to read the resulting
    diff and see that nothing but the vendored files changed.
    """
    pin = vendored_invoke_pin()
    status = context.run('git status --porcelain', hide=True, warn=True)
    if status is None or status.stdout.strip():
        print(emojize_message('Working tree is dirty; commit or stash first.', success=False))
        raise SystemExit(1)
    url = f'https://codeload.github.com/{pin["repository"]}/tar.gz/{pin["commit"]}'
    print(f'Fetching {pin["repository"]} {pin["version"]} ({pin["commit"][:12]})')
    with tempfile.TemporaryDirectory() as workspace:
        archive = Path(workspace) / 'vendored_invoke.tar.gz'
        try:
            with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310
                archive.write_bytes(response.read())
        except OSError as exc:
            print(emojize_message(f'Could not fetch {url}: {exc}', success=False))
            raise SystemExit(1) from exc
        for destination in VENDOR_DESTINATIONS:
            count = extract_vendor_tree(archive, destination)
            print(f'  {destination.relative_to(PROJECT_ROOT_DIRECTORY)}/vendor -> {count} files')
    print(emojize_message(f'Vendored invoke synced to {pin["version"]}.'))
