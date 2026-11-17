# ADR-0055: Generation runs no shell

- **Status**: accepted
- **Date**: 2026-11-17

## Context

`copier.yml` ran two tasks after writing a project: `tasks_render.py`, the Python hook that
installs the license, stamps the quarantine boundary and the uv pin and sets the launcher's
executable bit, and a second command that resolved the lockfile with the uv just pinned,
`uvx uv@$(sed … pyproject.toml) lock`. The second needed a POSIX shell for its command
substitution and `sed` for the read, so generation failed from a Windows command prompt
with an error about `sed`, after every file had been written. No document said generation
needed a POSIX shell.

## Decision

The lock moves into `tasks_render.py`, which reads the pin out of the rendered
`pyproject.toml` with the same pattern the other stamps use and runs `uvx uv@<version> lock`
as a fixed argument list, no shell. `copier.yml` runs that one task and nothing else.

A pyproject with no pin stops generation with a message, as the failed `sed` did without one.
A resolution that fails stops it too, as before.

## Consequences

- Generation needs Python, which copier already needs, and `uvx` on the path, which the
  docs ask for. It needs no shell of any kind.
- The hook's four steps and the lock run in one process, in the order the lock depends on.
- An invariant holds `copier.yml` to one task with no command substitution in it, and holds
  the hook's lock function to reading the pin from the project rather than repeating it.

## References

- [ADR-0008](0008-reproducibility-by-pin.md), which put the lock at generation.
- [Generation internals](../reference/generation-internals.md).
