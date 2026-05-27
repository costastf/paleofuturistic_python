"""Container task definitions for building and running the deps image."""

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import NamedTuple, cast

from invoke import Collection, Context, Task, task

from _CI.info import read as read_info

from .configuration import IMAGE_NAME
from .shared import container_engine, execute, is_ci, logged


@task
@logged('container.build')
def build(context: Context) -> None:
    """Build the dependency cache container image locally."""
    engine = container_engine()
    base_image = read_info('info.base-image')
    execute(
        context,
        f'{engine} build --build-arg BASE_IMAGE={base_image} -f Dockerfile.deps -t {IMAGE_NAME}:latest .',
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
        # ghcr.io rejects uppercase in image paths, but GITHUB_REPOSITORY preserves org/repo case.
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


def kaniko_publish(settings: _RegistrySettings, password: str, image: str, context: Context) -> None:
    """Write registry credentials for kaniko and run the kaniko executor.

    kaniko is a daemonless builder that runs entirely in userspace — required
    on GitLab runners that don't allow privileged docker-in-docker or user
    namespaces (which rule out docker, buildah, and podman).
    """
    token = base64.b64encode(f'{settings.user}:{password}'.encode()).decode()
    config = {'auths': {settings.url: {'auth': token}}}
    config_path = Path('/kaniko/.docker/config.json')
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config), encoding='utf-8')
    base_image = read_info('info.base-image')
    execute(
        context,
        f'/kaniko/executor --dockerfile=Dockerfile.deps --context=. '
        f'--destination={image} --build-arg=BASE_IMAGE={base_image}',
    )


def _docker_publish(settings: _RegistrySettings, image: str, context: Context) -> None:
    """Log into the registry with the detected engine and build+push when missing."""
    engine = container_engine()
    context.run(
        f'echo "${settings.password_env}" | {engine} login {settings.url} -u "{settings.user}" --password-stdin',
        hide=True,
    )
    result = context.run(f'{engine} manifest inspect {image}', hide=True, warn=True)
    if result and not result.failed:
        print(f'Image already exists: {image}')
    else:
        base_image = read_info('info.base-image')
        execute(context, f'{engine} build --build-arg BASE_IMAGE={base_image} -f Dockerfile.deps -t {image} .')
        execute(context, f'{engine} push {image}')


@task
@logged('container.publish')
def publish(context: Context) -> None:
    """Build the deps image and publish to a container registry (CI) or keep it local.

    In GitLab CI: uses kaniko (daemonless) to build and push — required where
    privileged docker-in-docker and user namespaces are unavailable.

    In GitHub Actions: logs into ghcr.io via the host docker, checks whether
    the image already exists, and builds and pushes only when missing.

    Locally: builds and tags the image without pushing anywhere.

    Writes the full image reference to ``.deps-image`` for downstream steps.
    """
    tag = hashlib.sha256(Path('uv.lock').read_bytes()).hexdigest()[:16]
    if is_ci():
        settings = _ci_registry_settings()
        image = f'{settings.image_prefix}-deps:{tag}'
        if os.environ.get('GITLAB_CI'):
            kaniko_publish(settings, os.environ[settings.password_env], image, context)
        else:
            _docker_publish(settings, image, context)
    else:
        image = f'{IMAGE_NAME}:{tag}'
        engine = container_engine()
        result = context.run(f'{engine} image inspect {image}', hide=True, warn=True)
        if result and not result.failed:
            print(f'Image already exists: {image}')
        else:
            base_image = read_info('info.base-image')
            execute(context, f'{engine} build --build-arg BASE_IMAGE={base_image} -f Dockerfile.deps -t {image} .')
    Path('.deps-image').write_text(image, encoding='utf-8')


namespace = Collection('container')
namespace.add_task(cast(Task, publish), default=True, name='all')
namespace.add_task(cast(Task, build))
