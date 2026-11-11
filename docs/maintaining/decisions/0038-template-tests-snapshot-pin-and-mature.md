# ADR-0038: Template tests generate from a snapshot, pin the uv version, and run one matured cell

- **Status**: accepted
- **Date**: 2026-04-24 (matrix), 2026-08-04 (pinned uv), 2026-09-08 (matured cell), 2026-11-10 (snapshot)
- **Record written**: 2026-11-11 (backfilled)

## Context

The template's own tests generate projects and run their gates. Three things about that needed
settling. Copying the whole working tree into the snapshot let caches, `.DS_Store` files and
agent state ship into generated projects during tests. Generation stamps the newest eligible uv
(ADR-0008), which the ambient uv in CI cannot satisfy, so every matrix cell failed on the
version mismatch. And a freshly generated project is a day-one project: the scaffold keeps
coverage at 100% and the ratchet dormant, and there is no remote for the badge, so the four
knob cells never exercised the ratchet, the coverage union, the badge slug or the dependency
audit.

## Decision

- The snapshot is what `git add -A` would commit: tracked files plus untracked ones git ignores
  nothing of, minus deleted ones. Uncommitted edits are tested; ignored files stay out.
- `TEMPLATE_UV_VERSION` pins what generation stamps to the template's committed pin, read from
  the template source so it follows `maintain.bump-uv`.
- The matrix is the cartesian product of host and Pages, four cells, plus one matured cell: a
  GitHub project with the smoke test replaced by one that leaves an import uncalled, a
  version-gated module so the union exceeds any single interpreter, and an origin remote. The
  dependency audit rides with that cell only, so a transient advisory-service error fails one
  job instead of five. Each cell runs `preflight --write`, then the bare `preflight` to prove
  the tree it wrote passes the read-only gate, then checks that nothing was left untracked.
- `test.matrix` is sequential by default; CI fans the cells out across runners instead.

## Consequences

- Four entry points, fastest first: `test.invariants`, `test`, `test.combo`, `test.matrix`.
- The matured cell is one extra cell rather than a third axis, because nothing it touches
  interacts with the knobs.
- The litter check lives here and not in generated projects, because it is only sound on a
  freshly generated, fully committed tree.

## References

- Commits `64f75a5` (matrix), `6cf4733` (`TEMPLATE_UV_VERSION`), `16251c1` (matured cell), `f73f484` (audit in one cell), `5295804` (snapshot).
- [Test the template](../how-to/test-the-template.md).
