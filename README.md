# Paleofuturistic Python

[![Documentation: Diátaxis](https://img.shields.io/badge/docs-Di%C3%A1taxis-009485?logo=readthedocs&logoColor=white)](https://diataxis.fr/)

> _The Python development workflow your past self had always hoped for is finally here._

<p align="center">
  <img src="./docs/paleofuturistic_python.png?raw=true" alt="Paleofuturistic Environment"/>
</p>

This is a [cruft](https://cruft.github.io/cruft/) template that generates a fully-scaffolded, enterprise-ready Python package — uv-managed, ruff-formatted, pytest-tested, properdocs-documented, with vendored CI tooling, SBOM generation, and optional Dependency Track integration.

The rest of this README is split into two parts: **[Using the template](#using-the-template)** (generating a project and working in it) and **[Developing the template](#developing-the-template)** (working on this repo itself). For longer-form material, the full [documentation](docs/index.md) is organized around the [Diátaxis](https://diataxis.fr/) framework. The project's history and its lineage as a detached fork of [Straight to the Money 💰](https://github.com/Carlovo/straight_to_the_money) live in [History and lineage](docs/explanation/history-and-lineage.md).

## Using the template

Prerequisite: [uv](https://docs.astral.sh/uv/)
(Installing uv should also provide you with uvx.
Give their docs a look-over before continuing if you want to get a better understanding of what is going on under the hood in the steps below.)

### Setup

- Initialize with `uvx cruft create --checkout latest https://github.com/schubergphilis/paleofuturistic_python` and fill in your project details.
- On first run of any workflow command, the bootstrap step will prompt to install pre-commit hooks.

### Workflow (in the generated project)

All commands in generated projects are invoked via `./workflow.cmd <namespace>.<task>`:

| Command | Description |
|---------|-------------|
| `./workflow.cmd format` | Format code and sort imports (ruff) |
| `./workflow.cmd lint` | Run all linters (ruff, pylint, ty, complexipy, commitizen) |
| `./workflow.cmd test` | Run all tests (pytest) |
| `./workflow.cmd build` | Run security checks and build the package |
| `./workflow.cmd release -i <type>` | Bump version, tag, push, build, publish, upload SBOM, and clean up |
| `./workflow.cmd quality` | Run code quality analysis (pyscn) |
| `./workflow.cmd secure` | Run security audit and generate SBOM |
| `./workflow.cmd document` | Build and view documentation (properdocs) |
| `./workflow.cmd container.build` | Build the dependency cache container image |
| `./workflow.cmd develop.pre-commit` | Run all pre-commit hooks on the codebase |
| `./workflow.cmd bootstrap --force` | Re-run the development environment setup |

### Features

- **Portable CI tooling** — vendored [Invoke](https://www.pyinvoke.org/) framework, no global installs required
- **Cross-platform** — `workflow.cmd` launcher works on Unix/macOS (sh) and Windows (cmd.exe)
- **Security** — pip-audit vulnerability scanning, CycloneDX SBOM generation, OWASP Dependency Track upload
- **Quality** — ruff linting/formatting, pylint, ty type checking, complexipy cognitive complexity, pyscn analysis
- **Release automation** — version bump, changelog generation, PyPI publish, SBOM upload, artifact cleanup
- **Container support** — dependency cache images
- **Documentation** — properdocs with API reference generation via mkdocstrings

For longer-form walkthroughs, start with the tutorials in the [docs](docs/index.md) — [Generate your first project](docs/tutorials/generate-your-first-project.md) and [From zero to a published package](docs/tutorials/from-zero-to-published-package.md).

### Template knobs

The cruft questionnaire exposes these switches; defaults in **bold**.

| Knob | Choices | Effect |
|------|---------|--------|
| `git_hosting_service` | **`github`** \| `gitlab` | Selects the CI host scaffolding and the matching `_CI/tasks/<host>.py` submodule. |
| `license` | **`Apache-2.0`** \| `MIT` \| `BSD-3-Clause` \| `None` | Ships the matching `LICENSE` file (`None` ships none). |
| `integrate_dependency_track` | **`true`** \| `false` | Opts the SBOM-upload code in `_CI/tasks/secure.py` in. |
| `integrate_pages` | **`true`** \| `false` | Opts the Pages workflow and `document.deploy-github` task in (effective only when `git_hosting_service = github`). |
| `min_python_version` / `max_python_version` | dotted version | Bounds the supported Python range for the generated package metadata. |

See [Cruft questionnaire variables](docs/reference/cookiecutter-variables.md) for the full reference and [Choose a git host](docs/how-to/choose-a-git-host.md) / [Enable Dependency Track](docs/how-to/enable-dependency-track.md) / [Publish docs to GitHub Pages](docs/how-to/publish-docs-to-github-pages.md) for the per-knob how-tos.

## Developing the template

The commands below run **from this repo**, not from a generated project.

### Test entry points

The template ships four test entry points; pick the one that matches the level of confidence you need.

| Command | Scope |
|---------|-------|
| `./workflow.cmd test.invariants` | Fast pytest layer — generates each matrix cell once and asserts structural invariants (no inner toolchain). Best signal-per-second. |
| `./workflow.cmd test` | Generate the template with default context and run the full inner QA cycle (`format`, `lint`, `test.tox`, `build`, `document`). |
| `./workflow.cmd test.combo --git-hosting-service <github\|gitlab> [--no-integrate-dependency-track] [--no-integrate-pages]` | Same as `test`, but for one explicit matrix cell. Use to reproduce a single CI failure locally. |
| `./workflow.cmd test.matrix` | Run every cell of the cartesian product; per-cell logs land in `reports/matrix/`. Defaults to sequential — CI parallelizes by fanning out across runners instead. |

CI (`.github/workflows/template-matrix.yaml`) runs `test.invariants` plus a fanned-out `test.combo` per matrix cell on every push to `main` and every pull request.

To skip known CVEs during template testing:

```bash
TEMPLATE_SECURITY_OVERRIDE="CVE-2025-71176" ./workflow.cmd test
```
