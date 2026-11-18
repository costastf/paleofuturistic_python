# ADR-0060: The 3.11 floor is its current patch release

- **Status**: accepted; moves the pin ADR-0056 held back
- **Date**: 2026-11-18

## Context

ADR-0056 pinned pymdown-extensions at 12.3 on both sides because 13.0 requires Python 3.11.5
and a generated project could floor at `>=3.11`, which admits 3.11.0. The pin was two
releases behind on the day it was written, with the floor as the only reason.

Python 3.11 has been in security-only maintenance since April 2024. Every patch below the
current one is a release with holes the current one closes, and nothing in the template
needs to run on them. The current release is 3.11.18, published 2026-10-25; the deps image
the template pins, uv 0.13.7 on `python3.11-trixie-slim`, already carries it.

A floor spelled to the patch has one consequence for uv. With `.python-version` saying
`3.11`, uv resolves the request to whatever 3.11 the machine has and then refuses it against
a `>=3.11.18` floor, telling the user to repin, instead of fetching one that fits. With
`.python-version` saying `3.11.18`, it fetches that release.

## Decision

A project answering `3.11` floors at `3.11.18`, in `requires-python` and in
`.python-version`, through a computed copier value, `python_floor`, that maps the series to
its patch floor and leaves every other series at its minor. The value is never asked and never
stored in the answers file; it is derived from `min_python_version` on every render, so moving
the floor is a template change and an update.

pymdown-extensions moves to 13.1 on both sides, its newest release.

Everything tagged per minor reads the minor: the classifiers, the tox environments, the
`target-version` ruff infers, the base image tag and the digest `develop.bump-uv` resolves.
The two readers of `requires-python` that feed those, `_CI/info.py` and the render hook, take
the major and minor and ignore a patch.

## Consequences

- The first `uv run` in a 3.11 project fetches 3.11.18 when the machine has no such
  interpreter. The upgrade how-to says so, and says to keep the patch spelling over a
  minor-only `.python-version` set by hand.
- The patch floor is a literal in `copier.yml`. When 3.11.19 ships, the literal moves and
  every 3.11 project picks it up at its next update; nothing automates that, and the series
  ends in October 2027.
- An invariant holds `.python-version` to the same version `requires-python` floors at, and
  holds the 3.11 floor to a patch. Another holds the pymdown-extensions pin equal on both
  sides.
- The parent's own floor is 3.12 and needs nothing.

## References

- [ADR-0056](0056-fenced-code-nests-in-lists.md), which held the pin back for this floor.
- [ADR-0006](0006-deliberate-non-goals.md), which set the 3.11 floor.
