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

`./workflow.cmd secure.sbom-extract --write` generates a [CycloneDX](https://cyclonedx.org/) bill of materials describing every dependency, transitive included. It ships in `dist/sbom.json` alongside the wheel on every release.

What an SBOM is: a machine-readable inventory of components. Each entry has a name, version, license, and (where available) PURL plus SHA-256 hashes.

What it enables:

- A downstream consumer can search your SBOMs for any component without reading your source.
- A security responder can answer "are we affected by X?" against your project in seconds, not hours.
- Compliance frameworks (SLSA, NIST SSDF) that mandate SBOMs are satisfied.

The SBOM exists whether you have a Dependency Track server or not. It's a release artifact.

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
