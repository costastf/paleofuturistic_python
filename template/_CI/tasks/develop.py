"""Development setup task definitions."""

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

from .shared import execute, logged, run

PYPROJECT = Path('pyproject.toml')


@task
@logged('develop.pre-commit-install')
@run('uv run pre-commit install')
def pre_commit_install(context: Context) -> None:
    """Install and activate pre-commit hooks."""


@task
@logged('develop.pre-commit')
def pre_commit(context: Context, all_files: bool = False) -> None:
    """Run the commit-stage hooks exactly as git will run them.

    A dry run of your next commit: pre-commit's own view of the staged files, through the
    installed configuration, so it exercises what `preflight.staged` alone does not — that the
    `sh -c … --paths="$*"` marshalling holds, that the `files:` filters select what you think
    they do, that `SKIP` is honoured, and the other commit-stage hooks run too.

    It used to pass `--all-files` unconditionally, which made the command behave differently
    from the hook it is named after: `--all-files` means every *tracked* file, not the staged
    ones. Now the default matches the hook and the flag widens it, the way `--write` widens
    `preflight` rather than the other way round.

    Nothing here writes: the hooks report, and `./workflow.cmd format` is what applies
    formatting. Neither is this the full check — ty, pyscn, the test matrix and the derived
    files are on pre-push, and `./workflow.cmd preflight` is the command that runs everything.

    Args:
        context: Invoke context.
        all_files: Run the same hooks over every tracked file instead of the staged ones.
            Useful right after installing hooks into an existing codebase, or after a
            `copier update`, to see the whole backlog at once.
    """
    execute(context, 'uv run pre-commit run --all-files' if all_files else 'uv run pre-commit run')


@task
@logged('develop.bump-uv')
def bump_uv(context: Context, version: str = '') -> None:
    """Move every uv pin to the newest release that has been out for a week.

    The pinned uv version reaches four places in `pyproject.toml` plus the base image's tag,
    and that tag carries a digest that has to move with it — a reference holding both resolves
    to the *digest*, so a bumped tag beside a stale digest silently keeps building the old
    image. This updates all of them together or none at all, then re-locks so `uv.lock` agrees.

    The version was current when this project was generated; it does not advance on its own.
    Running this is how it moves.

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


namespace = Collection('develop')
namespace.add_task(cast(Task, pre_commit_install), name='pre-commit-install')
namespace.add_task(cast(Task, pre_commit), name='pre-commit')
namespace.add_task(cast(Task, bump_uv), name='bump-uv')
