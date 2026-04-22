"""Shared utilities for CI task definitions."""

import os
import platform
import shutil
import sys
from collections.abc import Callable
from functools import wraps

from invoke import Context

for _stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(_stream, 'reconfigure', None)
    if reconfigure is not None:
        reconfigure(encoding='utf-8', errors='replace')


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

    Returns 'open' on macOS/Linux and 'start' on Windows.
    """
    return 'start' if operating_system() == 'windows' else 'open'


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
    """Decorator: print ✅ on success or ❌ on SystemExit failure."""

    def decorator(fn: Callable[..., None]) -> Callable[..., None]:
        @wraps(fn)
        def wrapper(context: Context, *args: object, **kwargs: object) -> None:
            try:
                fn(context, *args, **kwargs)
                print(f'✅ {name} passed 👍')
            except SystemExit:
                print(f'❌ {name} failed 👎')
                raise

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
