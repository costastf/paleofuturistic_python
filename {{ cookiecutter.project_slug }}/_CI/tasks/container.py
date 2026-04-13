"""Container task definitions for building and running the deps image."""

from pathlib import Path
from typing import cast

from invoke import Collection, Context, Task, task

from .shared import container_engine, execute, logged


IMAGE_NAME = '{{ cookiecutter.project_slug }}-deps'
QA_WORKFLOW = '.github/workflows/quality-assurance.yaml'


def _podman_socket(context: Context) -> str:
    """Discover the podman API socket path.

    Tries ``podman info`` first, then falls back to ``podman machine inspect``
    for macOS where podman runs inside a VM.

    Raises:
        SystemExit: If the socket path cannot be determined.
    """
    for cmd in (
        {%- raw %}
        'podman info --format "{{.Host.RemoteSocket.Path}}"',
        'podman machine inspect --format "{{.ConnectionInfo.PodmanSocket.Path}}"',
        {%- endraw %}
    ):
        result = context.run(cmd, hide=True, warn=True)
        if result and not result.failed and result.stdout.strip():
            socket = result.stdout.strip()
            if Path(socket).exists():
                return socket
    print('Could not determine podman socket path. Is podman machine running?')
    raise SystemExit(1)


@task
@logged('container.build')
def build(context: Context) -> None:
    """Build the dependency cache container image locally."""
    engine = container_engine()
    execute(context, f'{engine} build -f Dockerfile.deps -t {IMAGE_NAME}:latest .')


@task
@logged('container.act')
def act(context: Context) -> None:
    """Run the QA workflow locally using act."""
    engine = container_engine()
    if engine == 'podman':
        socket = _podman_socket(context)
        execute(
            context,
            f'DOCKER_HOST=unix://{socket} act push -W {QA_WORKFLOW} --secret-file .secrets '
            f'--container-architecture linux/amd64 '
            f'--container-daemon-socket {socket}',
        )
    else:
        execute(
            context,
            f'act push -W {QA_WORKFLOW} --secret-file .secrets '
            '--container-architecture linux/amd64 '
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
