# {{ cookiecutter.project_name }}

{{ cookiecutter.project_description }}

## Installation

```bash
uv add {{ cookiecutter.project_slug }}
```

## Development Setup

Clone the repository and sync dependencies:

```bash
git clone <repository-url>
cd {{ cookiecutter.project_slug }}
uv sync --all-extras --dev
```

On first run of any workflow command, the bootstrap step will prompt to install pre-commit hooks.

## Workflow Commands

All commands are invoked via `./workflow.cmd <namespace>.<task>`:

| Command | Description |
|---------|-------------|
| `./workflow.cmd lint` | Run all linters (ruff, pylint, ty, complexipy, commitizen) |
| `./workflow.cmd test` | Run all tests (pytest) |
| `./workflow.cmd build` | Run security checks and build the package |
| `./workflow.cmd release --increment <type>` | Bump version, tag, push, build, and publish to PyPI |
| `./workflow.cmd format` | Check code formatting (ruff) |
| `./workflow.cmd quality` | Run code quality analysis (pyscn) |
| `./workflow.cmd secure` | Run security audit and generate SBOM |
| `./workflow.cmd document` | Build and view documentation (mkdocs) |
| `./workflow.cmd container.build` | Build the dependency cache container image |
| `./workflow.cmd container.act` | Run the CI workflow locally using act |
| `./workflow.cmd develop.pre-commit` | Run all pre-commit hooks on the codebase |
| `./workflow.cmd bootstrap --force` | Re-run the development environment setup |
