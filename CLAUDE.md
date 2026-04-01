# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repo Is

A [cookiecutter](https://cookiecutter.readthedocs.io/) / [cruft](https://cruft.github.io/cruft/) template for enterprise-ready Python packages. The `{{ cookiecutter.project_slug }}/` directory is the template tree — files there contain Jinja2 template syntax and are **not** directly executable Python.

## Template Variables (cookiecutter.json)

| Variable | Default |
|---|---|
| `project_name` | `Paleofuturistic Python Project` |
| `project_slug` | derived from `project_name` (lowercase, underscored) |
| `project_description` | `Development flow as Paleofuturistic Python` |
| `full_name` | `Paleofuturistic Python` |
| `email` | `me@here.now` |
| `python_version` | `3.12` |
| `include_apache_license` | `true` |

## Commands (run inside a generated project)

All commands use `uv`. Prerequisites: [uv](https://docs.astral.sh/uv/) installed.

```bash
uv sync --all-extras --dev       # Install all dependencies after first init
uv run ruff format               # Format code
uv run ruff format --diff        # Check formatting without applying
uv run ruff check                # Lint
uv run ruff check --fix          # Lint + auto-fix
uv run mypy                      # Type check (checks src/ only)
uv run python -m unittest        # Run all tests
uv build                         # Build distribution artifacts
uv run mkdocs build              # Build documentation
uv run mkdocs serve              # Preview docs at http://127.0.0.1:8000/
uvx --with-editable . ptpython   # Interactive REPL with project context
```

The QA pipeline runs these in order: format → lint → type check → test → build → docs build.

## Generated Project Architecture

A generated project has this structure:
- `src/<slug>/` — package source; public API exported via `__all__` in `__init__.py`
- `tests/` — unittest-based tests
- `pyproject.toml` — single config file for dependencies, ruff, mypy, and build
- `.github/workflows/quality-assurance.yaml` — runs full QA on every PR and push to main
- `.github/workflows/release.yaml` — Release Please creates versioned PRs; on merge, publishes to PyPI and GitHub Pages

## Release Flow

Releases are automated via [Release Please](https://github.com/googleapis/release-please-action). Commits must follow [Conventional Commits](https://www.conventionalcommits.org/). When merging PRs into main, squash merge using the PR title as the commit message.

## Key Design Decisions

- **`uv_build` backend** has an upper-bound pin in `pyproject.toml` (`<0.10.0`) — intentional; update it when upgrading uv past a minor version boundary.
- **`click<=8.2.1`** is pinned as a transient dep workaround for a known mkdocs issue ([mkdocs#4032](https://github.com/mkdocs/mkdocs/issues/4032)).
- **Ruff lint + format** are configured to not conflict with each other; the activated rule sets include isort (`I`) beyond ruff defaults.
- **mypy** is configured with `disallow_untyped_defs = true` and scoped to `src/` only.
- **Release pipeline caching is deliberately disabled** to prevent cache poisoning attacks.
- **`{{ 'LICENSE' if cookiecutter.include_apache_license }}`** — the LICENSE file is conditionally generated; the filename itself is a Jinja2 expression.
