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
    'build_environment',
    'build_arguments',
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
    helpers = exec_from(
        source,
        *INDEX_NAMES,
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
    return helpers


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
