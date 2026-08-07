"""Shared utilities for CI task definitions."""

import json
import os
import platform
import re
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


class RemoteRef(NamedTuple):
    """The host and project path parsed out of a git remote, with credentials removed."""

    host: str
    path: str


for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, 'reconfigure', None)
    if reconfigure is not None:
        reconfigure(encoding='utf-8', errors='replace')


INDENT = '    '
DEPTH: ContextVar[int] = ContextVar('logged_depth', default=0)

# The two shapes git writes into `origin`. Tried in order; the scp form has no scheme, so it
# must be matched before the URL form or `git@host:group/proj` reads as scheme-less nonsense.
REMOTE_PATTERNS = (
    re.compile(r'^[^@/]+@(?P<host>[^:/]+):(?P<path>.+?)(?:\.git)?/?$'),
    re.compile(
        r'^(?P<scheme>https?|ssh|git)://(?:[^@/]+@)?(?P<host>[^/:]+)(?::(?P<port>\d+))?/(?P<path>.+?)(?:\.git)?/?$'
    ),
)

OPEN_COMMAND = {
    'linux': 'xdg-open',
    'macos': 'open',
    'windows': 'start',
}

# git's own summary line when it cannot create the commit object, which is how a signing
# failure surfaces whatever `gpg.format` is set to. The cause line above it is format-specific
# — openpgp prints "gpg: signing failed: No secret key", ssh prints "error: Couldn't load
# public key" — so neither is safe to match on. Verified against both formats on git 2.x.
# A failing pre-commit hook does not print this, which is what stops the unsigned retry below
# from turning an ordinary hook failure into a bogus report about signing.
SIGNING_FAILURE_MARKER = 'failed to write commit object'

# WSL registers a binfmt handler to run Windows executables. Distros with interop
# disabled have neither name, and there is then no way to reach a Windows browser.
WSL_INTEROP_MARKERS = (
    '/proc/sys/fs/binfmt_misc/WSLInterop',
    '/proc/sys/fs/binfmt_misc/WSLInterop-late',
)


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


def parse_remote_url(url: str) -> RemoteRef:
    """Split a git remote into its host and project path, credentials removed.

    Handles the two forms git writes: the scp-style ``git@host:group/project.git`` and the
    URL style ``https://host[:port]/group/project.git`` (also ``ssh://`` and ``git://``). The
    trailing ``.git`` and any trailing slash are dropped, and the path keeps every segment, so
    a nested GitLab group survives intact.

    Returns empty strings when the remote cannot be parsed, which callers treat as "no host
    known" rather than falling back to a guess.
    """
    text = strip_credentials(url.strip())
    for pattern in REMOTE_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        groups = match.groupdict()
        host = groups['host']
        # An explicit port is kept only for http(s). An ssh port (``ssh://host:2222/…``) means
        # nothing to a browser, and carrying it into a web URL would produce a dead link.
        if groups.get('scheme') in {'http', 'https'} and groups.get('port'):
            host = f'{host}:{groups["port"]}'
        return RemoteRef(host=host, path=groups['path'])
    return RemoteRef(host='', path='')


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


def wsl_interop_available() -> bool:
    """Return True when WSL can execute Windows binaries."""
    return any(os.path.exists(marker) for marker in WSL_INTEROP_MARKERS)


def open_on_wsl(context: Context, target: str) -> None:
    """Open `target` with the Windows default application, best-effort.

    There is no Linux browser to hand under WSL, so the file has to be handed to
    Windows. Three details make this awkward:

    * ``wslview`` (from ``wslu``) used to be the way to do this, but the package is
      deprecated and often simply absent. It is still preferred when installed, since
      an existing setup should keep working, and `cmd.exe` is used otherwise.
    * Windows cannot resolve a Linux path, so ``wslpath -w`` translates it first.
      Relative paths resolve against the current directory, which is what callers pass.
    * ``cmd.exe`` and ``explorer.exe`` both exit non-zero even when they succeed, so the
      exit status is deliberately not checked — failing on it would turn a working
      ``./workflow.cmd document`` into a red task.
    """
    if shutil.which('wslview'):
        context.run(f'wslview "{target}"', echo=True, warn=True)
        return
    if not wsl_interop_available():
        print(f'WSL interop is disabled, so {target} cannot be handed to Windows. Open it manually.')
        return
    result = context.run(f'wslpath -w "{target}"', hide=True, warn=True)
    windows_path = result.stdout.strip() if result is not None and not result.failed else ''
    if not windows_path:
        print(f'Could not translate {target} to a Windows path. Open it manually.')
        return
    # The empty "" is `start`'s window-title argument. Without it cmd.exe reads the
    # quoted path as the title and opens nothing at all.
    context.run(f'cmd.exe /c start "" "{windows_path}"', echo=True, warn=True)


def open_target(context: Context, target: str) -> None:
    """Open a file or URL in the host's default application.

    A failure to open is fatal on Windows, macOS and Linux, as it was before. WSL is the
    exception: the Windows helpers it has to delegate to report failure on success, so
    there is no exit status worth trusting and problems are reported as messages instead.
    """
    system = get_operating_system()
    if system == 'wsl':
        open_on_wsl(context, target)
        return
    execute(context, f'{OPEN_COMMAND[system]} {target}')


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


def signing_requested(context: Context) -> bool:
    """Return whether git is configured to sign commits in this repository.

    ``--type=bool`` normalizes every spelling git accepts (``1``, ``yes``, ``on``) to
    ``true``, so this does not have to guess at the value.
    """
    result = context.run('git config --type=bool --get commit.gpgsign', hide=True, warn=True)
    return result is not None and result.ok and result.stdout.strip() == 'true'


def commit(context: Context, message: str) -> None:
    """Commit the staged changes, letting git decide whether to sign.

    Signing is deliberately not forced in either direction. ``commit.gpgsign`` is what the
    developer or the repository has asked for, and a branch protected by a required-signatures
    rule rejects an unsigned commit at push time — so hardcoding ``--no-gpg-sign`` would break
    exactly the repositories that care most about provenance. CI, on the other hand, usually
    has no signing key at all, and a release must not stop on a documentation commit.

    So a signed commit is attempted first, and retried unsigned only when both guards hold:
    signing is what git was asked to do, and signing is what failed. Without the second guard
    a pre-commit hook failure would be retried too, reporting a signing problem that does not
    exist. The retry says plainly that the commit is unsigned and what that costs.

    Raises:
        SystemExit: with exit code 1 if the commit fails for any reason other than an
            unavailable signing key, or if the unsigned retry also fails.
    """
    result = context.run(f'git commit -m "{message}"', echo=True, warn=True)
    if result is not None and result.ok:
        return
    stderr = (result.stderr if result is not None else '') or ''
    if SIGNING_FAILURE_MARKER not in stderr or not signing_requested(context):
        raise SystemExit(1)
    print(
        'Signing failed and no usable signing key was found, so the commit was made unsigned. '
        'A branch that requires signed commits will reject it on push.'
    )
    execute(context, f'git commit --no-gpg-sign -m "{message}"')


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
