"""Invariants over the fenced-index credentials: where they come from, what they never do (ADR-0063, ADR-0064)."""

import json
import stat
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple, Self

import pytest

from .support import exec_from, function_source

INDEX_NAMES = (
    'setting',
    'index_url',
    'index_host',
    'fetch_json',
    'github_id_token',
    'exchange_id_token',
    'index_login',
    'registry_of',
    'fenced_registry',
    'build_environment',
    'build_arguments',
    'deps_build_command',
    'login_registry',
    'build_deps_image',
    'netrc_path',
    'write_netrc',
    'login',
    'IndexLogin',
    'IndexLoginError',
    'JFROG_TOKEN_PATH',
    'GRANT_TYPE',
    'SUBJECT_TOKEN_TYPE',
    'TIMEOUT_SECONDS',
    'NETRC_MODE',
)
FENCE = {
    'UV_DEFAULT_INDEX': 'https://pkgs.example.com/artifactory/api/pypi/internal/simple',
    'JFROG_URL': 'https://pkgs.example.com/',
    'JFROG_PROJECT': 'widget',
}


class Response:
    """What `urlopen` hands back: a context manager with a `read`."""

    def __init__(self, body: bytes) -> None:
        """Hold the bytes the fake endpoint answers with."""
        self.body = body

    def __enter__(self) -> Self:
        """Enter the `with` the module opens the response in."""
        return self

    def __exit__(self, *_exc: object) -> bool:
        """Leave it."""
        return False

    def read(self) -> bytes:
        """Return the body."""
        return self.body


class FakeRequest:
    """The slice of `urllib.request.Request` the exchange builds."""

    def __init__(self, url: str, data: bytes | None = None, headers: dict | None = None, method: str = 'GET') -> None:
        """Record what the exchange sends."""
        self.full_url, self.data, self.headers, self.method = url, data, headers or {}, method


def index_helpers(project, cell, environment, *, answers=()):
    """Exec the index module's functions against a fake environment and fake endpoints answering in order."""
    source = (project / '_CI' / 'tasks' / 'index.py').read_text(encoding='utf-8')
    requests = []
    replies = list(answers)

    def urlopen(request, timeout):
        requests.append((request, timeout))
        return Response(json.dumps(replies.pop(0) if replies else {}).encode('utf-8'))

    printed = []
    executed = []
    helpers = exec_from(
        source,
        *INDEX_NAMES,
        execute=lambda _context, command, env=None: executed.append((command, dict(env or {}))),
        os=SimpleNamespace(environ=dict(environment)),
        json=json,
        Path=Path,
        NamedTuple=NamedTuple,
        quote=lambda value, safe='': value.replace(':', '%3A').replace('/', '%2F') if safe == '' else value,
        urllib=SimpleNamespace(
            request=SimpleNamespace(Request=FakeRequest, urlopen=urlopen),
            error=SimpleNamespace(URLError=OSError),
        ),
        task=lambda fn: fn,
        logged=lambda _name: lambda fn: fn,
        Context=object,
        DEPS_IMAGE_BUILD_ARGS=('INDEX_URL', 'INDEX_USERNAME', 'INDEX_PASSWORD'),
        DOCKERFILE_DEPS=Path('Dockerfile.deps'),
        INDEX_OIDC_PROVIDER=cell['git_hosting_service'],
        print=printed.append,
    )
    helpers['printed'] = printed
    helpers['requests'] = requests
    helpers['executed'] = executed
    return helpers


class Engine:
    """A context whose `run` records the engine logins the build asks for."""

    def __init__(self) -> None:
        """Start with no login recorded."""
        self.logins: list[tuple[str, dict]] = []

    def run(self, command: str, **options: object) -> None:
        """Record the command and the environment it was given."""
        env = options.get('env')
        self.logins.append((command, dict(env) if isinstance(env, dict) else {}))


BASE_IMAGE = 'ghcr.io/astral-sh/uv:0.13.7-python3.11-trixie-slim@sha256:abc'
FENCED_IMAGE = 'pkgs.example.com/docker-remote/astral-sh/uv:0.13.7@sha256:abc'
INDEX = 'https://pkgs.example.com/artifactory/api/pypi/internal/simple'
INDEX_ON_A_PORT = 'https://pkgs.example.com:8081/artifactory/api/pypi/x/simple'


@pytest.mark.parametrize(
    ('reference', 'index', 'registry'),
    [
        (BASE_IMAGE, INDEX, ''),
        (BASE_IMAGE, '', ''),
        (FENCED_IMAGE, INDEX, 'pkgs.example.com'),
        ('docker.pkgs.example.com/astral-sh/uv:0.13.7', INDEX, 'docker.pkgs.example.com'),
        ('pkgs.example.com:5001/astral-sh/uv:0.13.7', INDEX, 'pkgs.example.com:5001'),
        ('pkgs.example.com/docker/uv:1', INDEX_ON_A_PORT, 'pkgs.example.com'),
        ('notpkgs.example.com/uv:1', INDEX, ''),
        ('pkgs.example.com.evil.net/uv:1', INDEX, ''),
    ],
)
def test_the_index_identity_reaches_only_the_index_host(generated_project, reference, index, registry):
    """A base image on the index host, a subdomain or a port of it gets the index identity; any other does not."""
    project, cell = generated_project
    helpers = index_helpers(project, cell, {})
    assert helpers['fenced_registry'](reference, index) == registry


def test_the_engine_logs_in_to_a_fenced_base_image_registry_before_it_builds(generated_project):
    """`build_deps_image` logs the engine in with the index credentials, by name, only when the fence serves the image.

    In the open, and for an open base image behind a fence, no login runs at all.
    """
    project, cell = generated_project
    environment = {'UV_DEFAULT_INDEX': INDEX, 'INDEX_USERNAME': 'widget-ci', 'INDEX_PASSWORD': 'minted'}
    helpers = index_helpers(project, cell, environment)
    engine = Engine()
    helpers['build_deps_image'](engine, 'podman', FENCED_IMAGE, 'widget-deps:latest')
    assert len(engine.logins) == 1, f'the engine logged in {len(engine.logins)} times'
    login, login_env = engine.logins[0]
    assert login == 'echo "$INDEX_PASSWORD" | podman login pkgs.example.com -u "$INDEX_USERNAME" --password-stdin'
    assert login_env['INDEX_PASSWORD'] == 'minted'  # noqa: S105 — a test value
    build, build_env = helpers['executed'][0]
    assert build.startswith(f'podman build --build-arg BASE_IMAGE={FENCED_IMAGE} --build-arg INDEX_URL="$INDEX_URL"')
    assert build_env == {'INDEX_URL': INDEX, 'INDEX_USERNAME': 'widget-ci', 'INDEX_PASSWORD': 'minted'}
    assert 'minted' not in build
    assert helpers['printed'] == ['Logged in to pkgs.example.com as widget-ci.']
    engine, helpers = Engine(), index_helpers(project, cell, environment)
    helpers['build_deps_image'](engine, 'podman', BASE_IMAGE, 'widget-deps:latest')
    assert not engine.logins, 'the index credentials were sent to ghcr.io'
    assert helpers['executed'][0][1]['INDEX_PASSWORD'] == 'minted', 'the builder stage lost its credentials'  # noqa: S105
    engine, helpers = Engine(), index_helpers(project, cell, {})
    helpers['build_deps_image'](engine, 'docker', FENCED_IMAGE, 'widget-deps:latest')
    assert not engine.logins
    open_build = f'docker build --build-arg BASE_IMAGE={FENCED_IMAGE} -f Dockerfile.deps -t widget-deps:latest .'
    assert helpers['executed'] == [(open_build, {})]


def test_nothing_happens_in_the_open(generated_project, tmp_path):
    """With no fence variable set there is no login, no build argument, no request and no netrc."""
    project, cell = generated_project
    netrc = tmp_path / 'netrc'
    helpers = index_helpers(project, cell, {'NETRC': str(netrc)})
    assert helpers['index_login']() is None
    assert helpers['build_environment']() == {}
    assert helpers['build_arguments']({}) == ''
    helpers['login'](None)
    assert helpers['requests'] == []
    assert not netrc.exists(), 'a netrc was written with nothing to put in it'
    assert helpers['printed'] == ['No fenced index configured; nothing to log in to.']


def test_credentials_already_set_win_and_need_no_exchange(generated_project):
    """A developer's own token, or the kaniko job's dotenv, is used as given: no exchange is attempted."""
    project, cell = generated_project
    environment = {**FENCE, 'UV_DEFAULT_INDEX': FENCE['UV_DEFAULT_INDEX'] + ' ', 'JFROG_ID_TOKEN': 'jwt'}
    environment.update({'INDEX_USERNAME': 'jane', 'INDEX_PASSWORD': 'personal-token'})
    helpers = index_helpers(project, cell, environment)
    assert helpers['build_environment']() == {
        'INDEX_URL': FENCE['UV_DEFAULT_INDEX'],
        'INDEX_USERNAME': 'jane',
        'INDEX_PASSWORD': 'personal-token',
    }
    assert helpers['requests'] == [], 'an exchange ran although credentials were given'


def test_the_exchange_sends_what_artifactory_expects_and_prints_no_token(generated_project):
    """The job's ID token goes to Artifactory's exchange endpoint with the provider and project, over https only."""
    project, cell = generated_project
    environment = {**FENCE, 'JFROG_ID_TOKEN': 'jwt-from-gitlab'}
    # Two answers: the login below and the build environment after it each exchange once.
    answers = [{'access_token': 'minted-token', 'expires_in': 3600}] * 2
    helpers = index_helpers(project, cell, environment, answers=answers)
    login = helpers['index_login']()
    assert login == ('widget-ci', 'minted-token')
    ((request, timeout),) = helpers['requests']
    assert request.full_url == 'https://pkgs.example.com/access/api/v1/oidc/token'
    assert request.method == 'POST'
    assert request.headers == {'Content-Type': 'application/json'}
    assert timeout == helpers['TIMEOUT_SECONDS']
    assert json.loads(request.data) == {
        'grant_type': 'urn:ietf:params:oauth:grant-type:token-exchange',
        'subject_token_type': 'urn:ietf:params:oauth:token-type:id_token',
        'subject_token': 'jwt-from-gitlab',
        'provider_name': cell['git_hosting_service'],
        'project_key': 'widget',
    }
    assert helpers['build_environment']() == {
        'INDEX_URL': FENCE['UV_DEFAULT_INDEX'],
        'INDEX_USERNAME': 'widget-ci',
        'INDEX_PASSWORD': 'minted-token',
    }
    leaked = [line for line in helpers['printed'] if 'minted-token' in line or 'jwt-from-gitlab' in line]
    assert not leaked, f'a token was printed: {leaked}'


def test_on_github_the_id_token_is_minted_from_the_actions_endpoint(generated_project):
    """Without a `JFROG_ID_TOKEN` variable, a job with `id-token: write` asks Actions for one for the audience."""
    project, cell = generated_project
    environment = {
        **FENCE,
        'JFROG_AUDIENCE': 'https://pkgs.example.com',
        'JFROG_PROVIDER': 'gh-oidc',
        'ACTIONS_ID_TOKEN_REQUEST_URL': 'https://pipelines.actions.githubusercontent.com/token?api-version=2',
        'ACTIONS_ID_TOKEN_REQUEST_TOKEN': 'runner-bearer',
    }
    answers = [{'value': 'jwt-from-github'}, {'access_token': 'minted-token'}]
    helpers = index_helpers(project, cell, environment, answers=answers)
    assert helpers['index_login']() == ('widget-ci', 'minted-token')
    (mint, _), (exchange, _) = helpers['requests']
    minted_at = environment['ACTIONS_ID_TOKEN_REQUEST_URL'] + '&audience=https%3A%2F%2Fpkgs.example.com'
    assert mint.full_url == minted_at
    assert mint.headers['Authorization'] == 'Bearer runner-bearer'
    assert mint.method == 'GET'
    sent = json.loads(exchange.data)
    assert (sent['subject_token'], sent['provider_name']) == ('jwt-from-github', 'gh-oidc')
    leaked = [line for line in helpers['printed'] if 'jwt-from-github' in line or 'runner-bearer' in line]
    assert not leaked, f'a token was printed: {leaked}'
    outside = index_helpers(project, cell, {**FENCE, 'JFROG_AUDIENCE': 'https://pkgs.example.com'})
    assert outside['index_login']() is None, 'a login was attempted with no ID token from anywhere'
    assert outside['requests'] == []


def test_the_exchange_refuses_plain_http_and_an_answer_without_a_token(generated_project):
    """An ID token never travels in clear, and an empty answer is an error rather than an empty password."""
    project, cell = generated_project
    environment = {**FENCE, 'JFROG_URL': 'http://pkgs.example.com', 'JFROG_ID_TOKEN': 'jwt'}
    helpers = index_helpers(project, cell, environment)
    with pytest.raises(helpers['IndexLoginError']):
        helpers['index_login']()
    assert helpers['requests'] == []
    helpers = index_helpers(project, cell, {**FENCE, 'JFROG_ID_TOKEN': 'jwt'}, answers=[{'error': 'nope'}])
    with pytest.raises(helpers['IndexLoginError']):
        helpers['index_login']()


def test_the_login_writes_a_private_netrc_for_the_index_host(generated_project, tmp_path):
    """`index.login` adds the index host to the netrc every later fetch reads, replacing a stale entry, mode 600."""
    project, cell = generated_project
    netrc = tmp_path / 'netrc'
    netrc.write_text('machine other.example.com login a password b\nmachine pkgs.example.com login old password gone\n')
    environment = {**FENCE, 'JFROG_ID_TOKEN': 'jwt', 'NETRC': str(netrc)}
    helpers = index_helpers(project, cell, environment, answers=[{'access_token': 'minted-token'}])
    helpers['login'](None)
    assert netrc.read_text(encoding='utf-8') == (
        'machine other.example.com login a password b\nmachine pkgs.example.com login widget-ci password minted-token\n'
    )
    assert stat.S_IMODE(netrc.stat().st_mode) == 0o600
    assert helpers['printed'][-1] == f'Logged in to pkgs.example.com as widget-ci; credentials in {netrc} for this job.'
    assert not any('minted-token' in line for line in helpers['printed'])


def test_publish_takes_the_minted_login_when_only_the_url_is_set(generated_project):
    """`release.publish` fills the two `UV_PUBLISH_*` credentials from the index login, and only then (ADR-0063)."""
    project, _ = generated_project
    source = (project / '_CI' / 'tasks' / 'release.py').read_text(encoding='utf-8')
    assert 'apply_index_login()' in function_source(source, 'publishes_with_credentials')
    environ = {'UV_PUBLISH_URL': 'https://pkgs.example.com/artifactory/api/pypi/internal'}
    helpers = exec_from(
        source,
        'apply_index_login',
        os=SimpleNamespace(environ=environ),
        index_login=lambda: SimpleNamespace(username='widget-ci', password='minted-token'),  # noqa: S106 — a test value
    )
    helpers['apply_index_login']()
    assert environ['UV_PUBLISH_USERNAME'] == 'widget-ci'
    assert environ['UV_PUBLISH_PASSWORD'] == 'minted-token'  # noqa: S105 — a test value
    environ = {'UV_PUBLISH_URL': 'https://pkgs.example.com', 'UV_PUBLISH_USERNAME': 'me'}
    environ['UV_PUBLISH_PASSWORD'] = 'mine'  # noqa: S105 — a test value
    helpers['os'].environ = environ
    helpers['apply_index_login']()
    assert environ['UV_PUBLISH_PASSWORD'] == 'mine', 'a credential already set was overwritten'  # noqa: S105 — a test value
    environ = {}
    helpers['os'].environ = environ
    helpers['apply_index_login']()
    assert not environ, 'credentials were filled in with no URL to send them to'
