# Harden the GitHub repository

After generating with `git_hosting_service=github`, you have six workflow files under `.github/workflows/` (five without Pages) and a release pipeline that wants to publish to PyPI. This page lists the GitHub-side settings worth applying before that pipeline ever fires.

## Prerequisite security

These are non-negotiable for any repository connected to CI/CD:

- **Branch protection on `main`.** Require pull requests, require status checks, require a linear history. Block force pushes and deletions. Require only checks that run on every pull request — and today that is none of the shipped ones. **Do not require `Preflight`**: the workflows trigger on `push`, so a pull request from a fork runs nothing in this repository and a required check would sit pending forever, leaving the repository unable to merge an external contribution. `security-audit` is filtered by `on.push.paths` on top of that. Require them once the workflows gain a `pull_request` trigger, which is a decision the template has not taken yet.
- **Tag protection for `v*`.** Forbid deleting and editing release tags.
- **Required approvals.** At least one reviewer per PR.

## PyPI trusted publishing

The shipped `.github/workflows/publish.yaml` is configured for [PyPI trusted publishing](https://docs.pypi.org/trusted-publishers/) — short-lived OIDC tokens, no long-lived secrets.

1. Create a `pypi` environment on the repo: **Settings → Environments → New environment**.
2. Restrict deployment branches: only `main` may deploy to `pypi`.
3. On [pypi.org](https://pypi.org/), add a [trusted publisher](https://docs.pypi.org/trusted-publishers/adding-a-publisher/) pointing at your repo + workflow + environment name (`pypi`).

The workflow grants `id-token: write` on the publish job — that's what makes the OIDC handshake possible. Don't set `UV_PUBLISH_*` secrets alongside: when all three are present `release.publish` uploads with them instead, and without attestations.

The same OIDC identity signs two attestations over the wheel and sdist before they are uploaded. `actions/attest-build-provenance` records GitHub's own (needs `attestations: write`, already granted), verified with `gh attestation verify`. `release.attest` signs a [PEP 740](https://packaging.python.org/en/latest/specifications/index-hosted-attestations/) attestation per file that `uv publish` uploads to PyPI, where it shows as *Provenance* on each file and is verified with `pypi-attestations verify pypi`. PyPI takes the second kind only through Trusted Publishing, which is one more reason to keep the credential path unused. See [SBOM and security model](../explanation/sbom-and-security-model.md#layer-3-build-provenance).

## Hardening against external contributors

- Set **Settings → Actions → Fork pull request workflows → Require approval for all external contributors**.
- Enable **Settings → Code review limits → Limit to users explicitly granted read or higher access**.
- Consider **Temporary interaction limits** if the repo gets brigaded.

## Hardening against insider mistakes

- Add **Required reviewers** under **Settings → Environments → pypi → Deployment protection rules**. Even a self-merge can't publish unless a designated reviewer approves the deployment.
- Avoid personal-account ownership of org repos. Assuming org/repo admin access should require four-eyes approval.
- Enable Dependabot alerts and secret scanning (free for public repos).

## Verify the workflows still pass

After applying ruleset changes, push an empty commit and watch the Continuous Integration workflow run end-to-end. Anything blocked by your new rules will surface in the Actions tab.

## See also

- [GitHub's repository security hardening guide](https://docs.github.com/en/code-security/getting-started/securing-your-repository) — official reference.
- [Choose a git host](choose-a-git-host.md) — if you're considering GitLab instead.
