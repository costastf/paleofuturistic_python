# ADR-0066: GitHub pushes the deps image where a variable says, and pulls it anonymously

- **Status**: accepted; extends ADR-0065
- **Date**: 2026-11-27

## Context

ADR-0065 brought the base image inside the fence on both hosts and left one GitHub gap
open: the deps image itself was pushed to and pulled from `ghcr.io`, hardcoded in the GitHub
module and in every workflow's `container:` block, and the build job downloaded uv through
`setup-uv`. On github.com with hosted runners both are reachable and nothing was missing. On
self-hosted runners with no public egress, the full fence an organisation may run, every job
failed at the image pull.

Two facts shaped the design. The jobs that run inside the image pull it before any step
runs, so no OIDC exchange can happen first: the pull is either anonymous or made with a stored
secret. And the Actions runner skips the registry login when either credential it is given is
empty, so a workflow can blank them by expression without a second copy of every job.

## Decision

A `DEPS_IMAGE_REGISTRY` organisation variable, `host/repository` of a docker repository in
Artifactory, moves the image. Unset, nothing changes.

- The build job pushes under it by repository name, logged in with the index identity when
  its host is the index host or a subdomain, the same rule as the base image. A registry on
  any other host gets no credentials, and the push says it goes anonymously.
- The jobs that run in the image pull it anonymously. Every `container:` block's credentials
  are the workflow token when the variable is unset and empty when it is set, which the
  runner reads as no login. The repository therefore allows anonymous reads from inside the
  network, which is the organisation's choice over a stored pull secret; the alternative,
  running fenced jobs on the runner without the image, would have kept the no-secret rule and
  given up the warm image and the audit.
- `container.audit` reads such an image back anonymously too, as the jobs do.
- `setup-uv`, which only the build job runs, takes a `UV_MANIFEST_FILE` variable as its
  manifest, in the `astral-sh/versions` format, pointing at copies of the releases on the
  organisation's generic remote. Empty means the action's default, Astral's mirror at
  `releases.astral.sh`. The action treats an empty input as absent.

The actions themselves and the OIDC token endpoint stay on github.com. A self-hosted runner
reaches both by definition, so they are allowances the organisation already has, not template
work.

## Consequences

- GitHub and GitLab are symmetric behind a full fence: one identity for the index, the
  interpreters, the base image and the deps image, and the audit still reads the pushed image
  back on both.
- A pull with empty credentials from `ghcr.io` would also work for a public image, but the
  expression keeps the token there, so a private project in the open is unchanged.
- The deps image's `packages: read` permission is meaningless against Artifactory and
  harmless; the jobs keep it for the open case.
- The manifest is one more thing the organisation hosts and keeps current, which is the price
  of a build runner that cannot reach Astral. A build job inside the deps image would avoid
  it, and would move the image build into an image that does not exist yet.
- Invariants hold every `container:` block to the blanking expression, the build workflow to
  handing the variable down and the manifest to the action, the module to pushing under the
  variable with the index identity and reading it back anonymously, and a registry off the
  index host to receiving no credentials.

## References

- [ADR-0065](0065-the-deps-build-pulls-a-fenced-base-image-with-the-index-identity.md), the
  host rule this reuses.
- [ADR-0041](0041-fork-pull-requests-run-the-gate-on-the-runners-image.md), the path a
  fenced project does not take, since it takes no pull requests from forks.
- [ADR-0050](0050-the-deps-image-is-built-every-run-unless-asked-to-reuse.md), whose trust
  argument applies to the Artifactory repository as it did to the ghcr package.
