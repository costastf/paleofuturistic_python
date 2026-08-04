# How uv is used

This template uses [uv](https://docs.astral.sh/uv/) for every Python operation in a generated project: creating virtualenvs, installing dependencies, resolving the lockfile, publishing to PyPI, even fetching Python interpreters. This page explains why, and what the template gives up to get there.

## What uv replaces

In an older lineage of this template, a fresh checkout required: a system Python, pipx, virtualenv, pipenv, pip-tools, tox-uv, and twine. Each had its own configuration surface, its own caching behaviour, and its own update cadence.

uv replaces all of them with a single Rust binary that:

- Installs and pins Python interpreters per project (no system-Python dependency).
- Resolves and locks dependencies (no `pip-compile`, no `pipenv`).
- Creates and manages virtualenvs (no `python -m venv`).
- Publishes to PyPI (no `twine`).
- Runs tools in ephemeral environments (`uvx`, no global `pipx`).

## Why this is worth the lock-in

**Speed.** uv resolves a typical lockfile in under a second. pipenv took tens of seconds — sometimes minutes on large dependency graphs. The dev loop genuinely feels different.

**One config surface.** `pyproject.toml` plus `uv.lock`. Two files. No `requirements.in`, no `requirements.txt`, no `Pipfile`, no `Pipfile.lock`.

**Reproducibility by default.** uv's lockfile is platform-portable and hash-locked. CI and a contributor's laptop get bit-identical environments without opt-in flags.

**Dependency groups, not extras-abuse.** uv first-classed PEP 735 dependency groups, which are exactly what's needed for the dev/lint/test/document/security split. The template previously used `[project.optional-dependencies]` and had to explain that those aren't really "optional," they're internal grouping. See [Design principles](../../maintaining/explanation/design-principles.md#why-groups-not-extras) for the full rationale.

## What the template gives up

**Tool risk.** uv is one company's project (Astral). If they pivot or the project stalls, a project built on it is more exposed than one that stuck with the pip/build/twine stack maintained by the PyPA. The template mitigates by:

- Keeping the generated `pyproject.toml` valid against PEP 517 / 518 / 621 — any PEP-compliant tool could build it.
- Not relying on uv-specific syntax beyond dependency groups (which are themselves standardised).

**Older Python support.** uv itself supports far older interpreters than the template targets, so the project's chosen `min_python_version` (as low as 3.10) isn't a constraint uv adds — if a generated project wanted to support 3.8, uv wouldn't stop it; that configuration just isn't one the template tests.

**Familiarity.** Some contributors will arrive expecting `pip install -r requirements.txt`. The generated README points them to `./workflow.cmd bootstrap` and the [tutorial that walks through generating a first project](../tutorials/generate-your-first-project.md).

## Which uv version a new project gets

Because `[tool.uv] required-version` is an **exact** pin, a stale uv version does not merely
lag — it refuses to run. A literal carried in the template would age between bumps, so a
project generated months after the last one would start life on an obstructive pin.

Generation therefore resolves it: a new project is pinned to the **newest uv release that has
been public for at least a week**. The cool-down means a same-day release withdrawn hours later
never reaches anyone, and it is why the pin is always resolvable under the `exclude-newer`
boundary stamped at the same moment.

That single version is written to five places at once — the constraint, the `test` group's `uv`
entry, the `uv_build` upper bound, the base image's tag with a freshly resolved digest, and
`uv.lock`. They are never written separately: a tag carrying both a version and a digest
resolves to the **digest**, so a bumped tag beside a stale digest would silently keep building
the old image.

From then on the version is frozen and maintaining it belongs to the project, not the template.
Nothing chases it, and no bot opens pull requests; `./workflow.cmd develop.bump-uv` inside the
project moves all five together whenever its developers choose to.

Two escape hatches:

- **Pin it explicitly.** Set `TEMPLATE_UV_VERSION` before generating to get exactly that
  version — which is also how the template's own test suite stays deterministic.
- **Generate offline.** If PyPI cannot be reached, generation keeps the version the template
  committed and says so. It never fails for want of a network, and never falls back silently.

## When this decision could be revisited

If two of these became true together:

1. uv's lockfile format incompatibly changed and broke existing projects.
2. A maintained alternative offered comparable speed and PEP 735 support.

Then the cost of migration would be one template revision and a `copier update`. The decision is reversible at the template level.

## See also

- [Design principles](../../maintaining/explanation/design-principles.md) — why dependency groups replaced extras.
