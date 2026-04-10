"""Documentation task definitions."""

from typing import cast

from invoke import Collection, Context, Task, task

from . import _exec, _logged, _run, _run_steps


@task
@_logged('document.build')
@_run('uv run mkdocs build')
def build(context: Context) -> None:
    """Build the documentation."""


@task
@_logged('document.open')
def open_(context: Context) -> None:
    """Open the built documentation in the default browser."""
    _exec(context, 'open site/index.html')


@task
@_logged('document')
def document(context: Context) -> None:
    """Build and open the documentation; reports all failures before exiting."""
    _run_steps(build, open_)(context)


namespace = Collection('document')
namespace.add_task(cast(Task, document), default=True)
namespace.add_task(cast(Task, build))
namespace.add_task(cast(Task, open_), name='open')
