# ADR-0030: Task commits follow the signing configuration, retried unsigned only on a signing failure

- **Status**: accepted
- **Date**: 2026-08-04
- **Record written**: 2026-11-11 (backfilled)

## Context

`release.bump` and `release.changelog` commit. Hardcoding `--no-gpg-sign` breaks exactly the
repositories that care most about provenance, where a branch rule rejects unsigned commits at
push time. Forcing a signature breaks CI, which usually has no signing key, and a release must
not stop on a documentation commit. A naive "retry unsigned on any failure" would retry a
pre-commit hook failure too, and report a signing problem that does not exist.

## Decision

`shared.commit` tries a signed commit first, letting git decide from `commit.gpgsign`. It
retries with `--no-gpg-sign` only when both guards hold: git was asked to sign, and the failure
is git's own "failed to write commit object" line, which is how a signing failure surfaces
whatever `gpg.format` is set to. The retry says plainly that the commit is unsigned and what
that costs.

## Consequences

- A developer with a key gets signed release commits; CI gets unsigned ones with a warning.
- The cause line above git's summary is format-specific (openpgp and ssh print different
  things), so the marker is the summary line, verified against both formats on git 2.x.

## References

- Commit `6a841e1`, "sign the changelog commit when the repository asks for it".
- `commit` and `signing_requested` in `template/_CI/tasks/shared.py`.
