"""Build task definitions."""

from typing import cast

from invoke import Collection, Context, Task, task

from .secure import sbom
from .shared import logged, run, run_steps


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

    It also no longer records its outcome in a README badge. That badge said whether the last
    *local* build passed, which tells a reader nothing and could claim "passing" on a run that
    went on to fail; the CI badge now points at the host's own status endpoint, which is always
    current. See `document.update_pipeline_badge`.
    """
    run_steps(sbom, package)(context)


namespace = Collection('build')
namespace.add_task(cast(Task, build), default=True, name='all')
namespace.add_task(cast(Task, package))
