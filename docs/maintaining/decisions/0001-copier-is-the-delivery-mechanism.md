# ADR-0001: Copier is the delivery mechanism

- **Status**: accepted
- **Date**: 2026-05-29
- **Record written**: 2026-11-11 (backfilled)

## Context

The template started in November 2024 as a cookiecutter project, with cruft added for updates.
Three things kept costing work:

- Leaving out the unchosen host's files meant a post-generation hook that walked the output and
  deleted them. A rendering decision was being made as a filesystem operation after the fact.
- The questionnaire knew strings and lists. Booleans, choices and validation lived in hook code.
- The vendored `_CI/lib/` tree must never be rendered, which cookiecutter expressed as a
  `_copy_without_render` glob list that had to be kept in step with the tree.

Updates through cruft worked, but cruft tracks the template at the file level with a plain diff,
and the hook-driven deletions did not replay cleanly.

## Decision

Migrate the engine to [copier](https://copier.readthedocs.io/). Specifically:

- `copier.yml` holds the questionnaire, with typed questions and per-question `validator`
  expressions that abort before any file is written.
- A file or directory whose rendered name is empty is not created, so host- and feature-specific
  files are expressed as conditional filenames
  (`{% if git_hosting_service == 'github' %}.github{% endif %}`). Nothing is deleted after
  generation.
- Only files ending in `.jinja` are rendered; everything else is copied verbatim. The vendored
  tree needs no exclusion list.
- `.copier-answers.yml` records the template revision and the answers, and `copier update`
  performs a three-way merge against them.
- The work that cannot be declarative (installing the licence, stamping dates and the uv pin,
  the executable bit) runs once from `tasks_render.py`, gated to `copier copy`.

## Consequences

- A generated project has exactly one host code path; `from .{{ git_hosting_service }} import …`
  is rendered concrete at copy time and the other module never ships.
- Generation needs `--trust`, because the template runs a task.
- Ownership is per file. Copier cannot know that one section of `pyproject.toml` is the
  template's and another the project's, so template-owned files are shaped so that user edits
  land in predictable places, and project-owned tasks got a file of their own (ADR-0015).
- A project tracks one template; composing several is not possible.

## References

- Commit `115d161`, "migrate the template engine from cruft to copier".
- [Why copier?](../explanation/why-copier.md), [Generation internals](../reference/generation-internals.md).
