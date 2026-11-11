# ADR-0032: Dependency-Track upload removed

- **Status**: accepted
- **Date**: 2026-11-10 (introduced 2026-04-14)
- **Record written**: 2026-11-11 (backfilled)

## Context

From April 2026 the release flow could upload the SBOM to an OWASP Dependency-Track server,
behind an `integrate_dependency_track` question, two secrets, a `secure.sbom-upload` task and
a developer how-to. It tied every generated project to one SCA platform, carried credentials
the template had no business knowing about, and added a knob to the test matrix for a feature
most projects left off.

## Decision

The upload is gone. The SBOM is still composed, validated and shipped inside every wheel
(ADR-0012); which platform reads it, and with what credentials, is each organisation's call.
Copier no longer asks the question, and an answer left in `.copier-answers.yml` has no effect.
An organisation that wants the upload adds it as a task in `local.py` and calls it from its
pipeline after publishing.

## Consequences

- The matrix lost an axis; the remaining knobs are the host and Pages.
- The migration note tells updating projects which secrets to delete and where the upload would
  go if they still want it.

## References

- Commits `c01c8a8` (introduced), `1e83250` (removed).
- [Upgrading past the Dependency-Track removal](../../using/how-to/update-existing-project-with-copier.md#upgrading-past-the-dependency-track-removal).
