# Dependency groups

The template uses [PEP 735 dependency groups](https://peps.python.org/pep-0735/) (uv's first-class support for them) to separate dev-time tooling from runtime requirements. Each group corresponds to one workflow task family.

## Runtime

The `[project.dependencies]` list in `pyproject.toml`. These ship in the published wheel. Add via:

```bash
uv add <package>
```

## Dev-time groups

Listed under `[dependency-groups]` in `pyproject.toml`. They're installed by `develop.bootstrap` and on demand by individual workflow tasks, but never end up in the wheel.

| Group | Packages | Used by |
| --- | --- | --- |
| `dev` | Aggregator that pulls in every group below. | Default `uv sync` target; convenient for IDE setup. |
| `develop` | `pre-commit`, `commitizen`, `tomlkit` | `./workflow.cmd develop.*`, `release.*` (commitizen). |
| `lint` | `ruff`, `pylint`, `ty`, `complexipy` | `./workflow.cmd lint` and `format`. |
| `test` | `pytest`, `pytest-cov`, `pytest-xdist`, `pytest-env`, `pytest-metadata`, `pytest-html`, `coverage`, `tox`, `tox-uv` | `./workflow.cmd test`. |
| `document` | `properdocs`, `mkdocstrings[python]`, `mkdocs-include-markdown-plugin` | `./workflow.cmd document`. |
| `quality` | `pyscn` | `./workflow.cmd quality`. |
| `security` | `pip-audit`, `cyclonedx-py` | `./workflow.cmd secure`. |

## Adding to a group

```bash
uv add --group <group-name> <package>
```

This updates both `pyproject.toml` and `uv.lock`. Commit both. See [How-to: add a dependency](../how-to/add-a-dependency.md) for the full flow.

## Why everything is pinned, and what bounds the rest

Every entry in every group is pinned to an exact version, and `[tool.uv] exclude-newer`
carries a fixed date that bounds the transitive closure. Together they mean a resolution
only changes when a commit changes it.

That date used to be a rolling `"1 week"` window, which moved forward on its own — so a
newly published package could alter a resolution, and turn a gate red, with nothing in the
history to explain it. A fixed date trades automatic freshness for that guarantee.

**The date was stamped with this project's generation date**, not inherited from the
template. A literal carried in the template would recede further into the past the longer
the template went unbumped, so a project generated later would start life pinned to stale
packages. Stamping means the boundary was current on day one and is frozen from then on.

The consequence is that **upgrades are deliberate**. To take newer versions:

1. Raise `exclude-newer` to today's date.
2. Re-resolve (`uv lock --upgrade`) and run the full QA cycle.
3. Commit the date, the pin bumps and `uv.lock` **together** — a boundary that disagrees
   with the pins is the confusing state this setup exists to prevent.

`[tool.docker-versions]` is pinned the same way, by tag *and* digest. When bumping uv,
change the version in the tag and the digest together: a reference carrying both resolves
to the digest, so a bumped tag with a stale digest silently keeps the old image.

## The uv pin, and the one command that moves it

uv gets its own treatment because `[tool.uv] required-version` is an **exact** match: a stale
uv pin does not merely lag, it refuses to run. And the version appears in five places that
must agree:

| Where | Why |
|---|---|
| `[tool.uv] required-version` | the constraint every `uv` invocation checks |
| `uv==` in the `test` group | tox-uv installs a uv binary into `.venv/bin` that would otherwise shadow the image's |
| `uv_build` upper bound in `[build-system]` | the build backend ships in lockstep with uv |
| the `base-image` tag in `[tool.docker-versions]` | CI runs inside that image |
| `uv.lock` | resolved from the `test` group entry |

Like the quarantine date, **the pin was the newest release that had been public for a week
when this project was generated** — not a literal inherited from the template, which would
have grown staler the longer the template went unbumped.

It does not advance on its own. This moves all five together, re-resolving the image digest
and the lockfile in one step:

```bash
./workflow.cmd develop.bump-uv
```

It picks the newest release at least **7 days** old — long enough that a same-day release
withdrawn hours later never reaches you, and the reason the pin is always resolvable under an
`exclude-newer` stamped at generation. It refuses a version the `uv-build` backend has not
published, says nothing changed rather than pretending, and warns when a bump crosses a minor
version, because uv is pre-1.0 and minor releases may break behaviour.

To take a specific version, including one newer than the cool-down allows:

```bash
./workflow.cmd develop.bump-uv --version=0.12.1
```

**Editing any of those five by hand is the failure this command exists to avoid** — most of all
the tag, whose digest has to be re-resolved with it.

## How CI picks them up

The CI workflow installs only the group it needs for each job — `lint` job installs the `lint` group, `test` job installs `test`. This keeps job containers small and parallel-safe.

The container images built by `./workflow.cmd container.publish` cache the `dev` group's resolution so subsequent CI runs skip the install step.

## See also

- [Add a dependency](../how-to/add-a-dependency.md) — adding to any group.
- [Configuration files](configuration-files.md) — where the groups are declared.
