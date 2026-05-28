# Design principles

The template is opinionated. The choices below were made deliberately, not by accumulation — each replaces something an earlier revision relied on.

## uv is the only tool you install

Earlier revisions asked users to install Python, then `pipx`, then `tox`, then `pre-commit`, then `commitizen`. Today, every one of those is a uv-managed dependency group inside the generated project. You install uv; uv installs the rest.

**Tradeoff:** the template is now bound to uv's lifecycle. If uv goes away or changes lock format incompatibly, the template needs work. We accept that risk because uv has compressed the toolchain to a single binary that's fast enough to run on every commit.

## Ruff replaces Black + isort + flake8 (and most of pylint)

One tool, one config block, one cache. Ruff doesn't yet cover everything pylint does — so pylint stays, but only for the checks Ruff doesn't have. We expect pylint's role to shrink as Ruff grows.

## ty replaces mypy

[ty](https://github.com/astral-sh/ty) is Astral's type checker, written in Rust. It's faster than mypy and shares the Ruff/uv codebase's quality bar. Mypy compatibility issues still surface occasionally; we accept that trade for the speed and consistency.

## pytest, not unittest

The original lineage used `python -m unittest`. We moved to pytest for fixtures, parametrization, coverage integration, and parallel execution via xdist. Unittest test classes still work — pytest discovers them.

## Conventional Commits drive the release notes

Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/) — the lint step rejects anything that doesn't parse. We use them for **automatic release notes**: [commitizen](https://commitizen-tools.github.io/commitizen/) reads the commits since the last tag and groups them by prefix (`feat:`, `fix:`, etc.) into a generated changelog.

We do **not** use commitizen's autorelease mode. The version bump is an explicit choice you make at release time: `./workflow.cmd release -i <major|minor|patch|…>`. Commit prefixes inform changelog structure, not the version number.

## properdocs (not vanilla mkdocs), with mkdocstrings for API docs

properdocs is mkdocs with a curated plugin set. mkdocstrings reads the source directly — no `.rst` files in the middle. Sphinx is more capable; we don't need that capability here.

## SBOMs ship by default

Every release builds a CycloneDX SBOM regardless of whether you've enabled the Dependency Track upload. The SBOM lands in `dist/` alongside the wheel. The cost is one extra build step; the benefit is that supply-chain questions have an answer the day someone asks them.

## Vendored CI tooling

`_CI/lib/vendor/` ships Invoke + its dependencies committed to the repo. `./workflow.cmd` works on a fresh clone with only uv installed — no `pip install invoke` step, no version drift between contributor machines. The vendoring cost is bytes in the repo; the benefit is that the dev cycle is the same on day one as on day one thousand.

## Diátaxis for our own docs

The four sections — Tutorials, How-to, Reference, Explanation — exist because the template's documentation has historically conflated "I want to start" with "I want to understand", and readers got annoyed at both. Diátaxis splits the audiences. This page is in *Explanation* because it tells you *why*; it won't show you *how* to change anything.

## What we deliberately do not do

- **No framework choice.** This is a library scaffold. It does not know about FastAPI, Django, or Click. Add what you need.
- **No monorepo support.** One package, one repo. If you want a monorepo, use a different template.
- **No Python below 3.11.** Async, exception groups, and tomllib are load-bearing.
- **No GitHub-only or GitLab-only assumptions in the dev cycle.** Host-specific code lives in `_CI/tasks/<host>.py`; the rest of the workflow runs identically.

## See also

- [Why a cruft template?](why-a-cookiecutter.md) — why we picked the template format we did.
- [History and lineage](history-and-lineage.md) — what this template was forked from and why.
