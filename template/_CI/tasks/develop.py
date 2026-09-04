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
@run('uv run pre-commit run --all-files')
def pre_commit(context: Context) -> None:
    """Run the commit-stage hooks over the entire codebase.

    This is the hooks' own view of the world — pre-commit runs the commit stage by default, so
    what this covers is the staged bundle (formatting, ruff, pylint, complexipy) widened to
    every file. It is not the full check: ty, pyscn, the test suite and the derived files live
    on pre-push. `./workflow.cmd preflight` is the command that runs everything.

    `--all-files` means every *tracked* file, not the staged ones. It writes nothing, as the
    hooks no longer do: `./workflow.cmd format` is what applies formatting, being the command
    named for it.

    pre-commit also splits a long file list across several concurrent invocations of the hook
    — six for a 23-file project — so the single-startup shape of the collapsed hook applies
    per partition here. Measured as a wash against forcing `require_serial`, 9.4s versus
    10.1s, because the concurrency pays for the extra startups; a normal commit stages few
    enough files to be one invocation anyway.
    """


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
