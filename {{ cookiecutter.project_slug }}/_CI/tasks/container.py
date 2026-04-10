"""Container task definitions for building and running the deps Docker image."""

from typing import cast

from invoke import Collection, Context, Task, task

from .shared import execute, logged


IMAGE_NAME = '{{ cookiecutter.project_slug }}-deps'


@task
@logged('container.build')
def build(context: Context) -> None:
    """Build the dependency cache Docker image locally."""
    execute(context, f'docker build -f Dockerfile.deps -t {IMAGE_NAME}:latest .')


@task
@logged('container.act')
def act(context: Context) -> None:
    """Run the full CI workflow locally using act."""
    execute(context, 'act push --secret-file .secrets')


@task
@logged('container')
def container(context: Context) -> None:
    """Build the deps image and run CI locally via act."""
    build(context)
    act(context)


namespace = Collection('container')
namespace.add_task(cast(Task, container), default=True, name='all')
namespace.add_task(cast(Task, build))
namespace.add_task(cast(Task, act))
