"""Shared utilities for CI task definitions."""

import os
import platform
import shutil
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from functools import wraps
from typing import IO, Any

from invoke import Context

for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, 'reconfigure', None)
    if reconfigure is not None:
        reconfigure(encoding='utf-8', errors='replace')


INDENT = '    '
DEPTH: ContextVar[int] = ContextVar('logged_depth', default=0)


class IndentingStream:
    """Wrap a text stream to prepend a prefix at the start of every line."""

    def __init__(self, inner: IO[str], prefix: str) -> None:
        self.inner = inner
        self.prefix = prefix
        self.at_line_start = True

    def write(self, data: str) -> int:
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


def operating_system() -> str:
    """Return the current operating system ('windows', 'macos', or 'linux').

    Raises:
        SystemExit: If the operating system is not recognized.
    """
    systems = {'windows': 'windows', 'darwin': 'macos', 'linux': 'linux'}
    system = platform.system().lower()
    if system in systems:
        return systems[system]
    print(f'Unsupported operating system: {system}')
    raise SystemExit(1)


def open_command() -> str:
    """Return the shell command to open a file in the default application.

    Picks 'start' on Windows, 'open' on macOS, 'wslview' on WSL when
    available (routes to the Windows default handler via interop), and
    'xdg-open' on plain Linux.
    """
    system = operating_system()
    if system == 'windows':
        return 'start'
    if system == 'macos':
        return 'open'
    if 'microsoft' in platform.release().lower() and shutil.which('wslview'):
        return 'wslview'
    return 'xdg-open'


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

    Nested calls are indented by one ``INDENT`` so a parent workflow command's
    subcommand output and per-step banners sit under the parent, and only the
    outermost banner lands flush-left at the end of the run.
    """

    def decorator(fn: Callable[..., None]) -> Callable[..., None]:
        @wraps(fn)
        def wrapper(context: Context, *args: object, **kwargs: object) -> None:
            depth_before = DEPTH.get()
            token = DEPTH.set(depth_before + 1)
            ctx = indented_streams(INDENT) if depth_before == 1 else nullcontext()
            try:
                with ctx:
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
