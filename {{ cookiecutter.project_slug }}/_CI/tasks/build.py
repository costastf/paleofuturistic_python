"""Build task definitions."""

from typing import cast

from invoke import Collection, Context, Task, task

from . import _logged, _run, _run_steps
from .secure import secure


@task
@_logged('build.package')
@_run('uv build')
def package(context: Context) -> None:
    """Build the package."""


@task
@_logged('build')
def build(context: Context) -> None:
    """Run security checks and build the package; reports all failures before exiting."""
    _run_steps(secure, package)(context)


namespace = Collection('build')
namespace.add_task(cast(Task, build), default=True)
namespace.add_task(cast(Task, package))
