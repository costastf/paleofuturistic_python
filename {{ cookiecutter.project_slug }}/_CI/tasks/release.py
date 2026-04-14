"""Release task definitions."""

from typing import cast

from invoke import Collection, Context, Task, task

from .build import build
from .shared import execute, logged


@task
@logged('release.validate')
def validate(context: Context) -> None:
    """Ensure the working tree is clean before releasing."""
    result = context.run('git status --porcelain', hide=True, warn=True)
    if result is None or result.failed:
        print('Could not determine git status.')
        raise SystemExit(1)
    if result.stdout.strip():
        print('Working tree is dirty. Commit or stash your changes before releasing.')
        print(result.stdout)
        raise SystemExit(1)


@task
@logged('release.bump')
def bump(context: Context, increment: str = '') -> None:
    """Bump the version, update the changelog, and create a git tag.

    Args:
        context: Invoke context.
        increment: Version increment type — major, minor, patch, alpha, beta, or rc.
    """
    prerelease_types = ('alpha', 'beta', 'rc')
    semver_types = ('major', 'minor', 'patch')
    valid = semver_types + prerelease_types
    if increment not in valid:
        print('Usage: ./workflow.cmd release <increment>')
        print(f'  increment: {", ".join(valid)}')
        raise SystemExit(1)
    if increment in prerelease_types:
        execute(context, f'uv run cz bump --prerelease {increment} --yes')
    else:
        execute(context, f'uv run cz bump --increment {increment} --yes')


@task
@logged('release.push')
def push(context: Context) -> None:
    """Push the bump commit and tag to the remote."""
    execute(context, 'git push')
    execute(context, 'git push --tags')


@task
@logged('release.publish')
def publish(context: Context) -> None:
    """Publish the package to PyPI."""
    execute(context, 'uv publish')


@task
@logged('release')
def release(context: Context, increment: str = '') -> None:
    """Run the full release flow: validate, bump, push, build, and publish.

    Steps execute sequentially — any failure stops the chain.

    Args:
        context: Invoke context.
        increment: Version increment type — major, minor, patch, alpha, beta, or rc.
    """
    validate(context)
    bump(context, increment=increment)
    push(context)
    build(context)
    publish(context)


namespace = Collection('release')
namespace.add_task(cast(Task, release), default=True, name='all')
namespace.add_task(cast(Task, validate))
namespace.add_task(cast(Task, bump))
namespace.add_task(cast(Task, push))
namespace.add_task(cast(Task, publish))


# Register each increment type as a named task so that
# `./workflow.cmd release minor` works alongside `./workflow.cmd release -i minor`.
def _make_increment_task(increment_type: str) -> Task:
    @task
    def _task(context: Context) -> None:
        release(context, increment=increment_type)

    _task.__doc__ = f'Release with {increment_type} version increment.'
    return cast(Task, _task)


for _increment in ('major', 'minor', 'patch', 'alpha', 'beta', 'rc'):
    namespace.add_task(_make_increment_task(_increment), name=_increment)
