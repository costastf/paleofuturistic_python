# ADR-0062: The deps image is built in stages and read back before it is trusted

- **Status**: accepted
- **Date**: 2026-11-18

## Context

A project behind a fenced index has to hand its index credentials to the `uv sync` inside
`Dockerfile.deps`. On GitLab the image is built by kaniko, which has no secret mounts, so the
only way in is a build argument. A build argument is recorded in the history of every layer
of the stage that declares it, as `|1 NAME=value /bin/sh -c …`, and with the single-stage
Dockerfile the template shipped, that history is the pushed image's. Anyone who can pull the
image could read the token.

This came up while designing the fenced-index support the template does not have yet. The
image build is the one place that support needs a secret inside a build, so it was settled
first, and in a way that holds before any pipeline passes a credential.

## Decision

`Dockerfile.deps` has three stages. `base` installs git and copies the two project files;
`builder` declares `INDEX_URL`, `INDEX_USERNAME` and `INDEX_PASSWORD`, writes a netrc for
the one `uv sync`, and removes it in the same layer; the final stage starts from `base`
again and copies `/app/.venv` out of the builder. The pushed image's history holds the final
stage's instructions and a `COPY` with no values in it. Nothing becomes an `ENV`, and the
netrc never outlives its `RUN`, so no layer that reaches a registry holds the credentials
either, kaniko's layer cache included. With the arguments empty, which is every project
today, the build produces what it did before.

`container.audit` reads the image back and refuses it on any trace: a history line or an
environment entry naming one of the three arguments, the sync command, or `netrc`. The sync
command is in the list because its presence in the final image is the surest sign the stage
boundary was lost, whatever the arguments were. The task reads through the container engine
when one holds the image, and through the registry API otherwise, with a standard-library
client that mints a bearer token from the first 401. GitHub runs it in the build job right
after the push; GitLab's kaniko job cannot, so `preflight` runs it first, inside the image.

The parent's matured cell builds the generated image and audits it, which proves the stage
boundary on every push to the template, with no secret in play.

## Consequences

- One Dockerfile for the open internet and the fenced company, with three empty arguments
  in the open. The pipeline wiring that fills them, and the token exchange that produces
  them, are the next decisions; neither can leak through the build any more.
- The final image no longer carries uv's download cache, which the single stage left under
  root's home: it is smaller by that much.
- A new module, `_CI/tasks/registry.py`, is the second registry reader beside the digest
  lookup in `uv_release.py`. They stay apart: one is stdlib-only for the render hook and
  talks to ghcr about uv's own image, the other to the project's registry about the project's.
- The matured cell needs a container engine on the machine that runs it, which the
  template's own matrix has, and the testing how-to says so.
- Invariants hold the arguments to the builder stage, the markers to the arguments, and the
  audit to both pipelines.

## References

- [ADR-0033](0033-the-deps-image-is-content-addressed-and-handed-on-by-digest.md), which
  this Dockerfile is an input to.
- [ADR-0034](0034-the-deps-image-runs-as-uid-1001.md), whose user and ownership lines moved
  to the final stage unchanged.
- [ADR-0050](0050-the-deps-image-is-built-every-run-unless-asked-to-reuse.md), the build
  every push performs.
