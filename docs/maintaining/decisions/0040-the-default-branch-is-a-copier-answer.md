# ADR-0040: The default branch is a copier answer

- **Status**: accepted
- **Date**: 2026-11-12

## Context

ADR-0014 made the version bump arriving on the default branch what a release is. That gave the
branch's name a job in five places: the publish workflow's trigger, the Pages workflow's trigger,
the check in `release` that refuses to start anywhere else, the base of the release pull or
merge request, and the CI badge, which reads the status of one named branch. All five spelled
`main`, and ADR-0014 closed by noting it.

A project whose default branch is not `main` therefore had every one of them wrong, and a
`copier update` put them back. The GitLab pipeline was the exception: GitLab names the branch
itself as `$CI_DEFAULT_BRANCH`, so that rule needed no spelling. GitHub Actions has no such
variable in a trigger, since `on.push.branches` is read before any job runs, which rules out
computing the name at run time.

## Decision

`default_branch` is a copier question, default `main`. The validator takes what
`git check-ref-format --branch` would, narrowed to the characters that need no quoting in a YAML
list or a badge URL: letters, digits, `.`, `_`, `/` and `-`, starting with a letter or digit, no
`..`, not ending in `/` or `.lock`.

The answer is spelled in one place at run time, `DEFAULT_BRANCH` in `_CI/tasks/configuration.py`,
which `release`, the host modules' badge and pull-request helpers read. The two workflow files
have it rendered in at generation, because a trigger cannot read a module. `pages.yaml` became a
`.jinja` file for that, with its Actions expressions inside `{% raw %}` blocks as `publish.yaml`
already had. The GitLab pipeline keeps `$CI_DEFAULT_BRANCH`; the answer has to agree with the
project's setting there, which the question's help says.

Prose that named the branch now either renders the answer, in the pages copier renders, or says
"the default branch", in the pages it copies verbatim.

The template's own tests generate the matrix cells with the default and one extra project with
`trunk`, then search that project for the word `main`. A cell generated with the default cannot
tell a rendered answer from a literal left behind.

## Consequences

- Renaming the default branch is a `copier update` with a new answer. Existing projects are asked
  once and keep `main` by accepting the default.
- Where the name is spelled is now a property the invariant suite enforces, so a future task or
  workflow that writes `main` fails the test rather than waiting for a project on another branch
  to find it.
- The branch is still one name for the whole project. A project that releases from several
  branches is outside what the template describes, as before.
- `pages.yaml` is a template now, so an edit to it has to keep every `${{ }}` inside a raw block
  or generation fails on the first one copier tries to render.

## References

- [ADR-0014](0014-a-release-is-the-version-bump-arriving-on-the-default-branch.md), which named
  this as the next decision in its area.
- [Copier questions: `default_branch`](../../using/reference/copier-questions.md#default_branch).
