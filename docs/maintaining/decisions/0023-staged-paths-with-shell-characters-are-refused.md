# ADR-0023: Staged paths with spaces or shell characters are refused

- **Status**: accepted
- **Date**: 2026-09-09
- **Record written**: 2026-11-11 (backfilled)

## Context

`preflight.staged` reads the staged paths and forwards them to each per-file step as a
space-separated `--paths` value, and when formatting fails it prints
`./workflow.cmd format --paths="…"` back for the reader to paste. A path containing a space
split into two fragments that matched no filter and were silently dropped, which is a hook
passing because it checked nothing. A path containing a shell metacharacter, and
`src/a";id;".py` is a valid filename, would have been printed as a command to run.

## Decision

Staged paths are split on lines, not whitespace, so a path with a space arrives whole, and any
path containing a character from `UNSAFE_IN_PATHS` fails the task with a message naming the
paths and the two ways out: rename them, or run the whole-project `preflight`. Paths that no
longer exist in the worktree are dropped, since a tool cannot read them.

## Consequences

- A hook that cannot check a file says so instead of passing.
- The `--paths` convention stays space-separated throughout the workflow, which is what every
  task's flag parsing expects.

## References

- Commit `10011e5`.
- `staged_files` in `template/_CI/tasks/preflight.py`.
