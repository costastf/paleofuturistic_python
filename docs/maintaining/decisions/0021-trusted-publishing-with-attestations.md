# ADR-0021: Trusted Publishing with PEP 740 attestations by default

- **Status**: accepted
- **Date**: 2026-11-10
- **Record written**: 2026-11-11 (backfilled)

## Context

Publishing with a long-lived PyPI API token stored as a CI secret means a leaked secret can
publish anything, and a wheel on PyPI says nothing about which pipeline built it. PyPI accepts
[PEP 740](https://packaging.python.org/en/latest/specifications/index-hosted-attestations/)
attestations only from a Trusted Publisher, so provenance and the credential model are one
decision.

## Decision

The publish job authenticates to PyPI with the host's OIDC token: `id-token: write` on GitHub,
`id_tokens:` with audiences `pypi` and `sigstore` on GitLab. `release.attest` signs an
attestation per wheel and sdist with that identity, `uv publish --trusted-publishing always`
uploads the files with their attestations, and on GitHub `actions/attest-build-provenance`
records a second attestation with the repository. The `pypi` environment is restricted to the
default branch, not to reviewers.

`UV_PUBLISH_*` credentials switch the whole path: when all three are set the upload uses them
with `--no-attestations` and `release.attest` signs nothing, because an index without Trusted
Publishing may reject an upload that carries attestations. Empty values are dropped first,
since GitHub injects an undefined secret as an empty string and uv reads an empty
`UV_PUBLISH_URL` as a URL.

## Consequences

- No PyPI secret exists anywhere; PyPI's Trusted Publisher form is a one-time setup per project.
- On GitLab, Trusted Publishing works from gitlab.com only; a self-managed instance uses the
  credential path.
- Nothing rebuilds between attesting and uploading (ADR-0014), or the attestation would name
  files that were never published.

## References

- Commit `b1a48da`, "cover every PyPA packaging specification".
- [SBOM and security model: Layer 3](../../using/explanation/sbom-and-security-model.md#layer-3-build-provenance),
  [Harden the GitHub repository](../../using/how-to/harden-github-repository.md).
