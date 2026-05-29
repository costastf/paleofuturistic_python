# Why copier?

The template is delivered as a [copier](https://copier.readthedocs.io/) project. This page explains why, and what we considered as alternatives.

## What copier buys us

**Copier** is a Jinja-templated directory tree with a `copier.yml` questionnaire, native conditional filenames, and a built-in update algorithm. It is actively maintained and designed precisely for the "generate once, update many times" use case.

The key capabilities that drove the choice:

- **Robust update algorithm.** Copier records the template source, revision, and all answers in `.copier-answers.yml` and replays later template versions over the existing project with a three-way merge. The merge is more accurate than a plain diff because copier knows the base revision and both sides of the change.
- **Richer questionnaire types.** Choices, booleans, computed defaults, and per-question validators are all first-class — no custom hook code needed for the questionnaire layer.
- **Native conditional filenames.** A file or directory whose rendered name is empty string is simply skipped. The unchosen git-host scaffolding, the optional Pages workflow, and similar variants are expressed as filename conditions — no filesystem-walking post-gen hook to delete the wrong files.
- **Per-file `.jinja` rendering.** Only files whose names end in `.jinja` are rendered through Jinja (suffix stripped on output); everything else is copied verbatim. This replaces cookiecutter's `_copy_without_render` glob list and makes the rendering boundary explicit and per-file.

## What we considered

### cookiecutter + cruft

[Cookiecutter](https://cookiecutter.readthedocs.io/) was the previous engine: a Jinja-templated directory tree with a `cookiecutter.json` questionnaire and optional Python pre/post hooks. [Cruft](https://cruft.github.io/cruft/) wrapped it to add an update path via `.cruft.json`. The combination worked but had limitations that copier resolves:

- Conditional file selection required a post-gen hook to delete unchosen files — filesystem operations after the fact, not a rendering decision.
- Questionnaire types were limited to strings and lists; booleans and choices required hook-side validation.
- The `_copy_without_render` glob list was a template-level workaround for vendored content that should never be Jinja-expanded.

Copier makes all three of those first-class features.

### Hatch new / poetry new / uv init

These commands generate single-file or minimal-layout starts. They don't carry CI scaffolding, vendored tooling, or update paths. Useful for prototypes, not for the "enterprise-ready package" use case the template targets.

### A custom shell or Python script

Some teams write a `bootstrap-project.sh` instead of using a templating tool. It works, but reinvents update tracking, questionnaire handling, and Jinja rendering — and locks the format into a bespoke shape no one else recognises.

### A scaffolding monorepo (one repo with all templates)

Considered for variants (CLI vs. library vs. service). Rejected because copier handles variation through questionnaire branches (e.g. `git_hosting_service`, `integrate_dependency_track`) without forking the template. Variants live as code paths inside one repo.

## What we gave up

- **Per-file ownership tracking.** Copier's update is at the file level; it doesn't know "this section of pyproject.toml is template-owned, that section is yours." We compensate by structuring template-owned files so user edits land in predictable, non-overlapping locations (e.g. dependency groups vs. project metadata).
- **Multi-template composition.** Copier tracks one template at a time per project. You can't `copier update` from both this template and a separate `docs-only` template in the same project.

## See also

- [Design principles](design-principles.md) — what the template chose to opinionate.
- [Update an existing project with copier](../how-to/update-existing-project-with-copier.md) — the practical update flow.
