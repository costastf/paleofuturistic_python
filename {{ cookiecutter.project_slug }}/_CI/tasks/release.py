"""Release task definitions."""

import os
import shutil
from pathlib import Path
from typing import cast

from invoke import Collection, Context, Task, task

from .build import build
from .configuration import OWASP_DTRACK_SETTINGS, UV_PUBLISH_SETTINGS
from .secure import sbom_upload
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
    """Bump the version and create a git tag.

    Args:
        context: Invoke context.
        increment: Version increment type — major, minor, patch, alpha, beta, or rc.
    """
    prerelease_types = ('alpha', 'beta', 'rc')
    semver_types = ('major', 'minor', 'patch')
    valid = semver_types + prerelease_types
    if increment not in valid:
        print('Usage: ./workflow.cmd release -i <increment>')
        print(f'  increment: {", ".join(valid)}')
        raise SystemExit(1)
    if increment in prerelease_types:
        execute(context, f'uv run cz bump --prerelease {increment} --allow-no-commit --yes')
    else:
        execute(context, f'uv run cz bump --increment {increment} --allow-no-commit --yes')


@task
@logged('release.changelog')
def changelog(context: Context, write: bool = False) -> None:
    """Generate the changelog from all tags.

    By default prints the changelog to stdout. With --write, writes to
    docs/changelog.md and commits the result.

    Args:
        context: Invoke context.
        write: Write changelog to file and commit instead of printing to stdout.
    """
    if write:
        execute(context, 'uv run cz changelog')
        execute(context, 'git add docs/changelog.md')
        execute(context, 'git commit --no-gpg-sign -m "docs: update changelog"')
    else:
        execute(context, 'uv run cz changelog --dry-run')


@task
@logged('release.push')
def push(context: Context) -> None:
    """Push the bump commit and tag to the remote."""
    execute(context, 'git push')
    execute(context, 'git push --tags')


@task
@logged('release.publish')
def publish(context: Context) -> None:
    """Build, publish, and upload SBOM — the full post-release publishing pipeline."""
    missing = [v for v in UV_PUBLISH_SETTINGS + OWASP_DTRACK_SETTINGS if not os.environ.get(v)]
    if missing:
        print(f'Missing required environment variables: {", ".join(missing)}')
        raise SystemExit(1)
    clean(context)
    build(context)
    execute(context, 'uv publish')
    sbom_upload(context)
    clean(context)


@task
@logged('release')
def release(context: Context, increment: str = '', no_push: bool = False) -> None:
    """Run the release flow: validate, bump version, update changelog, and push.

    Steps execute sequentially — any failure stops the chain.
    Use ``release.publish`` separately to build, publish, and upload the SBOM.

    Args:
        context: Invoke context.
        increment: Version increment type — major, minor, patch, alpha, beta, or rc.
        no_push: Skip push step (useful during development).
    """
    validate(context)
    bump(context, increment=increment)
    changelog(context, write=True)
    if no_push:
        print('Skipping push.')
    else:
        push(context)


@task
@logged('release.clean')
def clean(context: Context) -> None:
    """Remove build artifacts (dist/ and sbom.json)."""
    if Path('dist').exists():
        shutil.rmtree('dist')
        print('Removed dist/')
    sbom = Path('sbom.json')
    if sbom.exists():
        sbom.unlink()
        print('Removed sbom.json')


namespace = Collection('release')
namespace.add_task(cast(Task, release), default=True, name='all')
namespace.add_task(cast(Task, validate))
namespace.add_task(cast(Task, bump))
namespace.add_task(cast(Task, changelog))
namespace.add_task(cast(Task, push))
namespace.add_task(cast(Task, publish))
namespace.add_task(cast(Task, clean))
