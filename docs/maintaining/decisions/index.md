# Decision records

One file per decision that shaped the template, with the situation it was made in, what was
decided, and what it costs. The explanation pages are the synthesis; these are the dated records
behind them. A docstring or a config comment states the current rule and, where the reason is
not obvious, names the record. The history stays here.

Records describe the template's evolution, so they do not ship into generated projects. The
rationale a project developer needs is in the six explanation pages that do ship, each of which
links back to the published records.

## Format

Each record is `NNNN-slug.md`, numbered in the order the decisions were made, with:

- a title line `# ADR-NNNN: <decision>`,
- `Status`, one of `accepted`, `superseded` (naming the successor), `deprecated`,
- `Date`, when the decision was made, and `Record written` when that differs,
- `## Context`, `## Decision`, `## Consequences`, and optionally `## References` to the commits
  and pages involved.

`tests/test_template_invariants.py` checks the numbering has no gaps, every record has that
shape, every record is in the nav and in the table below, and every `ADR-NNNN` mentioned
anywhere in the repository resolves to a file.

## Adding one

1. Take the next number and copy the shape above.
2. Add the page to `properdocs.yml` under *Maintaining the template → Decisions* and to the
   table below.
3. Name the record from the code or page whose behaviour it explains, as `ADR-NNNN`, so a reader
   who meets the rule finds the reason.
4. A decision that replaces an earlier one sets the old record to `superseded` and names the new
   one; the old record stays.

## Records

| Record | Decision |
| --- | --- |
| [ADR-0001](0001-copier-is-the-delivery-mechanism.md) | Copier is the delivery mechanism |
| [ADR-0002](0002-uv-is-the-only-tool-you-install.md) | uv is the only tool you install |
| [ADR-0003](0003-vendored-invoke-behind-one-launcher.md) | Vendored Invoke behind one launcher |
| [ADR-0004](0004-pipelines-run-template-commands-only.md) | Pipelines run template commands only |
| [ADR-0005](0005-dependency-groups-not-extras.md) | Dependency groups, not extras |
| [ADR-0006](0006-deliberate-non-goals.md) | Deliberate non-goals |
| [ADR-0007](0007-diataxis-with-shipped-rationale-pages.md) | Diátaxis for both sites, with the rationale pages shipped |
| [ADR-0008](0008-reproducibility-by-pin.md) | Reproducibility by pin |
| [ADR-0009](0009-one-qa-gate.md) | One QA gate |
| [ADR-0010](0010-verifying-is-the-default-writing-is-a-flag.md) | Verifying is the default, writing is a flag |
| [ADR-0011](0011-report-names-carry-a-scope.md) | Report names carry a scope |
| [ADR-0012](0012-the-sbom-ships-inside-the-wheel.md) | The SBOM ships inside the wheel |
| [ADR-0013](0013-the-audit-runs-on-a-schedule-and-the-dependency-surface.md) | The audit runs on a schedule and on the dependency surface |
| [ADR-0014](0014-a-release-is-the-version-bump-arriving-on-the-default-branch.md) | A release is the version bump arriving on the default branch |
| [ADR-0015](0015-local-py-is-the-projects-module.md) | `local.py` is the project's module |
