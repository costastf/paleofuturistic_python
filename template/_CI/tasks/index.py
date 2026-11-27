"""Credentials for a fenced package index, minted from the job's OIDC token or taken from the environment.

Everything a project needs to live behind an index of its own is a variable its organisation
sets once, on a GitLab group or a GitHub organisation (ADR-0063, ADR-0064). `UV_DEFAULT_INDEX`
tells uv where to resolve and
`UV_PUBLISH_URL` where to upload, both read by uv itself. The `JFROG_*` variables let a
pipeline job trade the ID token its host minted for it for a short-lived Artifactory token, so
no stored secret exists anywhere. A developer behind the same fence sets `INDEX_USERNAME` and
`INDEX_PASSWORD` from their own identity token instead, and the same code hands those on. In
the open every variable is unset and nothing here runs.

`index.login` is the task: it writes the credentials into a netrc for the rest of a job, which
uv, tox-uv and pip all read, so every fetch after it authenticates (ADR-0064). The same identity
pulls the deps image's base image when the index host serves it (ADR-0065).
"""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import NamedTuple, cast
from urllib.parse import quote

from invoke import Collection, Context, Task, task

from .configuration import DEPS_IMAGE_BUILD_ARGS, DOCKERFILE_DEPS, INDEX_OIDC_PROVIDER
from .shared import execute, logged

# Artifactory's token exchange: RFC 8693, plus two fields of its own naming the identity provider
# to verify the token against and the project the resulting token is scoped to.
JFROG_TOKEN_PATH = '/access/api/v1/oidc/token'  # noqa: S105 — a URL path, not a secret
GRANT_TYPE = 'urn:ietf:params:oauth:grant-type:token-exchange'
SUBJECT_TOKEN_TYPE = 'urn:ietf:params:oauth:token-type:id_token'  # noqa: S105 — a type URN, not a secret
TIMEOUT_SECONDS = 30
NETRC_MODE = 0o600


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


def index_host(url: str) -> str:
    """Return the host a netrc entry for ``url`` names."""
    return url.partition('://')[2].partition('/')[0]


def registry_of(reference: str) -> str:
    """Return the registry an image reference names: everything before its first slash, port included."""
    return reference.partition('/')[0]


def fenced_registry(reference: str, index: str) -> str:
    """Return the registry of ``reference`` when the index host serves it, else ''.

    Artifactory serves its docker repositories under the host that serves the index, by path,
    by port or by subdomain, so a base image whose registry is that host or one of its
    subdomains is pulled with the index identity (ADR-0065). Any other registry, ghcr.io in the
    open among them, is never sent the credentials.
    """
    registry, host = registry_of(reference), index_host(index)
    name, root = registry.partition(':')[0], host.partition(':')[0]
    if root and (name == root or name.endswith(f'.{root}')):
        return registry
    return ''


def fetch_json(request: urllib.request.Request, what: str) -> dict:
    """Return the JSON document ``request`` answers with, over https only.

    Raises:
        IndexLoginError: When the URL is not https, the request fails, or the answer is not an object.

    """
    if not request.full_url.startswith('https://'):
        msg = f'refusing to send a token over anything but https: {request.full_url}'
        raise IndexLoginError(msg)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 — https enforced above
            answer = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        msg = f'{what} failed: {exc}'
        raise IndexLoginError(msg) from exc
    if not isinstance(answer, dict):
        msg = f'{what} answered with something other than an object'
        raise IndexLoginError(msg)
    return answer


def github_id_token(audience: str) -> str | None:
    """Return an ID token for ``audience`` from GitHub Actions, or None outside a job that can mint one.

    Actions injects ``ACTIONS_ID_TOKEN_REQUEST_URL`` and ``_TOKEN`` into a job with
    ``id-token: write``, and the token comes from one request to that URL. GitLab needs no such
    call: its ``id_tokens:`` block hands the token over as a variable.
    """
    url, bearer = setting('ACTIONS_ID_TOKEN_REQUEST_URL'), setting('ACTIONS_ID_TOKEN_REQUEST_TOKEN')
    if not (url and bearer and audience):
        return None
    request = urllib.request.Request(  # noqa: S310 — https enforced in fetch_json
        f'{url}&audience={quote(audience, safe="")}',
        headers={'Authorization': f'Bearer {bearer}', 'Accept': 'application/json'},
    )
    token = fetch_json(request, 'minting the ID token at GitHub Actions').get('value')
    if not token:
        msg = 'GitHub Actions answered without an ID token'
        raise IndexLoginError(msg)
    return token


def exchange_id_token(base_url: str, project: str, id_token: str, provider: str) -> str:
    """Trade the job's ID token for an Artifactory access token scoped to ``project``.

    Raises:
        IndexLoginError: When the exchange endpoint is not https, cannot be reached, or answers
            without a token.

    """
    url = f'{base_url.rstrip("/")}{JFROG_TOKEN_PATH}'
    body = {
        'grant_type': GRANT_TYPE,
        'subject_token_type': SUBJECT_TOKEN_TYPE,
        'subject_token': id_token,
        'provider_name': provider,
        'project_key': project,
    }
    request = urllib.request.Request(  # noqa: S310 — https enforced in fetch_json
        url,
        data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    token = fetch_json(request, f'the token exchange at {url}').get('access_token')
    if not token:
        msg = f'{url} answered without an access token'
        raise IndexLoginError(msg)
    return token


def index_login() -> IndexLogin | None:
    """Return the credentials for the organisation's index, or None where there is no fence.

    ``INDEX_USERNAME`` and ``INDEX_PASSWORD`` already in the environment win: a developer's own
    identity token, or the kaniko job reading what the plan job minted. Otherwise a job holding
    ``JFROG_URL`` and ``JFROG_PROJECT`` exchanges its ID token, the ``JFROG_ID_TOKEN`` GitLab's
    ``id_tokens:`` block minted or the one GitHub Actions mints on request; the username is the
    one Artifactory gives a project's CI identity, ``<project>-ci``. Nothing is printed but who
    logged in where.
    """
    if setting('INDEX_PASSWORD'):
        return IndexLogin(setting('INDEX_USERNAME'), setting('INDEX_PASSWORD'))
    base_url, project = setting('JFROG_URL'), setting('JFROG_PROJECT')
    if not (base_url and project):
        return None
    id_token = setting('JFROG_ID_TOKEN') or github_id_token(setting('JFROG_AUDIENCE'))
    if not id_token:
        return None
    token = exchange_id_token(base_url, project, id_token, setting('JFROG_PROVIDER') or INDEX_OIDC_PROVIDER)
    print(f'Index credentials minted for {project}-ci at {base_url} from the job ID token.')
    return IndexLogin(f'{project}-ci', token)


def build_environment() -> dict[str, str]:
    """Return the credential arguments of `Dockerfile.deps` by name, empty where there is no fence."""
    url, credentials = index_url(), index_login()
    if not url or credentials is None:
        return {}
    return dict(zip(DEPS_IMAGE_BUILD_ARGS, (url, credentials.username, credentials.password), strict=True))


def build_arguments(environment: dict[str, str]) -> str:
    """Return the ``--build-arg`` flags naming each variable in ``environment``, values left to the shell.

    The command line carries ``"$INDEX_PASSWORD"``, not the value, so the command the task
    echoes shows no secret; the environment the command runs in supplies it.
    """
    return ' '.join(f'--build-arg {name}="${name}"' for name in environment)


def deps_build_command(engine: str, base_image: str, image: str, environment: dict[str, str]) -> str:
    """Return the command that builds the deps image as ``image``, its credentials named from ``environment``."""
    flags = ' '.join(filter(None, (f'--build-arg BASE_IMAGE={base_image}', build_arguments(environment))))
    return f'{engine} build {flags} -f {DOCKERFILE_DEPS} -t {image} .'


def login_registry(context: Context, engine: str, registry: str, environment: dict[str, str]) -> None:
    """Log ``engine`` in to ``registry`` with the index credentials in ``environment``, read from the shell's own."""
    context.run(
        f'echo "$INDEX_PASSWORD" | {engine} login {registry} -u "$INDEX_USERNAME" --password-stdin',
        hide=True,
        env=environment,
    )
    print(f'Logged in to {registry} as {environment["INDEX_USERNAME"]} for the base image.')


def build_deps_image(context: Context, engine: str, base_image: str, image: str) -> None:
    """Build the deps image as ``image`` with ``engine``, logged in to the base image's registry if the fence serves it.

    Every builder of the image with an engine, by hand or in a job, goes through here so the
    credentials reach the builder stage the same way everywhere: named on the command line,
    supplied by the environment (ADR-0063). A base image the index host serves is pulled with
    the same identity, logged in before the build (ADR-0065); the kaniko job, which has no
    engine, gets the registry from `container.tag` and adds it to its own credential file.
    """
    environment = build_environment()
    registry = fenced_registry(base_image, environment.get('INDEX_URL', ''))
    if registry:
        login_registry(context, engine, registry, environment)
    execute(context, deps_build_command(engine, base_image, image, environment), env=environment)


def netrc_path() -> Path:
    """Return the netrc uv, pip and tox-uv read: ``NETRC`` when set, else the one in the home directory."""
    return Path(setting('NETRC') or Path.home() / '.netrc')


def write_netrc(host: str, credentials: IndexLogin) -> Path:
    """Add or replace the entry for ``host`` in the netrc, readable by its owner only."""
    path = netrc_path()
    existing = path.read_text(encoding='utf-8').splitlines() if path.exists() else []
    kept = [line for line in existing if not line.startswith(f'machine {host} ')]
    kept.append(f'machine {host} login {credentials.username} password {credentials.password}')
    path.write_text('\n'.join(kept) + '\n', encoding='utf-8')
    path.chmod(NETRC_MODE)
    return path


@task
@logged('index.login')
def login(context: Context) -> None:  # noqa: ARG001 — invoke always passes a Context to a @task
    """Log the job in to the organisation's package index for every fetch that follows.

    Writes a netrc entry for the index host from the credentials `index_login` finds, so uv,
    tox-uv and pip, all of which read it, authenticate for the rest of the job: the tox matrix
    installing every interpreter's environment, `uv build` fetching the build backend, the plan
    job installing uv. Prints where it logged in, never what with. In the open there is no
    index and nothing is written (ADR-0064).
    """
    url, credentials = index_url(), index_login()
    if not url or credentials is None:
        print('No fenced index configured; nothing to log in to.')
        return
    host = index_host(url)
    path = write_netrc(host, credentials)
    print(f'Logged in to {host} as {credentials.username}; credentials in {path} for this job.')


namespace = Collection('index')
namespace.add_task(cast(Task, login), default=True)
