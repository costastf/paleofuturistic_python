# Paleofuturistic Python

[![Documentation: Diátaxis](https://img.shields.io/badge/docs-Di%C3%A1taxis-009485?logo=readthedocs&logoColor=white)](https://diataxis.fr/)

> _The Python development workflow your past self had always hoped for is finally here._

<p align="center">
  <img src="./docs/paleofuturistic_python.png?raw=true" alt="Paleofuturistic Environment"/>
</p>

This is a [copier](https://copier.readthedocs.io/) template that generates a fully-scaffolded, enterprise-ready Python package.
It ships many best practices — uv-managed, ruff-formatted, pytest-tested, SBOM generation etc. — as boring defaults.
There is no need to be daunted by the list of tools and best practices even for newcomers to Python.
This project encapsulates all necessary tool calls in a set of simple commands to enhance your development cycle.

## Quickstart

Prerequisite: [uv](https://docs.astral.sh/uv/).

```bash
uvx copier copy --vcs-ref latest --trust https://github.com/schubergphilis/paleofuturistic_python <destination-dir>
```

Answer the questions, then run `./workflow.cmd document` inside the new project.
This will build and present the documentation primer for your project.
Each generated project ships with a manual on how to use the development scaffold.
Look for the _Developer_ section in the documentation.

## Documentation

Everything else lives in the [documentation](https://schubergphilis.github.io/paleofuturistic_python/), split by persona:

- For _users_ of this template, see: **Using the template** — start with [Generate your first project](docs/using/tutorials/generate-your-first-project.md); every knob is covered in [Copier questions](docs/using/reference/copier-questions.md).
- For _maintainers_ of this template, see: **Maintaining the template** — start with [Make your first template change](docs/maintaining/tutorials/make-your-first-template-change.md) and [Design principles](docs/maintaining/explanation/design-principles.md).

## Contributing

Run `./workflow.cmd test.invariants` for the fast check; the full test pyramid is described in [Test the template](docs/maintaining/how-to/test-the-template.md).
