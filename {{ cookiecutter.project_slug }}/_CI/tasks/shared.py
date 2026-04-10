"""Shared utilities for CI task definitions."""

from collections.abc import Callable
from functools import wraps

from invoke import Context

PATHS = 'src/ _CI/tasks/ tests/'
SECURITY_OVERRIDE_ENV = '{{ cookiecutter.project_slug | upper }}_SECURITY_OVERRIDE'


def execute(context: Context, cmd: str) -> None:
    """Execute a shell command, raising SystemExit(1) on failure."""
    result = context.run(cmd, echo=True, warn=True)
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
