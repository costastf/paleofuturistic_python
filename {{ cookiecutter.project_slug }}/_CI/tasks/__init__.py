"""CI task definitions for the project workflow."""

from collections.abc import Callable
from functools import wraps
from invoke import Collection, Context, task

_PATHS = 'src/ _CI/tasks/ tests/'
_SECURITY_OVERRIDE_ENV = '{{ cookiecutter.project_slug | upper }}_SECURITY_OVERRIDE'


def _exec(context: Context, cmd: str) -> None:
    """Execute a shell command, raising SystemExit(1) on failure."""
    result = context.run(cmd, echo=True, warn=True)
    if result is None or result.failed:
        raise SystemExit(1)


def _run(cmd: str) -> Callable[[Callable[[Context], None]], Callable[[Context], None]]:
    """Decorator: replace the function body with a shell-command invocation."""

    def decorator(fn: Callable[[Context], None]) -> Callable[[Context], None]:
        @wraps(fn)
        def wrapper(context: Context) -> None:
            _exec(context, cmd)

        return wrapper

    return decorator


def _logged(name: str) -> Callable[[Callable[..., None]], Callable[..., None]]:
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


def _run_steps(*steps: Callable[[Context], None]) -> Callable[[Context], None]:
    """Run all steps, accumulating failures (same pattern as lint)."""

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


from . import build as _build  # noqa: E402
from . import format_ as _format  # noqa: E402
from . import lint as _lint  # noqa: E402
from . import secure as _secure  # noqa: E402


@task
@_logged('test')
@_run('uv run pytest --strict')
def test(context: Context) -> None:
    """Run pytest."""


@task
@_logged('document')
@_run('uv run mkdocs build')
def document(context: Context) -> None:
    """Build the documentation."""


namespace = Collection(test, document)
namespace.add_collection(_format.namespace)
namespace.add_collection(_lint.namespace)
namespace.add_collection(_secure.namespace)
namespace.add_collection(_build.namespace)
