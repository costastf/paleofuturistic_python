# SBOM and security model

The template's security pipeline has three layers: known-vulnerability scanning, SBOM generation, and (optional) SBOM upload to an OWASP Dependency Track server. This page explains what each layer does and what threat model it addresses.

## The threat model

The template assumes:

- You publish a Python package consumed by people you mostly don't know.
- Your dependency graph is large and changes frequently.
- Some of your dependencies will, eventually, ship a vulnerability.
- Your downstream consumers will eventually ask "is your software affected by CVE-X?" — and they'll ask faster than you can audit by hand.

The pipeline answers those questions before the questions are asked.

## Layer 1 — pip-audit

`./workflow.cmd secure.audit` runs [pip-audit](https://github.com/pypa/pip-audit) against `uv.lock`, comparing every pinned package against the [PyPI advisory database](https://github.com/pypa/advisory-database).

What it catches: a vulnerability with a known CVE/PYSEC ID affecting a version in your lockfile.

What it doesn't catch:

- Zero-days (no advisory exists yet).
- Vulnerabilities in your *own* code.
- Misuse of a safe dependency.

Runs on every CI pipeline. See [Triage a security finding](../how-to/triage-a-security-finding.md) for the response workflow.

## Layer 2 — CycloneDX SBOM

`./workflow.cmd secure.sbom-extract --write` generates a [CycloneDX](https://cyclonedx.org/) 1.6 bill of materials and writes it to `src/<project_slug>/sbom.cdx.json`. Because that path is inside the package data tree, `uv build` automatically ships the SBOM **inside the wheel** — a downstream consumer unpacks the wheel and finds `<project_slug>/sbom.cdx.json` alongside the Python modules.

What an SBOM is: a machine-readable inventory of components. Each entry carries name, version, and a PURL identifier (PyPI for Python packages, `pkg:github/...` for GitHub Actions, `pkg:docker/...` for container images).

This template's SBOM has **three sources**, assembled into one document:

1. **Runtime dependencies.** Generated from `uv export --no-dev` against `uv.lock` — what actually lands in the wheel. Dev, lint, test, document, quality, and security groups are excluded; they aren't shipped.
2. **Vendored CI tooling.** Every package pinned in `_CI/lib/vendor.txt` (the vendored Invoke + its deps) is emitted as a PyPI component. These ship with the source tree even though they don't land in the wheel itself — they make the CI pipeline reproducible from a fresh clone.
3. **Pipeline components.** GitHub Actions (`uses:` refs across `.github/workflows/*.yaml`) on `github`, container images (`image:` and block-form `name:` refs in `.gitlab-ci.yml`) on `gitlab`. The host-specific code lives in `_CI/tasks/<host>.py` and is pulled in via the same Jinja-substituted import that `container.py` already uses.

`./workflow.cmd secure.sbom-validate` runs the CycloneDX 1.6 JSON-schema validator in a clean `uv run python` subprocess (so the venv-installed validator wins over the older vendored `jsonschema` that the workflow.cmd launcher places earlier on `sys.path`). The aggregate `./workflow.cmd secure` runs all three sub-steps; a clean run means: no known vulns, a fresh SBOM written, validated against the schema.

What this enables:

- A downstream consumer can extract the SBOM from the wheel with `unzip -p <wheel> <project_slug>/sbom.cdx.json` or `importlib.resources` — no separate artefact to track.
- A security responder can answer "are we affected by X?" against your project in seconds, not hours.
- Compliance frameworks (SLSA, NIST SSDF, EU CRA) that mandate SBOMs are satisfied — the SBOM travels with the artefact instead of needing to be re-correlated post-release.

The SBOM exists whether you have a Dependency Track server or not. It's part of every release.

## Layer 3 — Dependency Track (optional)

If `integrate_dependency_track` was enabled at generation time, `./workflow.cmd secure.sbom-upload` POSTs the SBOM to an OWASP Dependency Track instance.

What DT adds on top of layer 2:

- Continuous re-evaluation. DT re-checks your project against new CVEs every time the advisory database updates — without you re-running anything.
- Aggregation. One pane of glass across many projects in the same DT instance.
- Policy. You can set DT to fail builds based on policies (e.g. "no critical CVEs older than 30 days").
- Notification. DT can email/Slack on new findings against any tracked project.

Without DT, you only see what `pip-audit` reports at the moment you ran it. With DT, your release is *continuously* re-assessed against the world.

See [Upload an SBOM to Dependency Track](../how-to/upload-an-sbom-to-dependency-track.md) for setup.

## What about overrides?

`.security-overrides` is a project-local allow-list with mandatory expiry dates. It applies to `pip-audit`. It does **not** suppress findings in the SBOM or in Dependency Track — those continue to show the world the full truth. Override = "we accept this locally for now," not "make this invisible."

The expiry dates are load-bearing: a stale override is a security regression hidden in plain sight. The template's lint config doesn't enforce this; treat it as a code-review convention.

## What's deliberately out of scope

- **SAST**: Bandit / Semgrep / pyright security rules are not shipped. Add them as a `secure.*` task if you want them.
- **Container scanning**: Trivy / Grype are not shipped. The deps image built by `container.publish` is a dev convenience, not a published artifact, so we don't gate releases on it.
- **License compliance**: SBOM includes license metadata, but the template doesn't enforce license policies. DT does, if you turn it on there.

## See also

- [Triage a security finding](../how-to/triage-a-security-finding.md) — response playbook.
- [Upload an SBOM to Dependency Track](../how-to/upload-an-sbom-to-dependency-track.md) — wiring up layer 3.
