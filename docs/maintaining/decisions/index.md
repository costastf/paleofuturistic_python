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
| [ADR-0016](0016-ruff-replaces-black-isort-and-flake8.md) | Ruff replaces Black, isort and flake8; pylint stays for what Ruff lacks |
| [ADR-0017](0017-ty-replaces-mypy.md) | ty replaces mypy |
| [ADR-0018](0018-pytest-replaces-unittest.md) | pytest replaces unittest, with xdist at a fixed worker count |
| [ADR-0019](0019-conventional-commits-drive-the-changelog.md) | Conventional Commits drive the changelog, not the version |
| [ADR-0020](0020-properdocs-with-mkdocstrings.md) | properdocs with mkdocstrings |
| [ADR-0021](0021-trusted-publishing-with-attestations.md) | Trusted Publishing with PEP 740 attestations by default |
| [ADR-0022](0022-one-commit-stage-hook-and-no-filter-on-pre-push.md) | One commit-stage hook, and no `files:` filter on pre-push |
| [ADR-0023](0023-staged-paths-with-shell-characters-are-refused.md) | Staged paths with spaces or shell characters are refused |
| [ADR-0024](0024-commit-messages-are-checked-over-the-unpushed-range.md) | Commit messages are checked over the unpushed range only |
| [ADR-0025](0025-coverage-is-a-union-and-the-ratchet-starts-dormant.md) | Coverage is a union, `fail_under` is enforced once, and the ratchet starts dormant |
| [ADR-0026](0026-pyscn-json-in-the-gate-html-on-demand.md) | pyscn produces JSON in the gate and HTML on demand |
| [ADR-0027](0027-heavy-imports-stay-out-of-launcher-startup.md) | Heavy imports stay out of launcher startup |
| [ADR-0028](0028-the-audit-reads-the-lockfile-and-retries-without-a-verdict.md) | The audit reads `uv.lock` directly and retries a run with no verdict |
| [ADR-0029](0029-suppressions-from-three-sources-two-of-them-must-expire.md) | Suppressions come from three sources, and the two outside the repository must expire |
| [ADR-0030](0030-task-commits-follow-the-signing-configuration.md) | Task commits follow the signing configuration |
| [ADR-0031](0031-the-changelog-is-the-page-the-nav-shows.md) | The changelog lives at `docs/reference/changelog.md` |
| [ADR-0032](0032-dependency-track-upload-removed.md) | Dependency-Track upload removed |
| [ADR-0033](0033-the-deps-image-is-content-addressed-and-handed-on-by-digest.md) | The deps image is content-addressed and handed on by digest |
| [ADR-0034](0034-the-deps-image-runs-as-uid-1001.md) | The deps image runs as uid 1001 |
| [ADR-0035](0035-github-reuses-a-deps-tag-gitlab-builds-with-kaniko.md) | GitHub reuses an existing deps tag; GitLab's pipeline job builds with kaniko |
| [ADR-0036](0036-checkouts-persist-no-credentials.md) | Checkouts persist no credentials |
| [ADR-0037](0037-docs-deploy-on-release-through-gh-deploy.md) | Docs deploy on release through `gh-deploy` |
| [ADR-0038](0038-template-tests-snapshot-pin-and-mature.md) | Template tests generate from a snapshot, pin the uv version, and run one matured cell |
| [ADR-0039](0039-repository-url-renders-well-known-project-urls-or-nothing.md) | `repository_url` renders well-known `[project.urls]`, or nothing |
| [ADR-0040](0040-the-default-branch-is-a-copier-answer.md) | The default branch is a copier answer |
| [ADR-0041](0041-fork-pull-requests-run-the-gate-on-the-runners-image.md) | Fork pull requests run the gate on the runner's image |
| [ADR-0042](0042-refresh-deps-moves-the-boundary-and-the-pins-together.md) | `develop.refresh-deps` moves the boundary and the pins together |
| [ADR-0043](0043-the-gitlab-deps-tag-is-computed-by-the-launcher.md) | The GitLab deps tag is computed by the launcher |
