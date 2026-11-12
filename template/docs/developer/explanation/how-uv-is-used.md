<!-- canonical: rendered from docs/using/explanation/how-uv-is-used.md in the paleofuturistic_python template repo by `./workflow.cmd maintain.sync-docs`. Edit there, not here. -->
# How uv is used

This project uses [uv](https://docs.astral.sh/uv/) for every Python operation: creating virtualenvs, installing dependencies, resolving the lockfile, publishing to PyPI, even fetching Python interpreters. This page explains why, and what the template gives up to get there.

## What uv replaces

In an older lineage of this template, a fresh checkout required: a system Python, pipx, virtualenv, pipenv and pip-tools. Each had its own configuration surface, its own caching behaviour, and its own update cadence.

uv replaces all of them with a single Rust binary that:

- Installs and pins Python interpreters per project (no system-Python dependency).
- Resolves and locks dependencies (no `pip-compile`, no `pipenv`).
- Creates and manages virtualenvs (no `python -m venv`).
- Publishes to PyPI (`uv publish`; twine remains only for `twine check` on the built files).
- Runs tools in ephemeral environments (`uvx`, no global `pipx`).

## Why this is worth the lock-in

**Speed.** uv resolves a typical lockfile in under a second. pipenv took tens of seconds — sometimes minutes on large dependency graphs. The dev loop genuinely feels different.

**One config surface.** `pyproject.toml` plus `uv.lock`. Two files. No `requirements.in`, no `requirements.txt`, no `Pipfile`, no `Pipfile.lock`.

**Reproducibility by default.** uv's lockfile is platform-portable and hash-locked. CI and a contributor's laptop get bit-identical environments without opt-in flags.

**Dependency groups, not extras-abuse.** uv first-classed PEP 735 dependency groups, which are exactly what's needed for the build/develop/lint/test/document/quality/security split. The template previously used `[project.optional-dependencies]` and had to explain that those aren't really "optional," they're internal grouping. See [Design principles](design-principles.md#why-groups-not-extras) for the full rationale.

## What the template gives up

**Tool risk.** uv is one company's project (Astral). If they pivot or the project stalls, a project built on it is more exposed than one that stuck with the pip/build/twine stack maintained by the PyPA. The template mitigates by:

- Keeping the generated `pyproject.toml` valid against PEP 517 / 518 / 621 — any PEP-compliant tool could build it.
- Not relying on uv-specific syntax beyond dependency groups (which are themselves standardised).

**Older Python support.** uv itself supports far older interpreters than the template targets, so the project's chosen `min_python_version` (as low as 3.11) isn't a constraint uv adds — if this project wanted to support 3.8, uv wouldn't stop it; that configuration just isn't one the template tests.

**Familiarity.** Some contributors will arrive expecting `pip install -r requirements.txt`. The README points them at `./workflow.cmd`, and [First-run setup](../tutorials/first-run-setup.md) walks the whole loop.

## When this decision could be revisited

If two of these became true together:

1. uv's lockfile format incompatibly changed and broke existing projects.
2. A maintained alternative offered comparable speed and PEP 735 support.

Then the cost of migration would be one template revision and a `copier update`. The decision is reversible at the template level.

## See also

- [Design principles](design-principles.md) — why dependency groups replaced extras.
- [Dependency groups](../reference/dependency-groups.md) — the groups this project ships with, and the uv pin.
