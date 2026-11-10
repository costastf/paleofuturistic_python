"""Build task definitions."""

from typing import cast

from invoke import Collection, Context, Task, task

from .secure import sbom
from .shared import execute, logged, run_steps


@task
@logged('build.package')
def package(context: Context) -> None:
    """Build the sdist and wheel, then check both the way PyPI and installers will read them.

    `uv build` writes `dist/`. `twine check --strict` renders the metadata and the README
    exactly as PyPI's upload endpoint does, so a long description PyPI would refuse fails here
    instead of mid-release. `check-wheel-contents` inspects the wheel itself: duplicate or
    stray files, a missing package, bytecode, an empty wheel.

    The globs name wheels and sdists explicitly. `release.attest` later writes
    `*.publish.attestation` files beside them, which are neither, and would fail both checks.
    """
    execute(context, 'uv build')
    execute(context, 'uv run twine check --strict dist/*.whl dist/*.tar.gz')
    execute(context, 'uv run check-wheel-contents dist/*.whl')


@task
@logged('build')
def build(context: Context) -> None:
    """Compose the SBOM and build the package; reports all failures before exiting.

    Deterministic from the tree: the SBOM comes from the lockfile, and `uv build` ships it
    inside the wheel. There is no dependency audit here on purpose — see `secure.sbom` — so a
    wheel can still be built when a fresh advisory lands. `release.dist` audits before it
    builds, which is where refusing to proceed actually protects someone.

    It records no outcome in a README badge: the CI badge points at the host's own status
    endpoint, which is always current. See `document.update_pipeline_badge`.
    """
    run_steps(sbom, package)(context)


namespace = Collection('build')
namespace.add_task(cast(Task, build), default=True, name='all')
namespace.add_task(cast(Task, package))
