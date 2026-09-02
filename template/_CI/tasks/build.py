"""Build task definitions."""

from pathlib import Path
from typing import cast

from invoke import Collection, Context, Task, task

from .secure import sbom
from .shared import apply_badge, logged, note, run, run_steps

STATUS_COLORS = {'passing': 'brightgreen', 'failing': 'red'}


def update_build_badge(status: str) -> None:
    """Record the outcome of a build run in the README's build badge.

    Unlike the badges ``preflight`` owns, this one is not derived from a report that can be
    recomputed later — it records what happened when ``build`` last ran. So there is nothing
    for ``preflight --check`` to verify it against, and it is written here, by the task that
    knows the answer. It still goes through ``apply_badge`` so that every write to README.md
    in this tree happens in exactly one place.
    """
    note(
        apply_badge(
            Path('README.md'),
            r'(\[!\[Build\]\(https://img\.shields\.io/badge/build-)[^)]+(\))',
            rf'\g<1>{status}-{STATUS_COLORS.get(status, "lightgrey")}\2',
            label='build badge',
            detail=status,
            write=True,
        )
    )


@task
@logged('build.package')
@run('uv build')
def package(context: Context) -> None:
    """Build the package."""


@task
@logged('build')
def build(context: Context) -> None:
    """Compose the SBOM and build the package; reports all failures before exiting.

    Deterministic from the tree: the SBOM comes from the lockfile, and `uv build` ships it
    inside the wheel. There is no dependency audit here on purpose — see `secure.sbom` — so a
    wheel can still be built when a fresh advisory lands. `release.dist` audits before it
    builds, which is where refusing to proceed actually protects someone.
    """
    try:
        run_steps(sbom, package)(context)
    except SystemExit:
        update_build_badge('failing')
        raise
    update_build_badge('passing')


namespace = Collection('build')
namespace.add_task(cast(Task, build), default=True, name='all')
namespace.add_task(cast(Task, package))
