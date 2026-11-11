# ADR-0003: Vendored Invoke behind one launcher

- **Status**: accepted
- **Date**: 2026-03-30, vendoring moved upstream 2026-08-07
- **Record written**: 2026-11-11 (backfilled)

## Context

Every development action needed one entry point that works on a fresh clone. The candidates:
`make` is universal but whitespace-sensitive and awkward from Python; `just` is a binary to
install; `nox` has to be installed before it can install anything. Invoke is Python-native and
composable, but installing it first would contradict ADR-0002.

## Decision

Invoke and its dependencies are committed under `_CI/lib/vendor/`, and one launcher,
`workflow.cmd`, runs it: a three-line polyglot that sh and Windows `cmd` both read, each
executing `uv run python _CI/lib/vendor/bin/invoke --search-root _CI`. Tasks live in
`_CI/tasks/` as Invoke collections.

The vendored tree is not maintained here. Since August 2026 it is built by
[schubergphilis/vendored_invoke](https://github.com/schubergphilis/vendored_invoke), pinned in
`[tool.vendored-invoke]` by tag and by the commit the tag points at, and copied in verbatim by
`maintain.sync-vendor` into both this repository's `_CI/lib/` and the template's. Two
hand-maintained patches travel with it: one puts the search root on `sys.path` so nothing is
installed, one hard-codes Invoke's version string, which a vendored copy cannot read from package
metadata.

## Consequences

- `./workflow.cmd` works with only uv present, on day one and on day one thousand, and the same
  Invoke runs on every contributor machine and in CI.
- The cost is bytes in the repository, and a tree nobody may hand-edit. `maintain.sync-vendor`
  refuses a dirty working tree so that the diff it produces is the vendored change alone, and an
  invariant checks the two trees are byte-identical.
- The vendored packages ship as source with no `.dist-info`, so the dependency audit names them
  from `vendor.txt` and a hand-edited file is watched by CI rather than audited.
- `_CI/lib` is excluded from ruff, and `ty` gets it as an extra path.

## References

- Commits `6a216d1` (vendored tree tracked), `413f883` (`workflow.cmd` for Windows), `0ccef7d` (upstream vendoring).
- [The _CI tasks architecture](../explanation/the-ci-tasks-architecture.md), [Refresh the vendored invoke](../how-to/refresh-the-vendored-invoke.md).
