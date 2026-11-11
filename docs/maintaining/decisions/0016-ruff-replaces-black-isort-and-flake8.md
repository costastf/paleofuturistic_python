# ADR-0016: Ruff replaces Black, isort and flake8; pylint stays for what Ruff lacks

- **Status**: accepted
- **Date**: 2024-11-18; pylint and complexipy added 2026-03-30 and 2026-04-10
- **Record written**: 2026-11-11 (backfilled)

## Context

The formatter, the import sorter and the linter used to be three tools with three
configuration blocks, three caches and three sets of version pins, and they disagreed with
each other often enough that a project needed a compatibility section for each pair.

## Decision

Ruff does formatting (`ruff format`), import sorting (`ruff check --select I --fix`) and
linting (`ruff check` with `select = ["ALL"]` and a short, commented ignore list). pylint stays
for the checks Ruff does not have, and complexipy adds cognitive complexity over `src/`. All
three are held to one line length, 120, and the same rule set applies to `src/`, `tests/` and
`_CI/tasks/`, with `_CI/` carrying its own lighter `pyproject.toml` for the few rules that make
no sense in task code. This repository's own `tests/` and `_CI/` are judged by the same
configuration.

## Consequences

- One tool, one configuration block, one cache for most of the lint gate; pylint is the slow
  step and runs last, behind everything cheaper that could also fail.
- pylint's role is expected to shrink as Ruff grows; nothing is configured twice on purpose.
- A rule disabled for one line is disabled in code with `# noqa`, with the reason beside it, not
  in the configuration.

## References

- Commits `ac2147c` (Ruff), `8aaea04` (pylint in the task set), `86e6c1d` (complexipy).
- [Design principles: Ruff replaces Black + isort + flake8](../explanation/design-principles.md#ruff-replaces-black-isort-flake8-and-most-of-pylint).
