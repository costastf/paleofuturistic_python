# ADR-0027: Heavy imports stay out of launcher startup

- **Status**: accepted
- **Date**: 2026-05-28 (in-process validation), 2026-09-08 (lazy import)
- **Record written**: 2026-11-11 (backfilled)

## Context

Every `./workflow.cmd` invocation imports every task module, so a module-scope import in any of
them is paid by every task. `cyclonedx-python-lib`'s JSON validator reaches `jsonschema._format`
and builds a lark grammar at import time: 1.0 second of the 1.2 seconds `sbom.py` cost to
import, paid by `./workflow.cmd lint` which never composes an SBOM.

Separately, SBOM validation used to run in a `uv run python` subprocess, because the launcher
puts the vendored tree earlier on `sys.path` than the venv and the vendored tree once carried
its own `jsonschema`, so an in-process import resolved to the wrong copy. That `jsonschema` was
a transitive dependency of the vendoring toolchain, which is no longer vendored.

## Decision

`secure.py` imports `sbom.py` inside the three tasks that compose an SBOM, not at module scope,
and `sbom.py` imports the validator inside `validate_sbom`. With the stray `jsonschema` gone,
validation runs in-process and the subprocess has nothing left to isolate. An invariant asserts
no task module imports `cyclonedx` at module scope.

## Consequences

- Launcher startup is about a tenth of a second, which is what makes one commit hook per
  commit cheap enough to argue for on legibility alone (ADR-0022).
- The vendored tree must contain nothing but what the shipped `_CI/` code imports; the
  `vendor` extra in `_CI/pyproject.toml` is the list, and the upstream build enforces it.

## References

- Commits `7e6c695` (in-process validation), `d63ef9f` (lazy import).
- `template/_CI/tasks/secure.py`, `validate_sbom` in `template/_CI/tasks/sbom.py`.
