# ADR-0005: Dependency groups, not extras

- **Status**: accepted
- **Date**: 2025-09-10
- **Record written**: 2026-11-11 (backfilled)

## Context

Development tooling used to sit under `[project.optional-dependencies]`. Extras are a feature of
the published package: `pip install pkg[lint]` is a real command a user can run, and the lint
toolchain is not a feature of the library. The docs had to explain that these extras were not
really optional, they were internal grouping.

## Decision

Development tooling lives in [PEP 735 dependency groups](https://peps.python.org/pep-0735/),
one group per task family (`build`, `develop`, `document`, `lint`, `quality`, `security`,
`test`), with `dev` as an aggregator of `include-group` entries. `uv run` syncs them on demand;
`lint.pyproject` validates the table against the dependency-groups specification, including
that every `include-group` resolves.

## Consequences

- Nothing in a group ever reaches the wheel or is user-installable.
- A package goes in the group whose task runs it. `uv run` installs every group into one
  `.venv` regardless, but the SBOM scopes dev groups as `optional`, and the audit and a reader of
  `pyproject.toml` take the groups at their word.
- The deps image syncs every group (`uv sync --all-extras --dev`), so CI jobs install nothing.

## References

- Commit `d79c66b`.
- The *Dependency groups* reference in the generated-project developer docs,
  [Design principles: Why groups, not extras](../explanation/design-principles.md#why-groups-not-extras).
