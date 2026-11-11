# ADR-0008: Reproducibility by pin

- **Status**: accepted
- **Date**: 2026-08-03 (quarantine date), 2026-08-04 (uv pin at generation)
- **Record written**: 2026-11-11 (backfilled)

## Context

Three things could change what a project resolved to without a commit changing it:

- `[tool.uv] exclude-newer` was a rolling `"1 week"`, so a package published yesterday could
  enter the resolution today and turn a gate red with nothing in the history to explain it.
- The uv pin in the template aged between maintainer bumps, and because `required-version` is
  an exact match, a stale pin does not lag, it refuses to run. A project generated months after
  the last bump started on an obstructive uv.
- The base image for CI is referenced by tag and by digest, and such a reference resolves to the
  digest. A bumped tag beside a stale digest silently keeps building the old image.

## Decision

- Every entry in every dependency group is an exact version, and `exclude-newer` is a fixed date
  that bounds the transitive closure. `tasks_render.py` stamps it with the generation date, so a
  new project's boundary is current on its first day and frozen from then on. This repository's
  own boundary is maintained by hand and re-resolved in the same commit.
- The uv pin is resolved at generation: the newest release that has been public for at least
  seven days and that `uv-build` has published too. The committed pin is the offline fallback
  and the uv this repository's CI installs. `TEMPLATE_UV_VERSION` forces a version so the
  template's own tests generate deterministically.
- The version and the image digest are never written separately. `develop.bump-uv` moves the
  four literals in a project's `pyproject.toml`, re-resolves the digest, and relocks;
  `maintain.bump-uv` moves the template's ten values, one digest per supported Python. Either
  refuses to write a half-bumped file, and both say loudly when a bump crosses a minor version.

## Consequences

- A resolution changes only when a commit changes it. Upgrades are deliberate: raise the date,
  relock, land the date and the pins together.
- There is no bot and no scheduled bump. Freshness for new projects comes from generation, not
  from the committed literal.
- The seven-day cool-down is also what keeps a stamped uv pin resolvable under a quarantine date
  stamped the same day.
- Raising the quarantine date is still a three-step manual flow; a `develop.refresh-deps` task is
  the open follow-up.

## References

- Commits `0ac5998` (fixed quarantine, resolved lockfile at generation), `6cf4733` (uv pin at generation, `bump-uv`).
- [Bump the uv pin](../how-to/bump-the-uv-pin.md), [How uv is used](../../using/explanation/how-uv-is-used.md).
