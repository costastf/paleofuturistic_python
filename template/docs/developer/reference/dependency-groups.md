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

## How CI picks them up

The CI workflow installs only the group it needs for each job — `lint` job installs the `lint` group, `test` job installs `test`. This keeps job containers small and parallel-safe.

The container images built by `./workflow.cmd container.publish` cache the `dev` group's resolution so subsequent CI runs skip the install step.

## See also

- [Add a dependency](../how-to/add-a-dependency.md) — adding to any group.
- [Configuration files](configuration-files.md) — where the groups are declared.
