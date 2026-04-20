"""Container task definitions for building and running the deps image."""

import hashlib
import os
from pathlib import Path
from typing import NamedTuple, cast

from invoke import Collection, Context, Task, task

from .configuration import ACT_IMAGE_NAME, IMAGE_NAME, QA_WORKFLOW
from .shared import container_engine, execute, is_ci, logged


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
    execute(context, f'{engine} build -f Dockerfile.act -t {ACT_IMAGE_NAME}:latest .')
    if engine == 'podman':
        socket = _podman_socket(context)
        execute(
            context,
            f'DOCKER_HOST=unix://{socket} act push -W {QA_WORKFLOW} --secret-file .secrets '
            f'--container-architecture linux/amd64 '
            f'--pull=false '
            f'--bind '
            f'--container-daemon-socket /var/run/docker.sock',
        )
    else:
        execute(
            context,
            f'act push -W {QA_WORKFLOW} --secret-file .secrets '
            '--container-architecture linux/amd64 '
            '--pull=false '
            '--bind '
            '--container-options "-v /var/run/docker.sock:/var/run/docker.sock"',
        )


class _RegistrySettings(NamedTuple):
    url: str
    user: str
    password_env: str
    image_prefix: str


def _ci_registry_settings() -> _RegistrySettings:
    """Detect CI platform and return container registry settings.

    Raises:
        SystemExit: If the CI platform cannot be determined.
    """
    if os.environ.get('GITHUB_ACTIONS'):
        repo = os.environ['GITHUB_REPOSITORY'].lower()
        return _RegistrySettings(
            url='ghcr.io',
            user=os.environ['GITHUB_ACTOR'],
            password_env='GITHUB_TOKEN',
            image_prefix=f'ghcr.io/{repo}',
        )
    if os.environ.get('GITLAB_CI'):
        return _RegistrySettings(
            url=os.environ['CI_REGISTRY'],
            user=os.environ['CI_REGISTRY_USER'],
            password_env='CI_REGISTRY_PASSWORD',
            image_prefix=os.environ['CI_REGISTRY_IMAGE'],
        )
    print('Unsupported CI platform.')
    raise SystemExit(1)


def _buildah_publish(settings: _RegistrySettings, image: str, context: Context) -> None:
    """Log into the registry with buildah and build+push the deps image."""
    context.run(
        f'echo "${settings.password_env}" | buildah login {settings.url} '
        f'-u "{settings.user}" --password-stdin',
        hide=True,
    )
    execute(context, f'buildah bud -f Dockerfile.deps -t {image} .')
    execute(context, f'buildah push {image}')


def _docker_publish(settings: _RegistrySettings, image: str, context: Context) -> None:
    """Log into the registry with the detected engine and build+push when missing."""
    engine = container_engine()
    context.run(
        f'echo "${settings.password_env}" | {engine} login {settings.url} '
        f'-u "{settings.user}" --password-stdin',
        hide=True,
    )
    result = context.run(f'{engine} manifest inspect {image}', hide=True, warn=True)
    if result and not result.failed:
        print(f'Image already exists: {image}')
    else:
        execute(context, f'{engine} build -f Dockerfile.deps -t {image} .')
        execute(context, f'{engine} push {image}')


@task
@logged('container.publish')
def publish(context: Context) -> None:
    """Build the deps image and publish to a container registry (CI) or keep it local.

    In GitLab CI: uses buildah (daemonless) to build and push — required where
    privileged docker-in-docker is unavailable.

    In GitHub Actions: logs into ghcr.io via the host docker, checks whether
    the image already exists, and builds and pushes only when missing.

    Locally: builds and tags the image without pushing anywhere.

    Writes the full image reference to ``.deps-image`` for downstream steps.
    """
    tag = hashlib.sha256(Path('uv.lock').read_bytes()).hexdigest()[:16]
    if is_ci() and not os.environ.get('ACT'):
        settings = _ci_registry_settings()
        image = f'{settings.image_prefix}-deps:{tag}'
        if os.environ.get('GITLAB_CI'):
            _buildah_publish(settings, image, context)
        else:
            _docker_publish(settings, image, context)
    else:
        image = f'{IMAGE_NAME}:{tag}'
        engine = container_engine()
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
