# ADR-0059: Formatting conventions are the template's, not configurable

- **Status**: accepted
- **Date**: 2026-11-17

## Context

Three choices in the generated `pyproject.toml` depart from the defaults a reader may expect:
ruff formats at a line length of 120 where Black's default is 88 (ADR-0016), with single
quotes where Black's are double, and checks docstrings against the Google convention where
the template once used numpy (ADR-0020). Whether to make them copier questions, or to revert
to the defaults, or to call the departure a hard break, was an open note. The ruling on the
docstring convention was a hard break with an upgrade note, and neither had been written.

## Decision

The three are the template's, with no question to answer and no way back to the older
choices short of editing the generated file:

- 120 columns, because 88 wraps the signatures and f-strings this tooling is full of, and
  every screen the template's authors have seen is wider.
- Single quotes, because they are quieter on the page; the formatter rewrites either way,
  so no one types them.
- Google docstrings, because mkdocstrings renders them and the sections read as prose.

A question per convention would be three more answers for a project to carry forward on
every update, so that `copier update` could re-render a formatting block nobody wants
changed. A project that disagrees edits `[tool.ruff]` and resolves that block at each update,
which is the same cost a question would hide.

## Consequences

- The upgrade how-to tells a project generated before the docstring switch what its first
  `lint` will report and what the fix is.
- The comments in the generated `pyproject.toml` say why each value differs from the
  default, so the departure reads as a choice and not an oversight.

## References

- [ADR-0016](0016-ruff-replaces-black-isort-and-flake8.md), which set the width.
- [ADR-0020](0020-properdocs-with-mkdocstrings.md), which chose the docstring convention
  with the renderer.
