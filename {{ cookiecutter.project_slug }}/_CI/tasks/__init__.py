from invoke import Collection, task


@task
def format(context):
    """Check code formatting with ruff."""
    context.run("uv run ruff format --diff", echo=True)


@task
def ruff_lint(context):
    """Run ruff linter."""
    context.run("uv run ruff check", echo=True)


@task
def pylint(context):
    """Run pylint on src/."""
    context.run("uv run pylint src/", echo=True)


@task(pre=[format, ruff_lint, pylint])
def lint(context):
    """Run all linting steps: format, ruff-lint, pylint."""


@task
def test(context):
    """Run pytest."""
    context.run("uv run pytest", echo=True)


@task
def build(context):
    """Build the package."""
    context.run("uv build", echo=True)


@task
def document(context):
    """Build the documentation."""
    context.run("uv run mkdocs build", echo=True)


namespace = Collection(format, ruff_lint, pylint, lint, test, build, document)
