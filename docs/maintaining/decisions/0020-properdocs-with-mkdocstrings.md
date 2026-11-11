# ADR-0020: properdocs with mkdocstrings

- **Status**: accepted
- **Date**: 2026-05-27 (mkdocs from 2024-11-18)
- **Record written**: 2026-11-11 (backfilled)

## Context

Documentation was plain mkdocs with a hand-picked plugin set that every project had to pin and
configure the same way. Sphinx was considered and is more capable, and that capability was not
needed: the API reference should come from the docstrings without an `.rst` layer in between.

## Decision

Both sites build with [properdocs](https://properdocs.org/), mkdocs with a curated plugin set,
pinned by exact version in the `document` group and, for this repository, in
`[tool.properdocs]`. mkdocstrings renders the API reference from Google-style docstrings
straight out of `src/`; `include-markdown` pulls the README into the index page. The build runs
`--strict` inside the gate, so a broken cross-reference or a page missing from the nav fails
the push rather than the release.

## Consequences

- One version to bump for the docs toolchain, and the same theme and plugins everywhere.
- `properdocs gh-deploy` is a Python command resolved from the lockfile, which is what lets the
  Pages deploy stay inside the SBOM (ADR-0004, ADR-0037).
- A docstring edit is a documentation edit; `document.serve` watches `src/` for that reason.

## References

- Commits `6dbb96f` (mkdocs), `8ce5eff` (properdocs).
- [Design principles: properdocs](../explanation/design-principles.md#properdocs-not-vanilla-mkdocs-with-mkdocstrings-for-api-docs).
