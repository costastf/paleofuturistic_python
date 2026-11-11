# ADR-0017: ty replaces mypy

- **Status**: accepted
- **Date**: 2026-03-30
- **Record written**: 2026-11-11 (backfilled)

## Context

Type checking was the slowest step in the lint gate, and mypy's configuration surface was the
one place the toolchain did not share a vendor with uv and Ruff.

## Decision

[ty](https://github.com/astral-sh/ty), Astral's type checker, runs over `src/`, `_CI/tasks/`
and `tests/`, with `_CI/lib/vendor` as an extra path so the vendored Invoke resolves. It is a
whole-program step in the gate: a signature change surfaces in its callers, so the commit hook
never narrows it to the staged files. Where ty is right about an upstream annotation that is
wrong, the suppression is scoped to the module and the lines involved, as the eleven
`invalid-type-form` tags in `sbom.py` are, so that ty itself reports the day the tag is no
longer needed.

## Consequences

- Speed, and one vendor's quality bar across uv, Ruff and ty.
- ty is pre-1.0 and pinned exactly; a bump can add checks, as it did when it learned to model
  the `py-serializable` mixins. Pins move deliberately and the gate says what changed.
- mypy compatibility gaps surface occasionally and are accepted.

## References

- Commit `b462aa3`, "add ty type checker and pip-audit security commands"; `c485092` for the scoped suppression.
- [Design principles: ty replaces mypy](../explanation/design-principles.md#ty-replaces-mypy).
