"""Shared utilities for CI task definitions."""

import json
import os
import platform
import shutil
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from functools import wraps
from typing import IO, Any, NamedTuple
from urllib.parse import urlsplit, urlunsplit

from invoke import Context


class PipelineComponent(NamedTuple):
    """A CI pipeline component (GitHub Action, container image, …) for inclusion in the SBOM."""

    name: str
    version: str
    purl: str


for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, 'reconfigure', None)
    if reconfigure is not None:
        reconfigure(encoding='utf-8', errors='replace')


INDENT = '    '
DEPTH: ContextVar[int] = ContextVar('logged_depth', default=0)

OPEN_COMMAND = {
    'linux': 'xdg-open',
    'macos': 'open',
    'windows': 'start',
    'wsl': 'wslview',  # from the wslu package; falls back to xdg-open if not installed
}


class IndentingStream:
    """Wrap a text stream to prepend a prefix at the start of every line."""

    def __init__(self, inner: IO[str], prefix: str) -> None:
        self.inner = inner
        self.prefix = prefix
        self.at_line_start = True

    def write(self, data: str) -> int:
        """Write data through, prefixing every line start with ``self.prefix``."""
        if not data:
            return 0
        chunks: list[str] = []
        for ch in data:
            if self.at_line_start and ch != '\n':
                chunks.append(self.prefix)
                self.at_line_start = False
            chunks.append(ch)
            if ch == '\n':
                self.at_line_start = True
        return self.inner.write(''.join(chunks))

    def flush(self) -> None:
        """Flush the wrapped stream."""
        self.inner.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


@contextmanager
def indented_streams(prefix: str) -> Iterator[None]:
    """Wrap sys.stdout and sys.stderr to prepend `prefix` to each new line."""
    original_out, original_err = sys.stdout, sys.stderr
    sys.stdout = IndentingStream(original_out, prefix)  # type: ignore[assignment]
    sys.stderr = IndentingStream(original_err, prefix)  # type: ignore[assignment]
    try:
        yield
    finally:
        sys.stdout, sys.stderr = original_out, original_err


def is_ci() -> bool:
    """Detect CI environment (GitHub Actions, GitLab CI, etc.)."""
    return os.environ.get('CI', '').lower() == 'true'


def strip_credentials(url: str) -> str:
    """Return ``url`` with any ``user:password@`` userinfo removed from its netloc.

    CI checkouts bake a token into the ``origin`` remote — for example
    ``https://x-access-token:<token>@github.com/owner/repo.git``. Anything that
    reads the remote back and publishes it must drop the credential first: the
    SBOM's VCS reference ships inside the wheel, so a token written there would
    become a permanent public artefact.

    Only the netloc is inspected, so an ``@`` elsewhere in the URL (a path or
    query) is left alone. URLs without userinfo are returned unchanged.
    """
    parts = urlsplit(url)
    if '@' not in parts.netloc:
        return url
    host = parts.hostname or ''
    netloc = f'{host}:{parts.port}' if parts.port else host
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def get_operating_system() -> str:
    """Return the current operating system ('windows', 'macos', 'linux', or 'wsl').

    Linux running under WSL is reported as 'wsl' (detected via /proc/version).

    Raises:
        SystemExit: If the operating system is not recognized.
    """
    system = platform.system()

    if system == 'Linux':
        with suppress(OSError), open('/proc/version', encoding='utf-8') as proc_version:
            if any(marker in proc_version.read().lower() for marker in ('microsoft', 'wsl')):
                return 'wsl'
        return 'linux'

    if system == 'Darwin':
        return 'macos'

    if system == 'Windows':
        return 'windows'

    print(f'Unsupported operating system: {system}')
    raise SystemExit(1)


def open_command() -> str:
    """Return the shell command to open a file in the default application.

    Picks 'start' on Windows, 'open' on macOS, 'wslview' on WSL when
    available (routes to the Windows default handler via interop), and
    'xdg-open' on plain Linux.
    """
    system = get_operating_system()
    if system == 'wsl' and not shutil.which('wslview'):
        print('wslview not found; install the wslu package for `open` to work. Falling back to xdg-open.')
        return OPEN_COMMAND['linux']
    return OPEN_COMMAND[system]


def container_engine() -> str:
    """Return the available container engine ('docker' or 'podman').

    Raises:
        SystemExit: If neither docker nor podman is found.
    """
    for engine in ('docker', 'podman'):
        if shutil.which(engine):
            return engine
    print('No container engine found. Install docker or podman.')
    raise SystemExit(1)


def image_digest_reference(context: Context, engine: str, image: str) -> str:
    """Return ``repository@sha256:…`` for a locally-present ``image``, else ``image`` unchanged.

    Downstream CI jobs pin the deps image by digest, so a tag repointed between the
    build job and a consumer job cannot change the container that consumer runs in.

    The image must already be local (freshly built, or pulled) for a repo digest to
    exist. The ``inspect`` JSON is parsed rather than shelling out with a Go template,
    which keeps the command free of braces needing shell quoting and avoids docker and
    podman disagreeing on which template field carries the repository digest.
    """
    repository = image.rsplit(':', 1)[0]
    result = context.run(f'{engine} image inspect {image}', hide=True, warn=True)
    if result is None or result.failed:
        print(f'Could not inspect {image} for a digest; falling back to the tag.')
        return image
    try:
        entries = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f'Could not parse {engine} inspect output for {image}; falling back to the tag.')
        return image
    for entry in entries:
        for reference in entry.get('RepoDigests') or []:
            if reference.startswith(f'{repository}@sha256:'):
                return reference
    print(f'No repo digest recorded for {image}; falling back to the tag.')
    return image


def execute(context: Context, cmd: str) -> None:
    """Execute a shell command, raising SystemExit(1) on failure.

    Honors ``INVOKE_SHELL`` to override the interpreter invoke spawns — needed
    on minimal CI images like kaniko:debug that ship busybox sh but no bash.
    """
    shell = os.environ.get('INVOKE_SHELL')
    kwargs: dict[str, object] = {'shell': shell} if shell else {}
    result = context.run(cmd, echo=True, warn=True, **kwargs)
    if result is None or result.failed:
        raise SystemExit(1)


def run(cmd: str) -> Callable[[Callable[[Context], None]], Callable[[Context], None]]:
    """Decorator: replace the function body with a shell-command invocation."""

    def decorator(fn: Callable[[Context], None]) -> Callable[[Context], None]:
        @wraps(fn)
        def wrapper(context: Context) -> None:
            execute(context, cmd)

        return wrapper

    return decorator


def logged(name: str) -> Callable[[Callable[..., None]], Callable[..., None]]:
    """Decorator: print ✅ on success or ❌ on SystemExit failure.

    The outermost ``@logged`` call wraps ``sys.stdout``/``sys.stderr`` so every
    line of body output — shell echoes, bare prints, nested subcommand banners
    — is indented by one ``INDENT``. The outermost banner itself is printed
    outside the wrap and lands flush-left, so a leaf task invoked directly
    (e.g. ``test.tox``) and a parent that orchestrates children (e.g. ``lint``)
    render the same way: indented body, flush-left final banner.
    """

    def decorator(fn: Callable[..., None]) -> Callable[..., None]:
        @wraps(fn)
        def wrapper(context: Context, *args: object, **kwargs: object) -> None:
            depth_before = DEPTH.get()
            token = DEPTH.set(depth_before + 1)
            try:
                if depth_before == 0:
                    try:
                        with indented_streams(INDENT):
                            fn(context, *args, **kwargs)
                        print(f'✅ {name} passed 👍')
                    except SystemExit:
                        print(f'❌ {name} failed 👎')
                        raise
                else:
                    try:
                        fn(context, *args, **kwargs)
                        print(f'✅ {name} passed 👍')
                    except SystemExit:
                        print(f'❌ {name} failed 👎')
                        raise
            finally:
                DEPTH.reset(token)

        return wrapper

    return decorator


def run_steps(*steps: Callable[[Context], None]) -> Callable[[Context], None]:
    """Run all steps, accumulating failures."""

    def runner(context: Context) -> None:
        failed = False
        for step in steps:
            try:
                step(context)
            except SystemExit:
                failed = True
        if failed:
            raise SystemExit(1)

    return runner
