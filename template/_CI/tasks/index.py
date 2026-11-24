"""Credentials for a fenced package index, minted from the job's OIDC token or taken from the environment.

Everything a project needs to live behind an index of its own is a variable its organisation
sets once, at group level (ADR-0063). `UV_DEFAULT_INDEX` tells uv where to resolve and
`UV_PUBLISH_URL` where to upload, both read by uv itself. The `JFROG_*` variables let a
pipeline job trade the ID token GitLab minted for it for a short-lived Artifactory token, so no
stored secret exists anywhere. A developer behind the same fence sets `INDEX_USERNAME` and
`INDEX_PASSWORD` from their own identity token instead, and the same code hands those on. In
the open every variable is unset and nothing here runs.
"""

import json
import os
import urllib.error
import urllib.request
from typing import NamedTuple

from .configuration import DEPS_IMAGE_BUILD_ARGS, DOCKERFILE_DEPS

# Artifactory's token exchange: RFC 8693, plus two fields of its own naming the identity provider
# to verify the token against and the project the resulting token is scoped to.
JFROG_TOKEN_PATH = '/access/api/v1/oidc/token'  # noqa: S105 — a URL path, not a secret
GRANT_TYPE = 'urn:ietf:params:oauth:grant-type:token-exchange'
SUBJECT_TOKEN_TYPE = 'urn:ietf:params:oauth:token-type:id_token'  # noqa: S105 — a type URN, not a secret
DEFAULT_PROVIDER = 'gitlab'
TIMEOUT_SECONDS = 30


class IndexLoginError(RuntimeError):
    """The token exchange did not produce a token."""


class IndexLogin(NamedTuple):
    """A username and password the index accepts, however they were obtained."""

    username: str
    password: str


def setting(name: str) -> str:
    """Return the environment variable ``name`` stripped, absent and empty being the same thing."""
    return os.environ.get(name, '').strip()


def index_url() -> str:
    """Return the index the deps image resolves from: ``INDEX_URL``, else ``UV_DEFAULT_INDEX``, else nothing."""
    return setting('INDEX_URL') or setting('UV_DEFAULT_INDEX')


def exchange_id_token(base_url: str, project: str, id_token: str, provider: str) -> str:
    """Trade the job's ID token for an Artifactory access token scoped to ``project``.

    Raises:
        IndexLoginError: When the exchange endpoint is not https, cannot be reached, or answers
            without a token.

    """
    url = f'{base_url.rstrip("/")}{JFROG_TOKEN_PATH}'
    if not url.startswith('https://'):
        msg = f'refusing to send an ID token over anything but https: {url}'
        raise IndexLoginError(msg)
    body = {
        'grant_type': GRANT_TYPE,
        'subject_token_type': SUBJECT_TOKEN_TYPE,
        'subject_token': id_token,
        'provider_name': provider,
        'project_key': project,
    }
    request = urllib.request.Request(  # noqa: S310 — https enforced above
        url,
        data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            answer = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        msg = f'the token exchange at {url} failed: {exc}'
        raise IndexLoginError(msg) from exc
    token = answer.get('access_token') if isinstance(answer, dict) else None
    if not token:
        msg = f'{url} answered without an access token'
        raise IndexLoginError(msg)
    return token


def index_login() -> IndexLogin | None:
    """Return the credentials for the organisation's index, or None where there is no fence.

    ``INDEX_USERNAME`` and ``INDEX_PASSWORD`` already in the environment win: a developer's own
    identity token, or the kaniko job reading what the plan job minted. Otherwise a job holding
    ``JFROG_URL``, ``JFROG_PROJECT`` and the ``JFROG_ID_TOKEN`` its ``id_tokens:`` block minted
    exchanges that token; the username is the one Artifactory gives a project's CI identity,
    ``<project>-ci``. Nothing is printed but who logged in where.
    """
    if setting('INDEX_PASSWORD'):
        return IndexLogin(setting('INDEX_USERNAME'), setting('INDEX_PASSWORD'))
    base_url, project, id_token = setting('JFROG_URL'), setting('JFROG_PROJECT'), setting('JFROG_ID_TOKEN')
    if not (base_url and project and id_token):
        return None
    token = exchange_id_token(base_url, project, id_token, setting('JFROG_PROVIDER') or DEFAULT_PROVIDER)
    print(f'Index credentials minted for {project}-ci at {base_url} from the job ID token.')
    return IndexLogin(f'{project}-ci', token)


def build_environment() -> dict[str, str]:
    """Return the credential arguments of `Dockerfile.deps` by name, empty where there is no fence."""
    url, login = index_url(), index_login()
    if not url or login is None:
        return {}
    return dict(zip(DEPS_IMAGE_BUILD_ARGS, (url, login.username, login.password), strict=True))


def build_arguments(environment: dict[str, str]) -> str:
    """Return the ``--build-arg`` flags naming each variable in ``environment``, values left to the shell.

    The command line carries ``"$INDEX_PASSWORD"``, not the value, so the command the task
    echoes shows no secret; the environment the command runs in supplies it.
    """
    return ' '.join(f'--build-arg {name}="${name}"' for name in environment)


def deps_build_command(engine: str, base_image: str, image: str) -> tuple[str, dict[str, str]]:
    """Return the command that builds the deps image as ``image``, and the environment it runs in.

    Every builder of the image, by hand or in a pipeline job with an engine, goes through here
    so the credentials reach the builder stage the same way everywhere: named on the command
    line, supplied by the environment.
    """
    environment = build_environment()
    flags = ' '.join(filter(None, (f'--build-arg BASE_IMAGE={base_image}', build_arguments(environment))))
    return f'{engine} build {flags} -f {DOCKERFILE_DEPS} -t {image} .', environment
