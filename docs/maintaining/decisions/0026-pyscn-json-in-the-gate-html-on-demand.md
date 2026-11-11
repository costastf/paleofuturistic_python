# ADR-0026: pyscn produces JSON in the gate and HTML on demand

- **Status**: accepted
- **Date**: 2026-09-04
- **Record written**: 2026-11-11 (backfilled)

## Context

Three things about pyscn were discovered the hard way. It opens a browser as soon as it writes
an HTML report, which made `quality.pyscn-analyze` open the report twice and had a tool reaching
for a browser on a CI runner. It allows one output format per run, so `--html --json` fails and
each format costs a full analysis with its own summary table. And `--quiet`, whose help promises
to suppress output unless issues are found, suppresses the issues too: a failure reported only
"Found 1 quality issue(s)" with no file or line.

## Decision

- Every HTML run passes `--no-open`. Whether a report is worth opening is the task's decision,
  and `is_ci()` is part of it.
- The gate produces JSON only, through `pyscn_json_report`: the badge reads the grade from it,
  and nothing in a hook or a pipeline opens an HTML report. `quality.pyscn-analyze` produces
  both and opens the HTML, for a human who asked.
- `pyscn check` is never `--quiet`. Two lines on a passing run buy the one line that names the
  finding on a failing one.
- `analyze` and `check` are both in the gate and are not a duplicate: `analyze` computes the
  lenient aggregate grade the badge shows, `check` applies the hard thresholds that fail the
  tree.
- Reports are cleared before each run, since pyscn timestamps them and `reports/` would grow
  for as long as the project runs its gate.

## Consequences

- The gate produces what it consumes and nothing else, which is the general rule (ADR-0009).
- A failed analysis leaves the directory empty, so the badge reports that it has no grade to
  read rather than certifying one measured against a tree that has since changed.

## References

- Commits `1bc1b6e` (`--no-open`), `a9a78db` (JSON only in the gate), `cf69fe4` (why not `--quiet`).
- `template/_CI/tasks/quality.py`.
