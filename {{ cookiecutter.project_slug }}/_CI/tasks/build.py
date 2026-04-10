"""Build task definitions."""

from typing import cast

from invoke import Collection, Context, Task, task

from ._shared import logged, run, run_steps
from .secure import secure


@task
@logged('build.package')
@run('uv build')
def package(context: Context) -> None:
    """Build the package."""


@task
@logged('build')
def build(context: Context) -> None:
    """Run security checks and build the package; reports all failures before exiting."""
    run_steps(secure, package)(context)


namespace = Collection('build')
namespace.add_task(cast(Task, build), default=True)
namespace.add_task(cast(Task, package))
