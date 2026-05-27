# Harden the GitHub repository

After generating with `git_hosting_service=github`, you have three workflow files under `.github/workflows/` and a release pipeline that wants to publish to PyPI. This page lists the GitHub-side settings worth applying before that pipeline ever fires.

## Prerequisite security

These are non-negotiable for any repository connected to CI/CD:

- **Branch protection on `main`.** Require pull requests, require status checks, require a linear history. Block force pushes and deletions.
- **Tag protection for `v*`.** Forbid deleting and editing release tags.
- **Required approvals.** At least one reviewer per PR.

## PyPI trusted publishing

The shipped `.github/workflows/publish.yaml` is configured for [PyPI trusted publishing](https://docs.pypi.org/trusted-publishers/) — short-lived OIDC tokens, no long-lived secrets.

1. Create a `pypi` environment on the repo: **Settings → Environments → New environment**.
2. Restrict deployment branches: only `main` may deploy to `pypi`.
3. On [pypi.org](https://pypi.org/), add a [trusted publisher](https://docs.pypi.org/trusted-publishers/adding-a-publisher/) pointing at your repo + workflow + environment name (`pypi`).

The workflow grants `id-token: write` on the publish job — that's what makes the OIDC handshake possible. Don't ship a `PYPI_API_TOKEN` secret alongside; the workflow drops empty `UV_PUBLISH_*` env vars so OIDC remains the only path.

## Hardening against external contributors

- Set **Settings → Actions → Fork pull request workflows → Require approval for all external contributors**.
- Enable **Settings → Code review limits → Limit to users explicitly granted read or higher access**.
- Consider **Temporary interaction limits** if the repo gets brigaded.

## Hardening against insider mistakes

- Add **Required reviewers** under **Settings → Environments → pypi → Deployment protection rules**. Even a self-merge can't publish unless a designated reviewer approves the deployment.
- Avoid personal-account ownership of org repos. Org/repo admin access should require 4-eyes approval for assumption.
- Enable Dependabot alerts and secret scanning (free for public repos).

## Verify the workflows still pass

After applying ruleset changes, push an empty commit and watch the Quality Assurance workflow run end-to-end. Anything blocked by your new rules will surface in the Actions tab.

## See also

- [GitHub's repository security hardening guide](https://docs.github.com/en/code-security/getting-started/securing-your-repository) — official reference.
- [Choose a git host](choose-a-git-host.md) — if you're considering GitLab instead.
