"""Container task definitions for building and running the deps image."""

import hashlib
import os
from pathlib import Path
from typing import cast

from invoke import Collection, Context, Task, task

from .shared import container_engine, execute, is_ci, logged


IMAGE_NAME = '{{ cookiecutter.project_slug }}-deps'
QA_WORKFLOW = '.github/workflows/continuous-integration.yaml'


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
            f'--pull=false '
            f'--container-daemon-socket /var/run/docker.sock',
        )
    else:
        execute(
            context,
            f'act push -W {QA_WORKFLOW} --secret-file .secrets '
            '--container-architecture linux/amd64 '
            '--pull=false '
            '--container-options "-v /var/run/docker.sock:/var/run/docker.sock"',
        )


@task
@logged('container.publish')
def publish(context: Context) -> None:
    """Build the deps image and publish to GHCR (CI) or keep it local.

    In CI (``GITHUB_ACTIONS=true``): logs into GHCR, checks whether the
    image already exists, builds and pushes only when missing.

    Locally: builds and tags the image without pushing anywhere.

    Writes the full image reference to ``.deps-image`` for downstream steps.
    """
    engine = container_engine()
    tag = hashlib.sha256(Path('uv.lock').read_bytes()).hexdigest()[:16]
    if is_ci() and not os.environ.get('ACT'):
        repository = os.environ['GITHUB_REPOSITORY']
        image = f'ghcr.io/{repository}-deps:{tag}'
        context.run(
            f'echo "$GITHUB_TOKEN" | {engine} login ghcr.io -u "$GITHUB_ACTOR" --password-stdin',
            hide=True,
        )
        result = context.run(f'{engine} manifest inspect {image}', hide=True, warn=True)
        if result and not result.failed:
            print(f'Image already exists: {image}')
        else:
            execute(context, f'{engine} build -f Dockerfile.deps -t {image} .')
            execute(context, f'{engine} push {image}')
    else:
        image = f'{IMAGE_NAME}:{tag}'
        result = context.run(f'{engine} image inspect {image}', hide=True, warn=True)
        if result and not result.failed:
            print(f'Image already exists: {image}')
        else:
            execute(context, f'{engine} build -f Dockerfile.deps -t {image} .')
    Path('.deps-image').write_text(image, encoding='utf-8')


@task
@logged('container')
def container(context: Context) -> None:
    """Build the deps image and run CI locally via act."""
    publish(context)
    act(context)


namespace = Collection('container')
namespace.add_task(cast(Task, container), default=True, name='all')
namespace.add_task(cast(Task, build))
namespace.add_task(cast(Task, publish))
namespace.add_task(cast(Task, act))
