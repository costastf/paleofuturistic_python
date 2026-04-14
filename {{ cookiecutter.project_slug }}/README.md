# {{ cookiecutter.project_name }}

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
