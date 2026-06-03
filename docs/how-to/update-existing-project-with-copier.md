# Update an existing project with copier

When this template ships a new version, you can pull the changes into an existing generated project without re-generating from scratch. [copier](https://copier.readthedocs.io/) tracks the template revision your project was generated from in `.copier-answers.yml` and produces a reviewable diff against the latest.

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

Review the changes with `git diff`, run the dev cycle (`./workflow.cmd format && lint && test && build`), and commit when happy.

## When questions have changed

If the new template version added or renamed a question (for example `git_hosting_service` was added in an earlier revision), copier will prompt for any missing answers during the update. Provide them — your `.copier-answers.yml` is updated in place.

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
