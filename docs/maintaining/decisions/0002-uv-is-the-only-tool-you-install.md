# ADR-0002: uv is the only tool you install

- **Status**: accepted
- **Date**: 2025-03-17
- **Record written**: 2026-11-11 (backfilled)

## Context

The lineage this template forked from asked a new contributor for a system Python, pipx,
virtualenv, pipenv and pip-tools, and later revisions of this template still had tox,
pre-commit and commitizen installed separately. Each tool had its own configuration surface,
cache and update cadence, and a fresh checkout was a sequence of installs before the first
command worked.

## Decision

uv does every Python operation: it fetches interpreters, creates and syncs the virtualenv,
resolves and writes the lockfile, runs every tool through `uv run`, builds with `uv_build`,
publishes with `uv publish`, and runs copier itself through `uvx`. Everything that used to be
installed separately is a dependency group inside the project (ADR-0005). The uv version is an
exact `[tool.uv] required-version` pin, so every machine and every job runs the same resolver.
uv arrived in March 2025; the last separate install, pipx, left the documentation in October
2025.

## Consequences

- One configuration surface: `pyproject.toml` and `uv.lock`. No requirements files, no Pipfile.
- The template is bound to uv's lifecycle. uv is pre-1.0, so a minor release may change
  behaviour, which is why `bump-uv` says so loudly when a bump crosses a minor (ADR-0008).
- An exact pin that lags does not merely age, it refuses to run. That is the reason the pin is
  stamped fresh at generation rather than inherited from the template (ADR-0008).
- twine remains only for `twine check`; uv does the upload.
- `pyproject.toml` stays valid against PEP 517, 518 and 621, so any compliant backend could build
  it if uv had to be replaced. The migration cost would be one template revision and a
  `copier update`.

## References

- [How uv is used](../../using/explanation/how-uv-is-used.md).
- [Design principles: uv is the only tool you install](../explanation/design-principles.md#uv-is-the-only-tool-you-install).
