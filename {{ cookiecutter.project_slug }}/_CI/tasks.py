from invoke import Collection, task


@task
def lint(context):
    """Run ruff format check, ruff check and pylint."""
    context.run('uv run ruff format --diff', echo=True)
    context.run('uv run ruff check', echo=True)
    context.run('uv run pylint src/', echo=True)


@task
def test(context):
    """Run pytest."""
    context.run('uv run pytest', echo=True)


@task
def build(context):
    """Build the package."""
    context.run('uv build', echo=True)


@task
def document(context):
    """Build the documentation."""
    context.run('uv run mkdocs build', echo=True)


namespace = Collection(lint, test, build, document)
