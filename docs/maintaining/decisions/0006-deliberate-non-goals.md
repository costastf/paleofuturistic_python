# ADR-0006: Deliberate non-goals

- **Status**: accepted
- **Date**: 2026-07-28; the 3.11 floor on 2026-10-26
- **Record written**: 2026-11-11 (backfilled)

## Context

A scaffold that tries to be a framework starter, a service template and a monorepo layout at
once ends up with switches for each and tests for every combination. The template's job is one
publishable Python package with a complete development cycle around it.

## Decision

Four things the template does not do:

- **No framework choice.** It generates a library. FastAPI, Django, Click and the rest are
  dependencies a project adds.
- **No monorepo support.** One package, one repository.
- **No Python below the chosen minimum, which is at least 3.11.** Python 3.10 was supported from
  July 2026 and dropped again in October 2026, so that `tomllib` is always in the standard
  library and the `tomli` fallback could go.
- **No host-specific assumptions in the development cycle.** GitHub and GitLab differ only in
  `_CI/tasks/<host>.py` and the pipeline file; every other task runs identically.

## Consequences

- The questionnaire stays short, and the test matrix stays at two knobs (host and Pages) plus
  one matured cell.
- Variants that need a different package shape are a different template, not a question here.
- Any new host-specific behaviour has to fit the contract both host modules expose; it cannot
  leak into the shared tasks.

## References

- Commits `5531689` (stated), `490daa5` (3.10 added), `059eb2c` (3.10 dropped), `71878fb` (tomli fallback removed).
- [Design principles: What we deliberately do not do](../explanation/design-principles.md#what-we-deliberately-do-not-do).
