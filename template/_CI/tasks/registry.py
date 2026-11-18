"""A read-only client for the registry the deps image is pushed to: enough to fetch an image's config.

`container.audit` reads the pushed image back where no container engine exists, which is the
GitLab pipeline: its build job runs kaniko and the jobs after it run inside the image. The OCI
distribution API makes that three requests at most, the manifest, the per-platform manifest an
index points to, and the config blob, with a bearer token minted from the `WWW-Authenticate`
challenge the first 401 carries, which is how both GitLab's registry and ghcr answer. Standard
library only, so it needs nothing installed.
"""

import base64
import json
import re
import urllib.error
import urllib.request
from http import HTTPStatus
from typing import NamedTuple
from urllib.parse import urlencode

MANIFEST_TYPES = (
    'application/vnd.oci.image.manifest.v1+json, '
    'application/vnd.oci.image.index.v1+json, '
    'application/vnd.docker.distribution.manifest.v2+json, '
    'application/vnd.docker.distribution.manifest.list.v2+json'
)
INDEX_TYPES = (
    'application/vnd.oci.image.index.v1+json',
    'application/vnd.docker.distribution.manifest.list.v2+json',
)
# The platform the pipelines run on; a single-platform manifest has no choice to make.
PLATFORM = ('linux', 'amd64')
CHALLENGE_PART = re.compile(r'(\w+)="([^"]*)"')
TIMEOUT_SECONDS = 30


class RegistryError(RuntimeError):
    """The registry did not answer in a way the audit can read."""


class ImageReference(NamedTuple):
    """A pushed image, split the way the distribution API addresses it."""

    registry: str
    repository: str
    reference: str


def parse_reference(image: str) -> ImageReference:
    """Split ``host/path[:tag][@sha256:…]`` into registry, repository and tag or digest.

    A digest wins over a tag, as it does for an engine; a bare path means ``latest``.
    """
    name, _, digest = image.partition('@')
    registry, _, repository = name.partition('/')
    if digest:
        return ImageReference(registry, repository, digest)
    if ':' in repository:
        repository, _, tag = repository.rpartition(':')
        return ImageReference(registry, repository, tag)
    return ImageReference(registry, repository, 'latest')


def read(url: str, headers: dict[str, str]) -> bytes:
    """Return the body of ``url``; the caller handles the HTTP errors it can act on."""
    if not url.startswith('https://'):
        msg = f'refusing to talk to a registry over anything but https: {url}'
        raise RegistryError(msg)
    request = urllib.request.Request(url, headers=headers)  # noqa: S310 — https enforced above
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        return response.read()


class RegistryClient:
    """Fetches JSON documents of one repository, minting a bearer token on the first 401."""

    def __init__(self, image: ImageReference, credentials: tuple[str, str] | None) -> None:
        """Remember where the repository lives and what to answer a token challenge with."""
        self.image = image
        self.credentials = credentials
        self.token: str | None = None

    def get_json(self, path: str, accept: str) -> dict:
        """Return the parsed document at ``/v2/<repository>/<path>``."""
        url = f'https://{self.image.registry}/v2/{self.image.repository}/{path}'
        try:
            return json.loads(self.request(url, accept))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            msg = f'could not read {url}: {exc}'
            raise RegistryError(msg) from exc

    def request(self, url: str, accept: str) -> bytes:
        """Fetch ``url``, answering one 401 with a token minted from its challenge."""
        headers = {'Accept': accept}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        try:
            return read(url, headers)
        except urllib.error.HTTPError as exc:
            if exc.code != HTTPStatus.UNAUTHORIZED or self.token is not None:
                raise
            self.token = self.mint_token(exc.headers.get('WWW-Authenticate', ''))
        return read(url, {**headers, 'Authorization': f'Bearer {self.token}'})

    def mint_token(self, challenge: str) -> str:
        """Exchange the challenge's realm, service and scope for a bearer token.

        The credentials, when there are any, go to the realm as HTTP basic auth: a job token
        on GitLab, the workflow token on GitHub. Without them the realm answers with a token
        good for public repositories, which is what a developer's audit of a public image gets.
        """
        parts = dict(CHALLENGE_PART.findall(challenge))
        realm = parts.get('realm')
        if not realm:
            msg = f'the registry asked for authentication without saying where: {challenge!r}'
            raise RegistryError(msg)
        query = urlencode({key: parts[key] for key in ('service', 'scope') if key in parts})
        headers = {}
        if self.credentials:
            encoded = base64.b64encode(':'.join(self.credentials).encode('utf-8')).decode('ascii')
            headers['Authorization'] = f'Basic {encoded}'
        body = json.loads(read(f'{realm}?{query}', headers))
        token = body.get('token') or body.get('access_token')
        if not token:
            msg = f'{realm} returned no token'
            raise RegistryError(msg)
        return token


def platform_manifest_digest(index: dict) -> str:
    """Return the digest of the manifest in ``index`` built for the pipelines' platform."""
    for manifest in index.get('manifests', []):
        platform = manifest.get('platform', {})
        if (platform.get('os'), platform.get('architecture')) == PLATFORM:
            return manifest['digest']
    msg = f'the image index holds no {"/".join(PLATFORM)} manifest'
    raise RegistryError(msg)


def image_config(image: str, credentials: tuple[str, str] | None = None) -> dict:
    """Return the OCI config of ``image``, history and environment included.

    Raises:
        RegistryError: When the registry cannot be reached, refuses the request, or answers
            with a document the audit cannot read.

    """
    client = RegistryClient(parse_reference(image), credentials)
    manifest = client.get_json(f'manifests/{client.image.reference}', MANIFEST_TYPES)
    if manifest.get('mediaType') in INDEX_TYPES:
        manifest = client.get_json(f'manifests/{platform_manifest_digest(manifest)}', MANIFEST_TYPES)
    return client.get_json(f'blobs/{manifest["config"]["digest"]}', 'application/json')
