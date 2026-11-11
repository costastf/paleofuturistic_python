# ADR-0028: The audit reads `uv.lock` directly and retries a run with no verdict

- **Status**: accepted
- **Date**: 2026-09-08 (retry), 2026-09-09 (lockfile)
- **Record written**: 2026-11-11 (backfilled)

## Context

Two narrower forms of the audit each saw less than the lockfile. `pip-audit` with no `-r`
enumerates installed distributions, so a Linux runner omitted whatever a platform marker, an
extra or an unsynced group kept out of the venv. `uv export` produces a universal requirements
file that keeps the markers, and pip-audit evaluates them, so the same pins were skipped a step
later. And a url source matched the string form of the source table and was audited as though
a PyPI release of that name existed.

Separately, pip-audit walks the advisory database one package at a time with no retry of its
own, so a single reset connection failed a run that had established nothing, and the first
retry logic keyed on a Python traceback, which would have gone quietly inert the day pip-audit
caught the exception and printed a message instead.

## Decision

- `secure.audit` reads `[[package]]` entries straight out of `uv.lock`: every version for every
  interpreter and platform, no markers to evaluate, no groups to remember. Only packages with a
  `registry` key in their source table are audited; git, URL and path sources are named on
  stdout as unauditable rather than dropped silently. One requirement file per version slot,
  because pip-audit refuses a file naming a package twice and a lockfile legitimately pins two
  versions behind different markers.
- `_CI/lib/vendor.txt` is audited by name, the vendored tree having no `.dist-info`.
- `--strict`, so a package the service cannot resolve fails the audit instead of landing in a
  skip table under exit 0.
- A run is retried only while its output contains none of the phrases pip-audit prints when it
  reached a conclusion either way. A finding is never retried. Three attempts, three then six
  seconds apart.

## Consequences

- Everything written about the audit can claim every locked version.
- What it still cannot see: a hand-edited vendored file, and `[build-system] requires`.
- The retry bias is deliberate: the worst it can do to a genuine finding is nothing.

## References

- Commits `8d22ec5` (a reset connection is not a finding), `10011e5` (audit the lockfile), `a3d7b9f` (a url source is not a registry source).
- [SBOM and security model: Layer 1](../../using/explanation/sbom-and-security-model.md#layer-1-pip-audit).
