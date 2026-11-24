# ADR-0064: Every job that fetches logs in to the index

- **Status**: accepted; extends ADR-0063
- **Date**: 2026-11-24

## Context

ADR-0063 handed the fence's credentials to the deps-image build and to the upload, on the
reading that the other jobs run inside the synced image and fetch nothing. That reading was
wrong. `preflight` runs the tox matrix, which creates an environment per interpreter beyond
the one the image carries and installs each from the index, and uv fetches the interpreters
themselves. `publish` runs `uv build`, which fetches the build backend. The plan job installs
uv with pip. Behind a fence, each of these fails on its first request.

The credentials were also GitLab-only: the exchange took the ID token from a variable the
`id_tokens:` block minted, and GitHub had two secrets instead.

## Decision

One task, `index.login`, writes a netrc entry for the index host from the credentials
`index_login` finds, so uv, tox-uv and pip, which all read the netrc, authenticate for the
rest of the job. `preflight`, `secure` and `publish` run it first, on both hosts. It prints
where it logged in and never what with, and with no fence configured it says so and writes
nothing.

On GitLab the ID token moves from two jobs to the pipeline's `default:` block, so every job
holds one; `publish` keeps its own list and repeats it, a job's `id_tokens:` replacing the
default's. On GitHub the exchange mints the ID token itself, from the Actions endpoint a job
with `id-token: write` is handed, for the audience in `JFROG_AUDIENCE`; every workflow hands
the five fence variables down as environment, and every job that fetches may write a token,
callers of the reusable build workflow included. The provider name defaults to the host that
minted the token, which is how an organisation most likely named it in Artifactory.

Two of uv's and pip's own knobs join the how-to rather than the code: `PIP_INDEX_URL` for the
plan job's one pip call, and `UV_PYTHON_INSTALL_MIRROR` for the interpreters.

Four things stay outside the fence and are stated as such: the advisory database pip-audit
asks, which nothing proxies; the docs inventories `document.build` fetches; the base image
from ghcr, which a Docker remote serves under another name the project edits in; and the
render hook's uv lookup, which already falls back to the committed pin.

## Consequences

- A netrc with a token exists in three jobs for their duration, readable by its owner only,
  in a container that ends with the job.
- GitHub needs `id-token: write` on four jobs that did not have it. A pull request from a
  fork gets no token and no variables, runs in the open, and fails on the first fetch; a
  fenced project does not take pull requests from forks.
- The GitHub secrets path for the image build stays, as a project's choice over mapping an
  OIDC identity, and wins over the exchange when set.
- Invariants hold the three jobs to logging in before anything that fetches, the GitLab
  default to minting the token, the GitHub workflows to the permission and the variables,
  the login to a private netrc that replaces a stale entry, and the GitHub exchange to the
  Actions endpoint and the audience.

## References

- [ADR-0063](0063-a-fenced-index-is-a-set-of-group-variables.md), which this corrects.
- [ADR-0062](0062-the-deps-image-is-built-in-stages-and-read-back.md), the image the
  credentials still build.
