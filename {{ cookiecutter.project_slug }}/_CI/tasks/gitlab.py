"""GitLab-specific helpers: container registry publish (kaniko) and release MR helpers."""

import base64
import json
import os
import re
from pathlib import Path
from typing import NamedTuple

from invoke import Context

from _CI.info import read as read_info

from .shared import execute


class RegistrySettings(NamedTuple):
    """Container registry credentials and image-prefix for the chosen host."""

    url: str
    user: str
    password_env: str
    image_prefix: str


def registry_settings() -> RegistrySettings:
    """Return GitLab container registry credentials sourced from GitLab CI env vars."""
    return RegistrySettings(
        url=os.environ['CI_REGISTRY'],
        user=os.environ['CI_REGISTRY_USER'],
        password_env='CI_REGISTRY_PASSWORD',
        image_prefix=os.environ['CI_REGISTRY_IMAGE'],
    )


def publish_deps_image(context: Context, tag: str) -> str:
    """Build and push the deps image via kaniko. Return the full image reference.

    kaniko is a daemonless builder that runs entirely in userspace — required
    on GitLab runners that don't allow privileged docker-in-docker or user
    namespaces (which rule out docker, buildah, and podman).
    """
    settings = registry_settings()
    image = f'{settings.image_prefix}-deps:{tag}'
    password = os.environ[settings.password_env]
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
    return image


def origin_slug(context: Context) -> str:
    """Return the project path (group/.../project) of the origin remote, or '' if not GitLab."""
    remote = context.run('git remote get-url origin', hide=True, warn=True)
    if remote is None or remote.failed:
        return ''
    url = remote.stdout.strip()
    match = re.match(
        r'(?:git@gitlab\.com:|https://gitlab\.com/)(.+?)(?:\.git)?/?$',
        url,
    )
    return match.group(1) if match else ''


def pr_create_url(context: Context, release_branch: str) -> str:
    """Compose the GitLab MR-create URL for a release branch, or '' if origin isn't GitLab."""
    slug = origin_slug(context)
    if not slug:
        return ''
    return f'https://gitlab.com/{slug}/-/merge_requests/new?merge_request[source_branch]={release_branch}'


def create_release_pr(context: Context, release_branch: str, new_version: str) -> str:
    """Open a release MR via the GitLab API. Currently a stub — returns ''.

    Implement against the GitLab Merge Requests API
    (https://docs.gitlab.com/ee/api/merge_requests.html#create-mr) when needed.
    """
    print('Auto-creation of GitLab merge requests is not yet implemented. See pr_create_url() for the manual URL.')
    return ''
