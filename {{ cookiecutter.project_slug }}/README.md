# {{ cookiecutter.project_name }}

[![Python](https://img.shields.io/badge/python-{{ cookiecutter.python_version }}-blue?logo=python&logoColor=white)](https://www.python.org)
{%- if cookiecutter.include_apache_license %}
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](https://opensource.org/licenses/Apache-2.0)
{%- endif %}
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-yellow.svg)](https://conventionalcommits.org)
[![pyscn quality](https://img.shields.io/badge/pyscn-not%20rated-lightgrey)](https://pyscn.ludo-tech.org)

{{ cookiecutter.project_description }}

## Usage

Legacy: `pip install {{ cookiecutter.project_slug }}`

Preferred: `uv add {{ cookiecutter.project_slug }}`

## Developing further

> Development flow as [Paleofuturistic Python](https://github.com/schubergphilis/paleofuturistic_python)

Prerequisite: [uv](https://docs.astral.sh/uv/)

### Setup

- Fork and clone this repository.
- Download dependencies: `uv sync --all-extras --dev`
- On first run of any workflow command, the bootstrap step will prompt to install pre-commit hooks.

### Workflow

All commands are invoked via `./workflow.cmd <namespace>.<task>`:

| Command | Description |
|---------|-------------|
| `./workflow.cmd format` | Format code and sort imports |
| `./workflow.cmd lint` | Run all linters (ruff, pylint, ty, complexipy, commitizen) |
| `./workflow.cmd test` | Run all tests (pytest) |
| `./workflow.cmd build` | Run security checks and build the package |
| `./workflow.cmd release -i <type>` | Bump version, tag, push, build, publish, and upload SBOM |
| `./workflow.cmd quality` | Run code quality analysis (pyscn) |
| `./workflow.cmd secure` | Run security audit and generate SBOM |
| `./workflow.cmd document` | Build and view documentation (mkdocs) |
| `./workflow.cmd container.build` | Build the dependency cache container image |
| `./workflow.cmd container.act` | Run the CI workflow locally using act |
| `./workflow.cmd develop.pre-commit` | Run all pre-commit hooks on the codebase |
| `./workflow.cmd bootstrap --force` | Re-run the development environment setup |

### Development cycle

- Add dependencies: `uv add some_lib_you_need`
- Develop (optional, tinker: `uvx --with-editable . ptpython`)
- Format: `./workflow.cmd format`
- Lint: `./workflow.cmd lint`
- Test: `./workflow.cmd test`
- Build: `./workflow.cmd build`
- Review docs: `./workflow.cmd document`
- Make a pull request.
