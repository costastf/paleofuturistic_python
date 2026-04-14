# Paleofuturistic Python

> _The Python development workflow your past self had always hoped for is finally here!_

<p align="center">
  <img src="./docs/paleofuturistic_python.png?raw=true" alt="Paleofuturistic Environment"/>
</p>

This project is meant as an enterprise-ready template for developing Python packages.
If that bar is a bit too high for you, then you can checkout [Straight to the Money 💰](https://github.com/Carlovo/straight_to_the_money).
Paleofuturistic Python is a detached fork of Straight to the Money 💰.

## Usage

Prerequisite: [uv](https://docs.astral.sh/uv/)
(Installing uv should also provide you with uvx.
Give their docs a look-over before continuing if you want to get a better understanding of what is going on under the hood in the steps below.)

### Setup

- Initialize with `uvx cruft create --checkout latest https://github.com/schubergphilis/paleofuturistic_python` and fill in your project details.
- On first run of any workflow command, the bootstrap step will prompt to install pre-commit hooks.

### Workflow

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
| `./workflow.cmd document` | Build and view documentation (mkdocs) |
| `./workflow.cmd container.build` | Build the dependency cache container image |
| `./workflow.cmd container.act` | Run the CI workflow locally using act |
| `./workflow.cmd develop.pre-commit` | Run all pre-commit hooks on the codebase |
| `./workflow.cmd bootstrap --force` | Re-run the development environment setup |

### Features

- **Portable CI tooling** — vendored [Invoke](https://www.pyinvoke.org/) framework, no global installs required
- **Cross-platform** — `workflow.cmd` launcher works on Unix/macOS (sh) and Windows (cmd.exe)
- **Security** — pip-audit vulnerability scanning, CycloneDX SBOM generation, OWASP Dependency Track upload
- **Quality** — ruff linting/formatting, pylint, ty type checking, complexipy cognitive complexity, pyscn analysis
- **Release automation** — version bump, changelog generation, PyPI publish, SBOM upload, artifact cleanup
- **Container support** — dependency cache images, local CI via act
- **Documentation** — mkdocs with API reference generation via mkdocstrings

For a more elaborate walkthrough, see the [docs](https://schubergphilis.github.io/paleofuturistic_python/walkthrough/).

### Template development

To test the template itself after making changes:

```bash
./workflow.cmd test
```

To skip known CVEs during template testing:

```bash
TEMPLATE_SECURITY_OVERRIDE="CVE-2025-71176" ./workflow.cmd test
```
