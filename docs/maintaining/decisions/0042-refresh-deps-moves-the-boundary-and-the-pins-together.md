# ADR-0042: `develop.refresh-deps` moves the boundary and the pins together

- **Status**: accepted
- **Date**: 2026-11-12

## Context

ADR-0008 fixed the resolution of a project with two things: every dependency entry is an exact
pin, and `[tool.uv] exclude-newer` is a date. Together they mean nothing changes until a
commit changes it, and ADR-0008 closed by noting that the commit was a three-step manual flow:
raise the date, re-resolve, run the gate, land everything together.

The second step was less useful than it read. `uv lock --upgrade` moves only what the pins
leave free, which with exact pins everywhere is the transitive closure. The direct pins, which
are the bulk of what a project depends on, had to be found and moved by hand, one entry at a
time, with no command saying which of them had a newer release under the new date. A flow
that laborious is run rarely, and a boundary left for months is the stale state the date
exists to make deliberate rather than permanent.

## Decision

`develop.refresh-deps` does the mechanical part of the flow and stops before the judgement.
It sets `exclude-newer` to today, or to `--boundary`, asks `uv tree --outdated` under the new
date which direct pins have a newer release, rewrites those pins in place, and runs
`uv lock --upgrade` for the rest. It prints every move, direct and transitive, and ends by
saying to run `preflight` and commit `pyproject.toml` and `uv.lock` together. It does not
commit: the new versions have to pass the gate first, and what to do when they do not is the
owner's call.

The `uv` pin is held back. Its version is tied to the base image's digest, and
`develop.bump-uv` moves the two together (ADR-0008); the refresh says when a newer uv is
available and leaves it there.

The newest version comes from uv, not from a second index client: `uv tree --outdated` already
answers under `exclude-newer`, so a pin never moves past the boundary that was just set. The
pins are rewritten by a pattern that matches one quoted `name==version` entry per line, which
is how every group spells them; the build backend's range and comments do not match.

## Consequences

- Taking newer versions is one command, a gate run, and a commit.
- The date and the pins still move only together. A refresh that is not committed is visible
  in `git status` as two changed files, and the gate judges them as one.
- The output of `uv tree` is parsed as text. A change to that format fails the refresh loudly
  rather than moving a pin to the wrong place, since a line that does not match is ignored and
  the pin it describes stays where it was, which the next refresh reports again.
- This repository's own boundary is still moved by hand. Its groups are pinned the same way,
  so the same task could serve it; that is a change to the parent's task set, not the
  template's.

## References

- [ADR-0008](0008-reproducibility-by-pin.md), whose open follow-up this closes.
- The shipped page `docs/developer/reference/dependency-groups.md` in a generated project
  documents the flow for its developers.
