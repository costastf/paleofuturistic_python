"""Container task definitions for building and running the deps image."""

from typing import cast

from invoke import Collection, Context, Task, task

from .shared import container_engine, execute, logged


IMAGE_NAME = '{{ cookiecutter.project_slug }}-deps'


@task
@logged('container.build')
def build(context: Context) -> None:
    """Build the dependency cache container image locally."""
    engine = container_engine()
    execute(context, f'{engine} build -f Dockerfile.deps -t {IMAGE_NAME}:latest .')


@task
@logged('container.act')
def act(context: Context) -> None:
    """Run the full CI workflow locally using act."""
    engine = container_engine()
    if engine == 'podman':
        result = context.run(
            {%- raw %}
            'podman info --format "{{.Host.RemoteSocket.Path}}"',
            {%- endraw %}
            hide=True, warn=True,
        )
        socket = result.stdout.strip() if result and not result.failed else '/run/podman/podman.sock'
        execute(
            context,
            f'DOCKER_HOST=unix://{socket} act push --secret-file .secrets '
            f'--container-options "-v {socket}:/var/run/docker.sock"',
        )
    else:
        execute(
            context,
            'act push --secret-file .secrets '
            '--container-options "-v /var/run/docker.sock:/var/run/docker.sock"',
        )


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
