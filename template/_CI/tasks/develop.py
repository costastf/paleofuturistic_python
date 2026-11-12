"""Development setup task definitions."""

import re
import tomllib
from datetime import date
from pathlib import Path
from typing import cast

from invoke import Collection, Context, Task, task

from _CI.info import read as read_info
from _CI.uv_release import (
    COOLDOWN_DAYS,
    UvReleaseError,
    apply_to_pyproject,
    crosses_minor,
    current_pin,
    describe_age,
    has_uv_build,
    image_digest,
    latest_eligible,
    version_key,
)

from .configuration import PYLOCK_FILE, UV_LOCK
from .shared import execute, logged, run

PYPROJECT = Path('pyproject.toml')
EXCLUDE_NEWER = re.compile(r'^exclude-newer = "(?P<boundary>[^"]*)"$', re.MULTILINE)
# A dependency entry pinned exactly: `"name==1.2"` or `"name[extra]==1.2"`, alone on its line,
# which is how every group in pyproject.toml spells its entries. Comments and the build
# backend's range are not matched.
PIN = re.compile(
    r'^(?P<lead>\s*")(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)(?P<extras>\[[^\]]*\])?'
    r'==(?P<version>[^"]+)"',
    re.MULTILINE,
)
# One line of `uv tree --outdated`: `├── ty v0.0.100 (group: lint) (latest: v0.0.101)`. Lines
# without a `latest` are current and do not match.
OUTDATED = re.compile(
    r'^[│├└─\s]*(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)(?:\[[^\]]*\])? v(?P<version>\S+)'
    r'.*\(latest: v(?P<latest>[^)]+)\)',
    re.MULTILINE,
)
# Pins `develop.refresh-deps` leaves alone. uv's version is tied to the base image's digest,
# and `develop.bump-uv` is what moves the two together.
HELD_BACK = frozenset({'uv'})


@task
@logged('develop.pre-commit-install')
@run('uv run pre-commit install')
def pre_commit_install(context: Context) -> None:
    """Install and activate pre-commit hooks."""


@task
@logged('develop.pre-commit')
def pre_commit(context: Context) -> None:
    """Run the commit-stage hooks exactly as git will run them.

    A dry run of your next commit: pre-commit's own view of the staged files, through the
    installed configuration. So it exercises what `preflight.staged` alone does not — that the
    `files:` filters select what you think, that `SKIP` is honoured, and that the other
    commit-stage hooks run.

    Nothing here writes; the hooks report, and `./workflow.cmd format` applies formatting. Nor
    is it the full check: ty, commitizen, the docs build, pyscn, the matrix and the derived
    files are on pre-push, and `./workflow.cmd preflight` runs everything.

    There is no whole-tree flag: the staged bundle reads the index rather than taking
    filenames, so there is nothing for `--all-files` to widen (ADR-0022). `./workflow.cmd
    preflight` checks every file in the project, which is what the whole backlog after
    installing hooks or a `copier update` calls for.

    Args:
        context: Invoke context.

    """
    execute(context, 'uv run pre-commit run')


@task
@logged('develop.bump-uv')
def bump_uv(context: Context, version: str = '') -> None:
    """Move every uv pin to the newest release that has been out for a week.

    The pinned uv version reaches four places in `pyproject.toml`, the last the base image's
    tag, and that tag carries a digest that has to move with it — a reference holding both resolves
    to the *digest*, so a bumped tag beside a stale digest silently keeps building the old
    image. This updates all of them together or none at all, then re-locks so `uv.lock` agrees.

    The version was current when this project was generated; it does not advance on its own
    (ADR-0008). Running this is how it moves.

    Args:
        context: Invoke context.
        version: Pin this version instead of resolving one. Skips the cool-down, so it is also
            how to take a release newer than the window allows.

    """
    try:
        pinned = current_pin(PYPROJECT.read_text(encoding='utf-8'))
        if version:
            target, age = version, 'requested explicitly'
        else:
            target, released = latest_eligible()
            age = f'released {describe_age(released)}'
        if version_key(target) <= version_key(pinned):
            print(f'uv {pinned} is already at or ahead of {target} ({age}); nothing to do.')
            return
        if not has_uv_build(target):
            print(f'uv {target} exists but uv-build {target} does not; refusing a version that cannot build.')
            raise SystemExit(1)
        digest = image_digest(target, read_info('info.python-version'))
        apply_to_pyproject(PYPROJECT, target, digest)
    except UvReleaseError as exc:
        print(f'Could not bump uv: {exc}')
        raise SystemExit(1) from None

    print(f'uv {pinned} → {target} ({age})')
    if crosses_minor(pinned, target):
        print(f'  NOTE: this crosses a minor version ({pinned} → {target}). uv is pre-1.0, so read')
        print('        its changelog before merging — minor releases are allowed to break behaviour.')
    print(f'  only releases older than {COOLDOWN_DAYS} days are chosen automatically')
    # `uv.lock` pins uv itself through the `test` group, so it has to be re-resolved or it
    # would still be holding the previous version.
    execute(context, 'uv lock')


def canonical(name: str) -> str:
    """Normalise ``name`` the way PyPI and uv compare it: lowercase, runs of `-`, `_` and `.` as one `-`."""
    return re.sub(r'[-_.]+', '-', name).lower()


def outdated_pins(tree: str) -> dict[str, str]:
    """Return ``{canonical name: newest version under the boundary}`` from ``uv tree --outdated``."""
    return {canonical(match['name']): match['latest'] for match in OUTDATED.finditer(tree)}


def move_pins(content: str, latest: dict[str, str]) -> tuple[str, list[tuple[str, str, str]]]:
    """Rewrite every exact pin in ``content`` that ``latest`` knows a newer version for.

    Returns the new content and ``[(name, old, new), ...]`` for what moved. Names in
    ``HELD_BACK`` stay where they are whatever ``latest`` says.
    """
    moved: list[tuple[str, str, str]] = []

    def replace(match: re.Match[str]) -> str:
        name = canonical(match['name'])
        target = latest.get(name)
        if target is None or name in HELD_BACK or target == match['version']:
            return match.group(0)
        moved.append((match['name'], match['version'], target))
        return f'{match["lead"]}{match["name"]}{match["extras"] or ""}=={target}"'

    return PIN.sub(replace, content), moved


def locked_versions() -> dict[str, str]:
    """``{name: version}`` for every package in ``uv.lock``."""
    packages = tomllib.loads(UV_LOCK.read_text(encoding='utf-8')).get('package', [])
    return {package['name']: package['version'] for package in packages}


@task
@logged('develop.refresh-deps')
def refresh_deps(context: Context, boundary: str = '') -> None:
    """Raise the resolution boundary to today and move every pin up to it.

    `[tool.uv] exclude-newer` is a fixed date, so nothing changes until someone moves it
    (ADR-0008). This is the move: the date goes to today, every exact pin in `pyproject.toml`
    goes to the newest release under the new date, and `uv lock --upgrade` brings the
    transitive closure with it. It prints what moved and stops short of committing, because
    the full QA cycle has to pass on the result first; the date, the pins and `uv.lock` then
    land in one commit, so the boundary and the pins never disagree (ADR-0042).

    `uv` is the one pin left alone: its version is tied to the base image's digest, and
    `develop.bump-uv` moves the two together. A newer uv is mentioned, not taken.

    Args:
        context: Invoke context.
        boundary: Date to set instead of today, as YYYY-MM-DD, to take releases up to a day
            that is not today, or to re-run a refresh at a boundary already chosen.

    """
    target = boundary or date.today().isoformat()  # noqa: DTZ011 - a calendar date, like the one it replaces
    try:
        date.fromisoformat(target)
    except ValueError:
        print(f'`{target}` is not a date of the form YYYY-MM-DD.')
        raise SystemExit(1) from None
    original = PYPROJECT.read_text(encoding='utf-8')
    match = EXCLUDE_NEWER.search(original)
    if not match:
        print('No `exclude-newer = "…"` line in pyproject.toml; nothing to raise.')
        raise SystemExit(1)
    previous = match['boundary']
    content = EXCLUDE_NEWER.sub(f'exclude-newer = "{target}"', original)
    PYPROJECT.write_text(content, encoding='utf-8')
    print(f'exclude-newer {previous} → {target}')

    # Asked under the new boundary, so "latest" means the newest release the date admits.
    tree = context.run('uv tree --depth 1 --all-groups --outdated', hide=True, warn=True)
    if tree.failed:
        PYPROJECT.write_text(original, encoding='utf-8')
        print(tree.stderr.strip())
        print('Could not read which pins are behind; pyproject.toml is as it was.')
        raise SystemExit(1)
    latest = outdated_pins(tree.stdout)
    content, moved = move_pins(content, latest)
    PYPROJECT.write_text(content, encoding='utf-8')
    for name, old, new in moved:
        print(f'  {name} {old} → {new}')
    if not moved:
        print('  every exact pin is already the newest release under the boundary')
    for name in sorted(HELD_BACK & latest.keys()):
        print(f'  {name} {latest[name]} is available; `./workflow.cmd develop.bump-uv` is what moves it')

    before = locked_versions()
    execute(context, 'uv lock --upgrade')
    after = locked_versions()
    direct = {canonical(name) for name, _, _ in moved}
    transitive = sorted(
        f'{name} {before[name]} → {after[name]}'
        for name in before.keys() & after.keys()
        if before[name] != after[name] and canonical(name) not in direct
    )
    if transitive:
        print(f'  {len(transitive)} transitive dependencies moved in uv.lock:')
        for line in transitive:
            print(f'    {line}')
    print('Run `./workflow.cmd preflight` and commit pyproject.toml and uv.lock together.')


@task
@logged('develop.pylock')
def pylock(context: Context) -> None:
    """Export the locked environment as a standard ``pylock.toml`` (PEP 751).

    `uv.lock` stays the source of truth: uv reads it, and every other task resolves from it.
    This writes the same pins, every dependency group included, in the format the packaging
    specs define, for tools that do not read `uv.lock` — another installer, an auditor, a
    platform that ingests lockfiles. It lands under `reports/`, which is gitignored: it is a
    derived file to hand over, not a second lock to keep in step.
    """
    PYLOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    execute(context, f'uv export --quiet --frozen --format pylock.toml --all-groups --output-file {PYLOCK_FILE}')
    print(f'Wrote {PYLOCK_FILE}.')


namespace = Collection('develop')
namespace.add_task(cast(Task, pre_commit_install), name='pre-commit-install')
namespace.add_task(cast(Task, pre_commit), name='pre-commit')
namespace.add_task(cast(Task, bump_uv), name='bump-uv')
namespace.add_task(cast(Task, refresh_deps), name='refresh-deps')
namespace.add_task(cast(Task, pylock))
