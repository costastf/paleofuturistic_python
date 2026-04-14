"""Documentation task definitions."""

from typing import cast

from invoke import Collection, Context, Task, task

from .shared import execute, is_ci, logged, open_command, run, run_steps


@task
@logged('document.build')
@run('uv run mkdocs build')
def build(context: Context) -> None:
    """Build the documentation."""


@task
@logged('document.view')
def view(context: Context) -> None:
    """Open the built documentation in the default browser. Skipped in CI."""
    if is_ci():
        return
    execute(context, f'{open_command()} site/index.html')


@task
@logged('document')
def document(context: Context) -> None:
    """Build and open the documentation; reports all failures before exiting."""
    run_steps(build, view)(context)


namespace = Collection('document')
namespace.add_task(cast(Task, document), default=True, name='all')
namespace.add_task(cast(Task, build))
namespace.add_task(cast(Task, view))
