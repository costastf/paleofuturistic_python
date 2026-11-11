# ADR-0019: Conventional Commits drive the changelog, not the version

- **Status**: accepted
- **Date**: 2026-04-10 (commit linting), 2026-04-14 (release flow)
- **Record written**: 2026-11-11 (backfilled)

## Context

Release notes written by hand are the first thing a release skips. Deriving them from commit
messages needs the messages to parse, and a tool that also infers the version bump from the
same messages, as Release Please and commitizen's autorelease do, turns a `feat:` typed in a
hurry into a minor release nobody meant.

## Decision

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/), checked by
`lint.commitizen` as a commit-msg hook and over the unpushed range in the gate. commitizen
generates the changelog from the commits since the last tag, grouped by type through a
`change_type_map`. The version bump is an explicit choice: `./workflow.cmd release -i <type>`,
with `cz bump --version-files-only` writing the version through uv's version provider so
`pyproject.toml` and `uv.lock` move together. Autorelease is not used.

## Consequences

- A commit prefix decides where a line lands in the changelog and nothing else.
- The lint step rejects a message that does not parse, so the history stays usable as release
  notes.
- The changelog is incremental and lives on the docs page the nav shows (ADR-0031).

## References

- Commits `6f2f433` (commit-message linting), `d0a2880` (release flow with `cz bump`).
- [Design principles: Conventional Commits drive the release notes](../explanation/design-principles.md#conventional-commits-drive-the-release-notes).
