# Choose a git host (GitHub or GitLab)

The copier questionnaire asks `git_hosting_service` with two choices: `github` (default) or `gitlab`. The answer determines which CI scaffolding and host-specific code is generated; the other host's files are omitted automatically via conditional filenames.

## What changes per choice

| Artifact | `github` | `gitlab` |
| --- | --- | --- |
| `.github/workflows/*.yaml` | shipped | absent |
| `.gitlab-ci.yml` | absent | shipped |
| `_CI/tasks/github.py` (registry creds, docker publish, release-PR API) | shipped | absent |
| `_CI/tasks/gitlab.py` (registry creds, kaniko publish, release-MR API) | absent | shipped |
| Build badge in `README.md` | GitHub Actions | GitLab Pipelines |
| Container registry | `ghcr.io` (push via docker) | GitLab Container Registry (push via kaniko) |
| Release PR/MR | auto-opened via GitHub API when `GITHUB_TOKEN` is set | auto-opened via GitLab API when `GITLAB_TOKEN` is set |
| PyPI Trusted Publishing | `id-token: write` on the publish job; uv reads `ACTIONS_ID_TOKEN_*` | `id_tokens:` on the publish job (`PYPI_ID_TOKEN`, audience `pypi`); **gitlab.com only** — PyPI does not trust self-managed instances |
| PEP 740 attestations | `release.attest` signs with the job's OIDC identity | `release.attest` signs with `SIGSTORE_ID_TOKEN` (audience `sigstore`); gitlab.com only, for the same reason |
| GitHub build provenance (`gh attestation verify`) | yes, a second attestation stored with the repository | — |

Everything else — the package layout, `pyproject.toml`, dependency groups, `./workflow.cmd` tasks, tests, docs — is identical.

## Switching later

If you guessed wrong at generation time, the change is reversible via copier:

```bash
uvx copier update --trust
```

When prompted, change `git_hosting_service` to the other value. Copier performs a three-way merge against your project that:

- Adds the new host's CI config and `_CI/tasks/<host>.py` module.
- Removes the old host's CI config and module.
- Flips the import line in `_CI/tasks/container.py`, `release.py`, `document.py` and `sbom.py` from `.github` to `.gitlab` (or back).

Review the result carefully — if you've already customised the host-specific CI files, your changes will need manual reconciliation.

## GitLab specifics to be aware of

- **Releasing needs `GITLAB_TOKEN`.** `create_release_pr` opens the MR through the GitLab API using a personal, project, or group access token with the `api` scope. Without one it says so and `release` falls back to printing the manual `pr_create_url`, which is also what happens if the API call fails — a release never stops because the MR could not be opened.
- **Self-hosted instances work.** The instance host is read from your `origin` remote rather than assumed to be gitlab.com, for both the API call and the manual URL. Nested groups are handled too; the project path is URL-encoded as the API requires.
- The shipped `.gitlab-ci.yml` covers the `preflight` gate, the dependency audit and publish for `gitlab.com` runners; self-hosted runners with kaniko may need adjustments.
- **Trusted Publishing needs gitlab.com.** PyPI accepts OIDC tokens only from gitlab.com, so register the publisher there with the namespace, project, `.gitlab-ci.yml` and environment `pypi` ([PyPI's guide](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)). On a self-managed instance, set `UV_PUBLISH_URL`, `UV_PUBLISH_USERNAME` and `UV_PUBLISH_PASSWORD` as CI/CD variables instead: `release.publish` then uploads with them, without attestations, and `release.attest` signs nothing. A generated project's *Set up Trusted Publishing* how-to walks through both.

## See also

- [Copier questions](../reference/copier-questions.md#git_hosting_service) — the prompt's full reference entry.
- [Update an existing project with copier](update-existing-project-with-copier.md) — the mechanics of `copier update`.
