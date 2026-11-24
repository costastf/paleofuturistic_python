# ADR-0063: A fenced index is a set of group variables

- **Status**: accepted
- **Date**: 2026-11-18

## Context

The template serves two worlds from one file: development in the open, resolving from PyPI
and publishing to it through Trusted Publishing, and development inside a company, where
every package comes from and goes to an Artifactory behind a fence, with OIDC in place of
stored tokens. The company's platform team ships a GitLab snippet for the token exchange,
`.jfrog_token`, that mints an ID token for an audience of their choosing and trades it at
`/access/api/v1/oidc/token` for a token scoped to a project, using `curl` and `jq`.

A copier question per fence, or an `include:` of that snippet, would put the company's
choices into the generated pipeline of every project and a branch into the template for each.
Neither world should know about the other.

## Decision

Every difference between the two worlds is a variable the organisation sets once, at group
level, and the generated project is byte-for-byte the same in both.

- `UV_DEFAULT_INDEX` and `UV_PUBLISH_URL` are uv's own, and the lock generation writes
  records whichever index was set.
- `JFROG_URL`, `JFROG_PROJECT`, `JFROG_AUDIENCE` and `JFROG_PROVIDER` drive the token
  exchange, which the template does itself in `_CI/tasks/index.py` with the standard library:
  the same request the platform team's snippet sends, from Python, because neither
  `python:3-slim` nor the deps image has `curl` or `jq`, and the snippet's job would not run
  in them.
- `INDEX_URL`, `INDEX_USERNAME` and `INDEX_PASSWORD`, when already set, win over an exchange:
  that is a developer's own identity token, the kaniko job reading the plan job's dotenv, or a
  GitHub repository's secrets.

The ID token is minted on every run of the two jobs that need it, `plan-deps-image` and
`publish`, for the audience in `JFROG_AUDIENCE`. GitLab refuses an empty audience, so the
pipeline file carries a placeholder, `not-configured`, as a global variable; a group variable
of the same name overrides it, variables set in the pipeline file ranking below group ones in
GitLab's precedence. A token nobody consumes is minted in the open and expires with the job.

`plan-deps-image` exchanges its token and writes the three `INDEX_*` values into the dotenv
it already hands the kaniko job, which passes them as build arguments; the artifact expires in
an hour. `publish` exchanges again, since the plan job's token may have expired, and fills
`UV_PUBLISH_USERNAME` and `UV_PUBLISH_PASSWORD` beside the `UV_PUBLISH_URL` the group set,
inside `publishes_with_credentials`, so the existing credentials path takes over. Every
builder of the image, by hand or in a job with an engine, goes through one
`deps_build_command`, which names the credentials on the command line as `"$INDEX_PASSWORD"`
and supplies them through the environment, so the command a task echoes shows no secret.

On GitHub the build job forwards a repository variable and two secrets as the same three
`INDEX_*` names; an OIDC exchange from GitHub is not wired.

## Consequences

- No copier question and no Jinja branch. The company sets six group variables; a project in
  the open sets nothing and inherits a placeholder audience it never uses.
- The credentials exist in two jobs for minutes, in a dotenv the build job reads at once, and
  reach the builder stage of a Dockerfile whose final image `container.audit` reads back
  (ADR-0062).
- The template owns a twenty-line copy of the platform team's exchange, with their two fields
  in it. A change to Artifactory's API reaches both copies separately.
- The placeholder audience depends on GitLab's variable precedence. It is documented in the
  fence how-to and the environment reference; an instance where a file-level variable won
  over a group one would surface as a token for `not-configured`, which Artifactory refuses.
- Invariants hold every builder to `deps_build_command`, the kaniko job to the three
  arguments, both token-minting jobs to the audience variable, the dotenv to its expiry, and
  the exchange to its endpoint and fields, with the token never printed.

## References

- [ADR-0062](0062-the-deps-image-is-built-in-stages-and-read-back.md), the build these
  credentials go into.
- [ADR-0055](0055-generation-runs-no-shell.md), the same reason the exchange is Python.
- The generated how-to *Work behind a fenced index*, which lists the variables.
