# SBOM and security model

The template's security pipeline has three layers: known-vulnerability scanning, SBOM generation, and (optional) SBOM upload to an OWASP Dependency Track server. This page explains what each layer does and what threat model it addresses.

## The threat model

The template assumes a generated project:

- Publishes a Python package consumed by people its maintainers mostly don't know.
- Has a dependency graph that's large and changes frequently.
- Will, eventually, have one of its dependencies ship a vulnerability.
- Will eventually get asked by a downstream consumer "is your software affected by CVE-X?" — faster than anyone could audit by hand.

The pipeline answers those questions before the questions are asked.

## Layer 1 — pip-audit

`./workflow.cmd secure.audit` runs [pip-audit](https://github.com/pypa/pip-audit) over the two requirement sets a generated project pins — `uv.lock`, exported with every dependency group, and `_CI/lib/vendor.txt` — comparing each pinned package against the [PyPI advisory database](https://github.com/pypa/advisory-database).

Requirement files rather than the installed environment, which is what `pip-audit` reads by default. An installed-distribution scan sees whatever the current interpreter and platform happen to have synced: it silently omits a package gated behind a platform marker, an extra, or a group that was not installed — all of it pinned in the lockfile and listed in the SBOM — while including packages that are not dependencies at all. The vendored CI tree needs naming for a different reason: it ships as committed source with no `.dist-info`, so nothing that enumerates installed distributions can see it, and it is code `./workflow.cmd` executes in every job.

What it catches: a vulnerability with a known CVE/PYSEC ID affecting a version in either file.

What it doesn't catch:

- Zero-days (no advisory exists yet).
- Vulnerabilities in the project's *own* code.
- Misuse of a safe dependency.

**When it runs, and why not on every push.** The audit's answer depends on the advisory
database at the moment it runs rather than on your branch, so a pull request touching a
docstring can go red for a CVE published overnight that its author neither introduced nor can
fix — and a pipeline failing for reasons outside the author's control is one people learn to
ignore. It is triggered on the axes it varies along instead:

- **On a schedule** (daily), which is what makes the expiry dates in `.security-overrides`
  load-bearing — a dependency can turn out to be vulnerable, and an override can come due,
  without anyone pushing anything.
- **On pushes that change the dependency surface** — `uv.lock`, `_CI/lib/vendor.txt`, the
  vendored tree and its patches, and `.security-overrides`. Change what you depend on and you
  own the result. A release lands here too: `version_provider = "uv"` re-locks, so the bump
  commit carries `uv.lock`, and the commit that publishes is worth auditing anyway.
- **A hand-edited vendored file is watched, not audited.** A push touching `_CI/lib/vendor/`
  fires the job so the diff reaches a human. No scanner can say anything about a patched
  vendored source: `vendor.txt` is what pip-audit reads, and it describes the packages that
  *should* be there.
- **Before publishing.** `release.dist` audits before it builds. That is the moment the outside
  world is exposed to these dependencies, and the one place where refusing to proceed protects
  somebody.

It is deliberately *not* part of `build`. The SBOM is (see Layer 2 — `uv build` ships it inside
the wheel); the audit is not, because coupling them would mean a newly published CVE making it
impossible to build a wheel from code that built yesterday. `./workflow.cmd preflight
--audit-dependencies` runs it locally alongside everything else.

## Layer 2 — CycloneDX SBOM

`./workflow.cmd secure.sbom-extract --write` generates a [CycloneDX](https://cyclonedx.org/) 1.7 bill of materials and writes it to `src/<your_package>/sbom.cdx.json`. Because that path is inside the package data tree, `uv build` automatically ships the SBOM **inside the wheel** — a downstream consumer unpacks the wheel and finds `<your_package>/sbom.cdx.json` alongside the Python modules.

### What's in it

**Metadata header** declares:

- A `lifecycles` entry of `phase: build` — this SBOM was produced during the build, not as a post-shipment inventory.
- A `tools.components` list naming what produced the SBOM (cyclonedx-python-lib, uv, the project's own generator), each with a version pin.
- `supplier` + `authors` derived from `pyproject.toml`'s `[project.authors]`.
- A `properties` entry recording the chosen `git_hosting_service` answer for downstream tools that want template-aware context.

**Components** are organised by **scope** so a consumer can distinguish what ships from what doesn't:

| Source | CycloneDX `scope` | Source path |
| --- | --- | --- |
| Project itself (root) | `required` | `[project]` block in pyproject.toml; root carries the project's licence and a `vcs` external_reference pointing at the git remote when present |
| Runtime dependencies | `required` | `uv export --no-dev` against `uv.lock` — exactly what ships in the wheel |
| Dev / lint / test / docs / quality / security groups | `optional` | full lockfile via `uv export --all-groups`, minus the runtime set |
| Vendored CI tooling | `excluded` | every package in `_CI/lib/vendor.txt` |
| Pipeline components | `excluded` | GitHub Actions (`uses:`) or GitLab CI images, sourced from `_CI/tasks/<host>.py`'s `iter_pipeline_components()` |

Plus one **synthetic build-environment component** (type `platform`, scope `excluded`) that groups the vendored + pipeline material into a single sub-graph.

**Dependencies** form a two-level graph:

- The project root depends on each runtime + dev component and on the build-environment.
- The build-environment depends on the vendored + pipeline components.

Reading top-down: "the project depends on these runtime + dev components for itself, and on the build-environment to be assembled. The build-environment in turn depends on these vendored + pipeline components."

### Per-component enrichment

Each PyPI component (runtime, dev, vendored) carries:

- **`licenses`** — declared SPDX expression. The lookup walks `PEP 639 License-Expression → legacy License header → LICENSE-File text → Trove classifier mapping`. Vendored entries first try text-detection over the `_CI/lib/vendor/<name>/LICENSE*` files (the vendoring tool drops dist-info but keeps the LICENSE), then defer to the venv-installed copy when the same package is also a transitive dev dep. A handful of packages with no licence-bearing file locally end up with `licenses: []` — graceful degradation rather than failure.
- **`hashes`** — SHA-256 from `uv.lock`'s `wheels[*].hash` (or `sdist.hash` fallback). Pipeline and vendored components carry no hash here — the GitHub-Action PURL already encodes the commit SHA, and vendored entries aren't in the lockfile.
- **`external_references`** — every PyPI component points at its PyPI project page (`type=website`); GitHub Actions point at their repo (`type=vcs`); GitLab images point at their registry (`type=distribution`).

### Validation

`./workflow.cmd secure.sbom-validate` runs the CycloneDX 1.7 JSON-schema validator in a clean `uv run python` subprocess (so the venv-installed validator wins over the older vendored `jsonschema` that the workflow.cmd launcher places earlier on `sys.path`). The aggregate `./workflow.cmd secure` runs all three sub-steps; a clean run means: no known vulns, a fresh SBOM written, validated against the schema.

### What this enables

- A downstream consumer can extract the SBOM from the wheel with `unzip -p <wheel> <your_package>/sbom.cdx.json` or `importlib.resources` — no separate artefact to track.
- A security responder can answer "are we affected by X?" against a project built from this template in seconds, not hours.
- Compliance frameworks (SLSA, NIST SSDF, EU CRA) that mandate SBOMs are satisfied — the SBOM travels with the artefact instead of needing to be re-correlated post-release.

The SBOM exists whether a project has a Dependency Track server or not. It's part of every release.

## Layer 3 — Dependency Track (optional)

If `integrate_dependency_track` was enabled at generation time, `./workflow.cmd secure.sbom-upload` uploads the SBOM straight to Dependency Track's `/api/v1/bom` REST endpoint, using nothing beyond the Python standard library's `urllib` — no extra dependency is pulled in just to make that one HTTP call.

What DT adds on top of layer 2:

- Continuous re-evaluation. DT re-checks the project against new CVEs every time the advisory database updates — without anyone re-running anything.
- Aggregation. One pane of glass across many projects in the same DT instance.
- Policy. DT can be set to fail builds based on policies (e.g. "no critical CVEs older than 30 days").
- Notification. DT can email/Slack on new findings against any tracked project.

Without DT, only what `pip-audit` reported at the moment it ran is visible. With DT, every release is *continuously* re-assessed against the world.

See [Enable Dependency Track integration](../how-to/enable-dependency-track.md) for setup.

## Layer 4 — build provenance

The SBOM says what is *inside* an artifact. Provenance says where the artifact *came from* — and unlike the SBOM, it is not self-reported. `actions/attest-build-provenance` signs a statement binding the exact file digests to the workflow, commit and runner that produced them, and that signature chains to GitHub's Sigstore instance rather than to anything the project controls. A forged SBOM is a text edit; a forged attestation is not.

A consumer verifies a downloaded artifact with:

```bash
gh attestation verify <package>-<version>-py3-none-any.whl --repo <owner>/<repo>
```

Order matters in the publish job: `release.dist` builds into `dist/`, the attestation is taken over those files, and `release.publish --prebuilt` uploads them *without* rebuilding. Rebuilding in between would publish files that no attestation refers to, and verification would then fail — reading as tampering rather than as a fresh build.

**GitHub only.** GitLab has no equivalent that works without extra infrastructure, so GitLab projects ship the SBOM without provenance. Nothing else about the release differs.

## What about overrides?

`.security-overrides` is a project-local allow-list with mandatory expiry dates. It applies to `pip-audit`. It does **not** suppress findings in the SBOM or in Dependency Track — those continue to show the world the full truth. Override = "we accept this locally for now," not "make this invisible."

The expiry dates are load-bearing: a stale override is a security regression hidden in plain sight. The template's lint config doesn't enforce this; treat it as a code-review convention.

## What's deliberately out of scope

- **SAST**: Bandit / Semgrep / pyright security rules are not shipped. Add them as a `secure.*` task if needed.
- **Container scanning**: Trivy / Grype are not shipped. The deps image built by `container.publish` is a dev convenience, not a published artifact, so releases aren't gated on it.
- **License compliance**: SBOM includes license metadata, but the template doesn't enforce license policies. DT does, if turned on.

## See also

- [Enable Dependency Track integration](../how-to/enable-dependency-track.md) — wiring up layer 3.
