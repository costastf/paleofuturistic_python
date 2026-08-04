"""Copy-time render task for the copier template.

Runs once, after copier writes the project (cwd is the generated project root), via the
``_tasks`` hook in ``copier.yml`` gated to ``_copier_operation == 'copy'``. It performs the
steps that cannot be expressed declaratively:

* install the chosen LICENSE (substituting author/year tokens) and drop the staging dir,
* stamp today's date as the dependency-quarantine boundary,
* stamp a fresh uv pin, so a project is current on the day it is created,
* ensure ``workflow.cmd`` keeps its executable bit.

Version validation moved to the ``copier.yml`` validator; host/pages pruning moved to
conditional file/directory names. Copier passes the answers this task needs as CLI args.
"""

import argparse
import importlib.util
import os
import re
import stat
from datetime import date
from pathlib import Path

LICENSES_DIR = Path('licenses')
WORKFLOW_CMD = Path('workflow.cmd')
PYPROJECT = Path('pyproject.toml')

TODAY = date.today()  # noqa: DTZ011
YEAR = str(TODAY.year)

EXCLUDE_NEWER_PATTERN = re.compile(r'^exclude-newer = "[^"]*"$', re.MULTILINE)
REQUIRES_PYTHON_PATTERN = re.compile(r'^requires-python = ">=([^"]+)"$', re.MULTILINE)

# Lets the template's own harness pin what generation stamps. Without it the ambient uv that
# CI installed — taken from the template's committed pin — would not satisfy a freshly stamped
# `required-version`, and every matrix cell would fail on the mismatch.
UV_VERSION_ENV = 'TEMPLATE_UV_VERSION'

# The resolver lives in the template so generated projects get it too; this script loads the
# very same file rather than carrying a second copy that could drift.
UV_RELEASE_MODULE = Path(__file__).resolve().parent / 'template' / '_CI' / 'uv_release.py'


def install_license(license_choice: str, author: str) -> None:
    """Copy the chosen LICENSE into place and drop the licenses/ staging directory."""
    if license_choice != 'None':
        body = (LICENSES_DIR / license_choice).read_text(encoding='utf-8')
        body = body.replace('{year}', YEAR).replace('{author}', author)
        Path('LICENSE').write_text(body, encoding='utf-8')
    if LICENSES_DIR.exists():
        for path in sorted(LICENSES_DIR.iterdir(), reverse=True):
            path.unlink()
        LICENSES_DIR.rmdir()


def stamp_dependency_quarantine_date() -> None:
    """Set ``[tool.uv] exclude-newer`` to today, fixing this project's resolution boundary.

    An absolute date is what stops a resolution changing under a project that has not
    changed. But a date baked into the template would hand every new project a boundary
    receding further into the past the longer the template goes unbumped — a project
    generated a year from now would start out pinned to year-old packages. Stamping it here
    gives each project a boundary that is current on its first day and frozen from then on,
    moving only when its owner moves it deliberately.

    Jinja cannot express this: copier exposes no clock, and ``jinja2-time`` would add a
    barely-maintained extension to the generation path for one substitution.
    """
    if not PYPROJECT.exists():
        return
    content = PYPROJECT.read_text(encoding='utf-8')
    updated, replaced = EXCLUDE_NEWER_PATTERN.subn(f'exclude-newer = "{TODAY.isoformat()}"', content)
    if replaced:
        PYPROJECT.write_text(updated, encoding='utf-8')


def load_uv_release():
    """Import the template's `_CI/uv_release.py` by path, or return None if unavailable.

    Stdlib-only by design, so importing it here — before the project has an environment — is
    safe. Returning None rather than raising keeps a missing or unreadable resolver from
    breaking generation outright; the caller falls back to the committed pin.
    """
    try:
        spec = importlib.util.spec_from_file_location('uv_release', UV_RELEASE_MODULE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (OSError, ImportError, AttributeError) as exc:
        print(f'note: could not load the uv resolver ({exc}); keeping the template default.')
        return None
    return module


def stamp_uv_version() -> None:
    """Pin the newest uv release that has been public for the cool-down period.

    The template carries a pin so it works offline, but that literal only ages between the
    maintainer's bumps — a project generated much later would otherwise start on a stale uv,
    and because `required-version` is an exact match a stale pin is actively obstructive rather
    than merely old. Resolving here means a project is current on the day it is created; from
    then on it is frozen and `./workflow.cmd develop.bump-uv` is how it moves.

    Never partially applied: the version and the image digest are written together or not at
    all, because a bumped tag beside a stale digest resolves to the digest and silently keeps
    the old image. Any failure — no network, a version the build backend lacks, an unexpected
    file shape — leaves the committed pin in place and says why, since generation must work
    offline and a silent fallback would mean freshness quietly stops happening.
    """
    if not PYPROJECT.exists():
        return
    uv_release = load_uv_release()
    if uv_release is None:
        return

    override = os.environ.get(UV_VERSION_ENV, '').strip()
    try:
        content = PYPROJECT.read_text(encoding='utf-8')
        pinned = uv_release.current_pin(content)
        # The image is per-Python, so the digest to fetch depends on this project's minimum.
        python_version = REQUIRES_PYTHON_PATTERN.search(content)
        if python_version is None:
            print(f'note: could not read requires-python; keeping uv {pinned}.')
            return
        if override:
            target, reason = override, f'pinned by {UV_VERSION_ENV}'
        else:
            target, released = uv_release.latest_eligible()
            reason = f'released {uv_release.describe_age(released)}'
        if uv_release.version_key(target) <= uv_release.version_key(pinned):
            why = (
                f'{UV_VERSION_ENV} asks for {target}'
                if override
                else f'nothing newer has cleared the {uv_release.COOLDOWN_DAYS}-day cool-down'
            )
            print(f'uv stays at {pinned}: {why}.')
            return
        if not uv_release.has_uv_build(target):
            print(f'note: uv-build {target} is not published; keeping uv {pinned}.')
            return
        digest = uv_release.image_digest(target, python_version.group(1))
        uv_release.apply_to_pyproject(PYPROJECT, target, digest)
    except uv_release.UvReleaseError as exc:
        print(f'note: keeping the template default uv pin — {exc}')
        return

    print(f'uv pinned at {target} ({reason}); was {pinned}.')
    if uv_release.crosses_minor(pinned, target):
        print(f'  this crosses a minor version ({pinned} → {target}); uv is pre-1.0, so behaviour may differ.')


def make_workflow_cmd_executable():
    """Set the executable bit on workflow.cmd so the Unix launcher works."""
    if WORKFLOW_CMD.exists():
        mode = os.stat(WORKFLOW_CMD).st_mode
        os.chmod(WORKFLOW_CMD, mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--license', required=True)
    parser.add_argument('--author', required=True)
    args = parser.parse_args()

    install_license(args.license, args.author)
    # Both stamps must precede the `uv lock` task in copier.yml: it resolves against the
    # quarantine boundary and runs `uvx uv@<version>` read back out of the file this writes.
    stamp_dependency_quarantine_date()
    stamp_uv_version()
    make_workflow_cmd_executable()


if __name__ == '__main__':
    main()
