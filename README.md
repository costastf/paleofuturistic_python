# Paleofuturistic Python

[![Documentation: Diátaxis](https://img.shields.io/badge/docs-Di%C3%A1taxis-009485?logo=readthedocs&logoColor=white)](https://diataxis.fr/)

> _The Python development workflow your past self had always hoped for is finally here._

<p align="center">
  <img src="./docs/paleofuturistic_python.png?raw=true" alt="Paleofuturistic Environment"/>
</p>

This is a [copier](https://copier.readthedocs.io/) template that generates a fully-scaffolded, enterprise-ready Python package — uv-managed, ruff-formatted, pytest-tested, properdocs-documented, with vendored CI tooling, SBOM generation, and optional Dependency Track integration.

## Quickstart

Prerequisite: [uv](https://docs.astral.sh/uv/).

```bash
uvx copier copy --trust https://github.com/schubergphilis/paleofuturistic_python <destination-dir>
```

Answer the questions, then run `./workflow.cmd document` inside the new project — its docs ship with it, including the full scaffold manual under the *Developer* section.

## Documentation

Everything else lives in the [documentation](https://schubergphilis.github.io/paleofuturistic_python/), split by persona:

- **Using the template** — start with [Generate your first project](docs/using/tutorials/generate-your-first-project.md); every knob is covered in [Copier questions](docs/using/reference/copier-questions.md).
- **Maintaining the template** — start with [Make your first template change](docs/maintaining/tutorials/make-your-first-template-change.md) and [Design principles](docs/maintaining/explanation/design-principles.md).

## Contributing

Run `./workflow.cmd test.invariants` for the fast check; the full test pyramid is described in [Test the template](docs/maintaining/how-to/test-the-template.md).
