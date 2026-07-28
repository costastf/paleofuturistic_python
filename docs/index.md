# Paleofuturistic Python

[![Documentation: Diátaxis](https://img.shields.io/badge/docs-Di%C3%A1taxis-009485?logo=readthedocs&logoColor=white)](https://diataxis.fr/)

> _The Python development workflow your past self had always hoped for is finally here._

<p align="center">
  <img src="./paleofuturistic_python.png?raw=true" alt="Paleofuturistic Environment"/>
</p>

This is a [copier](https://copier.readthedocs.io/) template that generates a fully scaffolded, enterprise-ready Python package — uv-managed, ruff-formatted, pytest-tested, properdocs-documented, with vendored CI tooling, SBOM generation, and optional Dependency Track integration.

The documentation is split by what you're here to do; each area is organized around the [Diátaxis](https://diataxis.fr/) framework. The **navigation bar at the top** is the full map — open an area's dropdown and click a quadrant to unfold its pages. (The panel on the left is just the current page's table of contents.)

## Using the template

You want to generate a Python project and pick the right knobs while doing so.

Start with [Generate your first project](using/tutorials/generate-your-first-project.md), then [From zero to a published package](using/tutorials/from-zero-to-published-package.md). The [Copier questions](using/reference/copier-questions.md) reference covers every knob.

Once your project exists, its **own docs ship with it**: the scaffold manual (daily workflow, extending tasks, design rationale) lives in the generated docs' *Developer* section — run `./workflow.cmd document` inside your project.

## Maintaining the template

You want to change what this template generates.

Start with [Make your first template change](maintaining/tutorials/make-your-first-template-change.md) for the edit-test loop, [Test the template](maintaining/how-to/test-the-template.md) for the four test entry points, and [Design principles](maintaining/explanation/design-principles.md) for the constraints every change should respect.
