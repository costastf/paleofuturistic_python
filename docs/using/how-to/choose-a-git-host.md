# Choose a git host (GitHub or GitLab)

The copier questionnaire asks `git_hosting_service` with two choices: `github` (default) or `gitlab`. The answer determines which CI scaffolding and host-specific code is generated; the other host's files are omitted automatically via conditional filenames.

## What changes per choice

| Artifact | `github` | `gitlab` |
| --- | --- | --- |
| `.github/workflows/*.yaml` | shipped | absent |
| `.gitlab-ci.yml` | absent | shipped |
| `_CI/tasks/github.py` (registry creds, docker publish, release-PR API) | shipped | absent |
| `_CI/tasks/gitlab.py` (registry creds, kaniko publish, manual MR URL) | absent | shipped |
| Build badge in `README.md` | GitHub Actions | GitLab Pipelines |
| Container registry | `ghcr.io` (push via docker) | GitLab Container Registry (push via kaniko) |
| Release PR/MR | auto-opened via GitHub API when `GITHUB_TOKEN` is set | manual URL printed; API stub waiting to be implemented |

Everything else — the package layout, `pyproject.toml`, dependency groups, `./workflow.cmd` tasks, tests, docs — is identical.

## Switching later

If you guessed wrong at generation time, the change is reversible via copier:

```bash
uvx copier update --trust
```

When prompted, change `git_hosting_service` to the other value. Copier performs a three-way merge against your project that:

- Adds the new host's CI config + submodule.
- Removes the old host's CI config + submodule.
- Flips the import line in `_CI/tasks/container.py` (and `release.py`) from `.github` to `.gitlab` (or back).

Review the result carefully — if you've already customised the host-specific CI files, your changes will need manual reconciliation.

## GitLab limitations to be aware of

The GitLab path currently has two stubs:

- **`create_release_pr`** in `_CI/tasks/gitlab.py` prints a message and returns `''` — auto-opening MRs via the GitLab API is not implemented. The `release` task falls back to printing the manual `pr_create_url`.
- The shipped `.gitlab-ci.yml` covers lint/test/build/publish for `gitlab.com` runners; self-hosted runners with kaniko may need adjustments.

PRs implementing the GitLab MR auto-creation are welcome — the seam exists exactly so contributors don't have to touch `release.py`.

## See also

- [Copier questions](../reference/copier-questions.md#git_hosting_service) — the prompt's full reference entry.
- [Update an existing project with copier](update-existing-project-with-copier.md) — the mechanics of `copier update`.
