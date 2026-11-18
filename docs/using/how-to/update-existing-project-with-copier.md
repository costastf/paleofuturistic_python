# Update an existing project with copier

When this template ships a new version, you can pull the changes into an existing generated project without re-generating from scratch. [copier](https://copier.readthedocs.io/) records the template revision your project was generated from — it's stored in `.copier-answers.yml` — and produces a reviewable diff against the latest version.

## The basic update

From the root of your generated project:

```bash
uvx copier update --trust
```

`--trust` is required because the template runs a post-copy task (`tasks_render.py`). Copier will not execute tasks from a template it doesn't trust.

copier:

1. Re-renders the template at the new revision using your stored answers (`.copier-answers.yml`).
2. Performs a three-way merge against your current files.
3. Applies the result, flagging conflicts for manual resolution.

Review the changes with `git diff`, run `./workflow.cmd format && ./workflow.cmd preflight`, and commit when happy.

## When questions have changed

If the new template version added or renamed a question (for example `git_hosting_service` was added in an earlier revision), copier will prompt for any missing answers during the update. Provide them — your `.copier-answers.yml` is updated in place.

## Upgrading past the Dependency-Track removal

Earlier versions asked `integrate_dependency_track` and, when it was on, uploaded the SBOM to an OWASP Dependency-Track server after every publish. The template no longer does this. The SBOM is still generated, validated and shipped inside every wheel. Only the upload is gone.

Updating removes:

- the `secure.sbom-upload` task and the `OWASP_DTRACK_SETTINGS` constant in `_CI/tasks/configuration.py`;
- the `OWASP_DTRACK_URL` / `OWASP_DTRACK_API_KEY` environment block in the GitHub publish workflow;
- the *Upload an SBOM to Dependency Track* page from the developer docs.

Copier no longer asks the question, and an `integrate_dependency_track` line left in `.copier-answers.yml` has no effect. If you customised any of the removed code, expect conflicts in `secure.py`, `release.py` or `publish.yaml`. Resolve them in favour of the template's version.

After the update:

1. Delete the `OWASP_DTRACK_URL` and `OWASP_DTRACK_API_KEY` secrets from your repository or group CI settings. Nothing reads them any more.
2. If your organisation still wants every release in Dependency-Track, add the upload as your own task in `_CI/tasks/local.py`, which `copier update` never touches (see *Add a workflow task* in your project's developer docs), and call it from your pipeline after `release.publish`. The SBOM to send is `src/<your_package>/sbom.cdx.json`. Dependency-Track's [CI/CD integration guide](https://docs.dependencytrack.org/usage/cicd/) documents the upload endpoint.

## Upgrading past the packaging-conformance change

This change adds a question and three checks:

- **`repository_url`** is asked once, with a suggestion built from the host, your email's local part and the slug. Accept or correct it to get `[project.urls]` (PyPI's sidebar links); clear it to skip. `copier update --defaults` takes the suggestion without asking, so check the result before committing.
- **New gates.** `lint.pyproject` (validate-pyproject) runs on commits that stage `pyproject.toml` and in `preflight`; `build.package` now runs `twine check --strict` and `check-wheel-contents`. A `pyproject.toml` you edited may fail the first run. The error names the field; fix it rather than skip the gate.
- **New dependency group** `build`, and new pins in `lint` and `security`. Run `uv lock` after the update and commit `uv.lock` with it.
- **Publishing.** The publish job now signs PEP 740 attestations. On GitLab it also requests `id_tokens:`, and PyPI needs a Trusted Publisher registered for the project (the new *Set up Trusted Publishing* how-to). If you publish with `UV_PUBLISH_*` credentials, nothing changes: that path uploads without attestations.

## Upgrading past the fork pull-request coverage

On GitHub, `continuous-integration.yaml` and `security-audit.yaml` now trigger on `pull_request` as well as `push`. A pull request from a fork runs the gate, and the audit when it touches the dependency surface, in a job that installs the dependencies with uv on the runner because a fork's token cannot push the deps image. Pull requests from your own branches run nothing on the new trigger, since the push already did. After updating, require the `Preflight` check in branch protection; the [hardening how-to](harden-github-repository.md) has the details. See [ADR-0041](../../maintaining/decisions/0041-fork-pull-requests-run-the-gate-on-the-runners-image.md).

## Upgrading past the default-branch question

`copier update` asks `default_branch`, with `main` as the default. Accept it if your default branch is `main` and nothing changes. Answer with your branch's name otherwise: the publish and Pages workflows start triggering on it, `release` starts from it, release pull or merge requests target it, and the CI badge reads it. Before the question, all of those spelled `main`, so a project on another branch had to edit each by hand after every update. See [ADR-0040](../../maintaining/decisions/0040-the-default-branch-is-a-copier-answer.md).

## Upgrading past the `grade` rename

The pyscn tasks answer to `grade` instead of `quality`: `./workflow.cmd grade`, `grade.pyscn`, `grade.pyscn-analyze` and `grade.pyscn-check`. The module moved with them, `_CI/tasks/quality.py` to `_CI/tasks/grade.py`, and so did the dependency group, `quality` to `grade`. After the update, `uv lock` records the new group name, and a `quality.py` left behind under `_CI/tasks/` is yours to delete: nothing imports it. Only your own scripts or notes that spelled the old command or group need the new name; the hooks and the pipelines run `preflight`, which never named either.

## Upgrading past the one-sequence publish

`release.publish` is `release.dist`, `release.attest` and the upload, in that order, and `release.ship` runs it; the `--prebuilt` flag is gone. A pipeline or script of your own that ran `release.dist`, `release.attest` and `release.publish --prebuilt` as three commands runs `release.publish` alone now, or `release.ship` where it detects the release itself. See [ADR-0049](../../maintaining/decisions/0049-publish-is-one-sequence.md).

## Upgrading past building the deps image every run

On GitHub, `build-deps-image` no longer reuses a tag that already exists in the registry: every run builds and pushes, and reuse is the opt-in `container.publish --reuse`. The shipped workflow passes no flag. If you want the old behaviour in a job of your own, restrict who can write to the `<repo>-deps` package first, then add the flag; the generated CI framework reference explains what a reused tag trusts. See [ADR-0050](../../maintaining/decisions/0050-the-deps-image-is-built-every-run-unless-asked-to-reuse.md).

## Upgrading past the exported commit range

The shipped `Preflight` jobs fetch full history and export `PRE_COMMIT_FROM_REF` and `PRE_COMMIT_TO_REF`, so `lint.commitizen` checks a pull request's commits, or what a push added, instead of the one commit a shallow checkout holds. A CI job of your own that runs the gate needs the same two things, `fetch-depth: 0` on the checkout and the two variables from the event, or it checks only the tip and, on a pull request, only the merge commit, which commitizen accepts. See [ADR-0053](../../maintaining/decisions/0053-ci-hands-the-commit-check-the-range-it-cannot-infer.md).

## Upgrading past the UTC quarantine boundary

`[tool.uv] exclude-newer` is spelled as an instant, `YYYY-MM-DDT00:00:00Z`, where it was a bare date. Your `pyproject.toml` holds the date stamped at generation, so the update may show a conflict on that line: keep your own date and give it the suffix, then `uv lock`. The lock records the boundary as an instant already; the spelling fixes it to midnight UTC instead of midnight in the zone the lock was last written in, so `uv lock` may move the recorded instant by your zone's offset and nothing else. See [ADR-0054](../../maintaining/decisions/0054-the-quarantine-boundary-is-an-instant-in-utc.md).

## Upgrading past nested code blocks in the docs

The `document` group pins `pymdown-extensions`, and `properdocs.yml` enables `pymdownx.superfences`, so a fenced block indented under a list item renders as code. Run `uv lock` after the update and commit `uv.lock` with it. Pages already written need no change. See [ADR-0056](../../maintaining/decisions/0056-fenced-code-nests-in-lists.md).

## Upgrading past the formatting conventions

Ruff formats with a line length of 120 and single quotes, and checks docstrings against the Google convention. None of the three is a copier question, and the template does not carry the numpy convention it used before 2026-04-13. A project generated before then meets the Google rules on its first `lint` after the update: ruff reports each docstring section it cannot read, and the fixes are by hand, since the docstring rules have no autofix. Keeping `convention = "numpy"` in your `pyproject.toml` works, at the cost of resolving that line at every update. See [ADR-0059](../../maintaining/decisions/0059-formatting-conventions-are-not-configurable.md).

## Upgrading past the 3.11 patch-level floor

A project with `min_python_version` of `3.11` floors at `3.11.18` after the update: `requires-python` and `.python-version` both spell the patch, and the `document` group moves `pymdown-extensions` to 13.1, which needs 3.11.5. Run `uv lock` and commit `uv.lock` with the update. The first `uv run` afterwards fetches 3.11.18 if the machine has no such interpreter; a project that pinned another 3.11 by hand in `.python-version` shows that line as a conflict, and the patch spelling is the one to keep, since uv refuses a minor-only pin that resolves to an older 3.11 against the floor. The deps image already carries 3.11.18. See [ADR-0060](../../maintaining/decisions/0060-the-3-11-floor-is-its-current-patch-release.md).

## Upgrading past the tag-on-main release flow

`release` used to create the tag on the release branch and push it with the branch. On GitLab that published the version before the MR was reviewed; on both hosts a squash merge left the tag pointing at a commit `main` never saw, and nothing published. Now `release` creates no tag. The publish job runs on every push to the default branch and hands it to `release.ship`, which publishes when `[project].version` changed between the previous tip and the new one: it creates the tag on the new tip through the host's Release API (a Release entry appears on the releases page), then builds, signs and uploads. Merge release PRs/MRs any way you like.

Updating changes:

- `.github/workflows/publish.yaml` or `.gitlab-ci.yml`: the publish job runs `release.ship` and, on GitHub, holds `contents: write` so `GITHUB_TOKEN` can create the tag. `detect-release-tag.yaml` is gone; `pages.yaml` runs `release.detect` itself.
- `release.bump` commits the version files itself; `release.changelog` takes `--version`; `release.push`, which had become a bare `git push` once tags were CI's to create, is gone.

After the update:

1. If the `pypi` environment has required reviewers or approvers, remove them and restrict the environment to the default branch instead; the job now runs on every push to it. The PyPI Trusted Publisher registration itself is unchanged.
2. On GitHub, if a ruleset restricts who may create `v*` tags, add a bypass for GitHub Actions, or `release.tag` fails.
3. A release branch opened before the update carries a tag on its bump commit. Delete that tag everywhere (`git tag -d vX.Y.Z && git push origin :refs/tags/vX.Y.Z`) before merging, or `release.tag` refuses to create it on the default branch because it exists on another commit.

## Upgrading past the changelog move

Releases used to write the changelog to `docs/changelog.md`, a page missing from the docs nav, while *Reference → Changelog* showed a placeholder that never changed. They now write `docs/reference/changelog.md`, the page the nav shows.

Nothing is lost: the new page has no releases in it yet, so the first `release.changelog` after the update writes your full history into it from the tags, below the page's header. Later releases add their entries on top. Delete `docs/changelog.md` in that release, or any time after. If you hand-edited entries there, copy them across before deleting it, since the history is rebuilt from commit messages.

## Resolving conflicts

Copier uses a three-way merge; conflicts appear as standard conflict markers in the affected files. The most common cause is that you customised a file the template also changed. Resolve them by hand and re-run `./workflow.cmd test`.

## Pinning a specific template version

By default `copier update` fetches the latest tagged release. To pin to a specific ref:

```bash
uvx copier update --trust --vcs-ref <tag-or-commit>
```

## When the upstream is unreachable

`copier update` needs network access to fetch the template. In an air-gapped environment, clone the template repo separately and point copier at the local path:

```bash
uvx copier update --trust /path/to/local/clone
```

## See also

- [Copier documentation](https://copier.readthedocs.io/en/stable/updating/) — the full update workflow.
- [Copier questions](../reference/copier-questions.md) — what each answer in `.copier-answers.yml` controls.
