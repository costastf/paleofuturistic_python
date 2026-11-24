"""Invariants over the fenced-index credentials: where they come from, what they never do (ADR-0063)."""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple, Self

import pytest

from .support import exec_from, function_source

INDEX_NAMES = (
    'setting',
    'index_url',
    'exchange_id_token',
    'index_login',
    'build_environment',
    'build_arguments',
    'IndexLogin',
    'IndexLoginError',
    'JFROG_TOKEN_PATH',
    'GRANT_TYPE',
    'SUBJECT_TOKEN_TYPE',
    'DEFAULT_PROVIDER',
    'TIMEOUT_SECONDS',
)


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


def index_helpers(project, environment, *, answer=None, requests=None):
    """Exec the index module's functions against a fake environment and a fake exchange endpoint."""
    source = (project / '_CI' / 'tasks' / 'index.py').read_text(encoding='utf-8')
    requests = [] if requests is None else requests

    def urlopen(request, timeout):
        requests.append((request, timeout))
        return Response(json.dumps(answer or {}).encode('utf-8'))

    printed = []
    helpers = exec_from(
        source,
        *INDEX_NAMES,
        os=SimpleNamespace(environ=dict(environment)),
        json=json,
        NamedTuple=NamedTuple,
        urllib=SimpleNamespace(
            request=SimpleNamespace(Request=FakeRequest, urlopen=urlopen),
            error=SimpleNamespace(URLError=OSError),
        ),
        DEPS_IMAGE_BUILD_ARGS=('INDEX_URL', 'INDEX_USERNAME', 'INDEX_PASSWORD'),
        DOCKERFILE_DEPS=Path('Dockerfile.deps'),
        print=printed.append,
    )
    helpers['printed'] = printed
    helpers['requests'] = requests
    return helpers


class FakeRequest:
    """The slice of `urllib.request.Request` the exchange builds."""

    def __init__(self, url: str, data: bytes | None = None, headers: dict | None = None, method: str = 'GET') -> None:
        """Record what the exchange sends."""
        self.url, self.data, self.headers, self.method = url, data, headers or {}, method


def test_nothing_happens_in_the_open(generated_project):
    """With no fence variable set there is no login, no build argument and no request."""
    project, _ = generated_project
    helpers = index_helpers(project, {})
    assert helpers['index_login']() is None
    assert helpers['build_environment']() == {}
    assert helpers['build_arguments']({}) == ''
    assert helpers['requests'] == []


def test_credentials_already_set_win_and_need_no_exchange(generated_project):
    """A developer's own token, or the kaniko job's dotenv, is used as given: no exchange is attempted."""
    project, _ = generated_project
    environment = {
        'UV_DEFAULT_INDEX': 'https://pkgs.example.com/artifactory/api/pypi/internal/simple ',
        'INDEX_USERNAME': 'jane',
        'INDEX_PASSWORD': 'personal-token',
        'JFROG_URL': 'https://pkgs.example.com',
        'JFROG_PROJECT': 'widget',
        'JFROG_ID_TOKEN': 'jwt',
    }
    helpers = index_helpers(project, environment)
    assert helpers['build_environment']() == {
        'INDEX_URL': 'https://pkgs.example.com/artifactory/api/pypi/internal/simple',
        'INDEX_USERNAME': 'jane',
        'INDEX_PASSWORD': 'personal-token',
    }
    assert helpers['requests'] == [], 'an exchange ran although credentials were given'


def test_the_exchange_sends_what_artifactory_expects_and_prints_no_token(generated_project):
    """The job's ID token goes to Artifactory's exchange endpoint with the provider and project, over https only."""
    project, _ = generated_project
    environment = {
        'UV_DEFAULT_INDEX': 'https://pkgs.example.com/artifactory/api/pypi/internal/simple',
        'JFROG_URL': 'https://pkgs.example.com/',
        'JFROG_PROJECT': 'widget',
        'JFROG_ID_TOKEN': 'jwt-from-gitlab',
    }
    helpers = index_helpers(project, environment, answer={'access_token': 'minted-token', 'expires_in': 3600})
    login = helpers['index_login']()
    assert login == ('widget-ci', 'minted-token')
    ((request, timeout),) = helpers['requests']
    assert request.url == 'https://pkgs.example.com/access/api/v1/oidc/token'
    assert request.method == 'POST'
    assert request.headers == {'Content-Type': 'application/json'}
    assert timeout == helpers['TIMEOUT_SECONDS']
    assert json.loads(request.data) == {
        'grant_type': 'urn:ietf:params:oauth:grant-type:token-exchange',
        'subject_token_type': 'urn:ietf:params:oauth:token-type:id_token',
        'subject_token': 'jwt-from-gitlab',
        'provider_name': 'gitlab',
        'project_key': 'widget',
    }
    assert helpers['build_environment']() == {
        'INDEX_URL': environment['UV_DEFAULT_INDEX'],
        'INDEX_USERNAME': 'widget-ci',
        'INDEX_PASSWORD': 'minted-token',
    }
    leaked = [line for line in helpers['printed'] if 'minted-token' in line or 'jwt-from-gitlab' in line]
    assert not leaked, f'a token was printed: {leaked}'


def test_the_exchange_refuses_plain_http_and_an_answer_without_a_token(generated_project):
    """An ID token never travels in clear, and an empty answer is an error rather than an empty password."""
    project, _ = generated_project
    environment = {'JFROG_URL': 'http://pkgs.example.com', 'JFROG_PROJECT': 'widget', 'JFROG_ID_TOKEN': 'jwt'}
    helpers = index_helpers(project, environment)
    with pytest.raises(helpers['IndexLoginError']):
        helpers['index_login']()
    assert helpers['requests'] == []
    helpers = index_helpers(project, {**environment, 'JFROG_URL': 'https://pkgs.example.com'}, answer={'error': 'nope'})
    with pytest.raises(helpers['IndexLoginError']):
        helpers['index_login']()


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
