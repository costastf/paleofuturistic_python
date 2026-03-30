from invoke import Collection, task


@task
def format(context):
    """Check code formatting with ruff."""
    context.run("uv run ruff format --diff src/ _CI/tasks/ tests/", echo=True)


@task
def ruff_lint(context):
    """Run ruff linter."""
    context.run("uv run ruff check src/ _CI/tasks/ tests/", echo=True)


@task
def pylint(context):
    """Run pylint on src/."""
    context.run("uv run pylint src/ _CI/tasks/ tests/", echo=True)


@task
def ty(context):
    """Run ty type checker on src/."""
    context.run("uv run ty check src/ _CI/tasks/ tests/", echo=True)


@task(pre=[format, ruff_lint, pylint, ty])
def lint(context):
    """Run all linting steps: format, ruff-lint, pylint, ty."""


@task
def secure(context):
    """Run pip-audit security scan."""
    context.run("uv run pip-audit", echo=True)


@task
def test(context):
    """Run pytest."""
    context.run("uv run pytest --strict", echo=True)


@task
def build(context):
    """Build the package."""
    context.run("uv build", echo=True)


@task
def document(context):
    """Build the documentation."""
    context.run("uv run mkdocs build", echo=True)


namespace = Collection(format, ruff_lint, pylint, ty, lint, secure, test, build, document)
