"""Stdlib-only helpers for resolving and applying a fresh uv pin.

uv is pinned exactly (`[tool.uv] required-version = "==X"`), and that one version reaches
five places in a project's `pyproject.toml`: the constraint itself, the `uv` entry in the
`test` group, the `uv_build` upper bound, and the base image's tag — which also carries a
digest that has to move with it. A reference carrying tag *and* digest resolves to the
**digest**, so a bumped tag left beside a stale digest silently keeps building the old image.
That is why nothing here rewrites a version without also having its digest in hand.

Imported by `_CI/tasks/develop.py` in a generated project, and by this template's own tooling
straight from source, so both share one implementation. Stdlib only — a generated project has
nothing but invoke vendored, and this runs before any environment exists.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# How long a release must have been public before this will pin it. Long enough that a
# same-day release yanked hours later never reaches anyone; short enough to stay current.
# Also what keeps a pinned uv resolvable under an `exclude-newer` stamped at generation:
# the version is always older than that boundary.
COOLDOWN_DAYS = 7

PYPI_RELEASES_URL = 'https://pypi.org/pypi/{package}/json'
GHCR_TOKEN_URL = 'https://ghcr.io/token?scope=repository:{repository}:pull&service=ghcr.io'
GHCR_MANIFEST_URL = 'https://ghcr.io/v2/{repository}/manifests/{reference}'
UV_IMAGE_REPOSITORY = 'astral-sh/uv'
IMAGE_TAG_TEMPLATE = '{version}-python{python_version}-trixie-slim'

MANIFEST_ACCEPT = ','.join(
    (
        'application/vnd.oci.image.index.v1+json',
        'application/vnd.docker.distribution.manifest.list.v2+json',
        'application/vnd.oci.image.manifest.v1+json',
    )
)

TIMEOUT_SECONDS = 30

# Release versions only. A pre-release (rc/beta/dev) is never an automatic choice.
RELEASE_VERSION_PATTERN = re.compile(r'^\d+(?:\.\d+)*$')


class UvReleaseError(Exception):
    """Anything that stopped a version or digest being resolved.

    Deliberately the only exception this module raises, so a caller has exactly one thing to
    catch when deciding between falling back and failing.
    """


def version_key(version: str) -> tuple[int, ...]:
    """Sort key for a dotted release version."""
    return tuple(int(part) for part in version.split('.'))


def is_release(version: str) -> bool:
    """Return True for a plain release version, False for pre-releases and oddities."""
    return bool(RELEASE_VERSION_PATTERN.match(version))


def fetch_json(url: str) -> dict:
    """GET and decode JSON, raising `UvReleaseError` on any failure."""
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        msg = f'could not read {url}: {exc}'
        raise UvReleaseError(msg) from exc


def released_versions(package: str = 'uv') -> dict[str, datetime]:
    """Return `{version: first upload time}` for every release of `package`.

    The *earliest* file upload dates a release: wheels for later platforms can trail the
    first by hours, and the cool-down should run from when the release first became usable.
    """
    data = fetch_json(PYPI_RELEASES_URL.format(package=package))
    releases = data.get('releases') or {}
    dated: dict[str, datetime] = {}
    for version, files in releases.items():
        if not files or not is_release(version):
            continue
        stamps = [file['upload_time_iso_8601'] for file in files if file.get('upload_time_iso_8601')]
        if not stamps:
            continue
        dated[version] = datetime.fromisoformat(min(stamps).replace('Z', '+00:00'))
    if not dated:
        msg = f'no dated releases found for {package}'
        raise UvReleaseError(msg)
    return dated


def latest_eligible(cooldown_days: int = COOLDOWN_DAYS, *, now: datetime | None = None) -> tuple[str, datetime]:
    """Return the newest release at least `cooldown_days` old, with its release time.

    Args:
        cooldown_days: Minimum age, in days, before a release may be pinned.
        now: Reference time; defaults to the current UTC time. Injected by tests.

    Raises:
        UvReleaseError: If PyPI cannot be read, or nothing has cleared the cool-down.
    """
    moment = now or datetime.now(timezone.utc)
    cutoff = moment - timedelta(days=cooldown_days)
    eligible = {version: released for version, released in released_versions().items() if released <= cutoff}
    if not eligible:
        msg = f'no uv release is older than {cooldown_days} days'
        raise UvReleaseError(msg)
    newest = max(eligible, key=version_key)
    return newest, eligible[newest]


def has_uv_build(version: str) -> bool:
    """Return True when `uv-build` published `version` too.

    The build backend is pinned to the same number as uv. They have tracked each other so
    far, which is exactly why it is worth checking rather than assuming — a bump that
    outpaces `uv-build` would leave an unbuildable project.
    """
    return version in released_versions('uv-build')


def image_digest(version: str, python_version: str) -> str:
    """Return the manifest digest for uv's `version` image built on `python_version`.

    Resolved so the pinned image reference cannot be repointed upstream. Anonymous pull
    token, then a HEAD for the digest header — no image is downloaded.

    Raises:
        UvReleaseError: If the token or the manifest cannot be fetched.
    """
    token = fetch_json(GHCR_TOKEN_URL.format(repository=UV_IMAGE_REPOSITORY)).get('token')
    if not token:
        msg = 'ghcr did not return a pull token'
        raise UvReleaseError(msg)
    tag = IMAGE_TAG_TEMPLATE.format(version=version, python_version=python_version)
    request = urllib.request.Request(  # noqa: S310
        GHCR_MANIFEST_URL.format(repository=UV_IMAGE_REPOSITORY, reference=tag),
        method='HEAD',
        headers={'Authorization': f'Bearer {token}', 'Accept': MANIFEST_ACCEPT},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            digest = response.headers.get('Docker-Content-Digest')
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        msg = f'could not resolve a digest for {tag}: {exc}'
        raise UvReleaseError(msg) from exc
    if not digest or not digest.startswith('sha256:'):
        msg = f'ghcr returned no usable digest for {tag}'
        raise UvReleaseError(msg)
    return digest


def crosses_minor(current: str, candidate: str) -> bool:
    """Return True when moving `current` → `candidate` changes the major or minor version.

    uv is pre-1.0, so a minor bump is allowed to break things. Callers announce this rather
    than refusing it — the point is that nobody should merge such a bump unaware.
    """
    return version_key(current)[:2] != version_key(candidate)[:2]


def describe_age(released: datetime, *, now: datetime | None = None) -> str:
    """Human-readable age of a release, for task output."""
    days = ((now or datetime.now(timezone.utc)) - released).days
    return 'today' if days == 0 else f'{days} day{"s" if days != 1 else ""} ago'


def current_pin(pyproject: str) -> str:
    """Return the uv version a concrete `pyproject.toml`'s text currently pins.

    Raises:
        UvReleaseError: If `[tool.uv] required-version` is absent or not an exact pin.
    """
    match = re.search(r'^required-version = "==([^"]+)"$', pyproject, re.MULTILINE)
    if not match:
        msg = 'could not find an exact [tool.uv] required-version to bump from'
        raise UvReleaseError(msg)
    return match.group(1)


def rewrite_pins(pyproject: str, version: str, digest: str) -> str:
    """Return `pyproject` text with every uv pin moved to `version`, and the image digest set.

    Rewrites, in order: the `test` group's `uv==` entry, the `uv_build` upper bound, the
    `required-version` constraint, and the base image's tag plus digest. The digest is applied
    in the same pass as the tag on purpose — see the module docstring for why splitting them
    is dangerous.

    Raises:
        UvReleaseError: If any of the four substitutions matches nothing, which would leave a
            half-bumped file.
    """
    substitutions = (
        ('test-group pin', r'"uv==[^"]+"', f'"uv=={version}"'),
        ('uv_build bound', r'(requires = \["uv_build>=[^,]+,<=)[^"]+(")', rf'\g<1>{version}\g<2>'),
        ('required-version', r'^required-version = "==[^"]+"$', f'required-version = "=={version}"'),
        (
            'base-image reference',
            r'^base-image = "([^:]+):[^"]*(-python\d+\.\d+-trixie-slim)@sha256:[0-9a-f]+"$',
            rf'base-image = "\g<1>:{version}\g<2>@{digest}"',
        ),
    )
    updated = pyproject
    for label, pattern, replacement in substitutions:
        updated, count = re.subn(pattern, replacement, updated, flags=re.MULTILINE)
        if not count:
            msg = f'no {label} found to update; refusing to write a half-bumped pyproject.toml'
            raise UvReleaseError(msg)
    return updated


def apply_to_pyproject(path: Path, version: str, digest: str) -> None:
    """Move every uv pin in the `pyproject.toml` at `path` to `version`.

    Raises:
        UvReleaseError: If the file cannot be read, or any pin is missing. Nothing is written
            unless every substitution succeeded.
    """
    try:
        original = path.read_text(encoding='utf-8')
    except OSError as exc:
        msg = f'could not read {path}: {exc}'
        raise UvReleaseError(msg) from exc
    updated = rewrite_pins(original, version, digest)
    if updated != original:
        path.write_text(updated, encoding='utf-8')
