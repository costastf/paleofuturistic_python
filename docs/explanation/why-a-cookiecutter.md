# Why a cruft template?

The template is delivered as a [cookiecutter](https://cookiecutter.readthedocs.io/) project consumed via [cruft](https://cruft.github.io/cruft/). This page explains why, and what we considered as alternatives.

## What cookiecutter + cruft buys us

**Cookiecutter** is the underlying engine: a Jinja-templated directory tree with a `cookiecutter.json` questionnaire and optional Python pre/post hooks. It's mature, ubiquitous in the Python ecosystem, and trivial to inspect — the template is just files.

**Cruft** is a thin wrapper that adds one critical capability: **updates**. A project generated via cookiecutter alone is a one-way fork — the template can improve, but the generated project has no way to pull those improvements in. Cruft tracks the template revision in `.cruft.json` and lets you replay later versions of the template over the existing project with a reviewable diff.

The combination gives us:

- A familiar prompt-driven generation flow.
- A standard format other templates already follow (low surprise).
- A working update path — generated projects don't ossify.
- Per-file opt-out via `.cruft.json`'s `skip` list — divergence is supported.

## What we considered

### Copier

[Copier](https://copier.readthedocs.io/) covers the same ground (Jinja templates + updates) with a more sophisticated update algorithm and richer questionnaire types. It's a credible choice. We picked cruft because:

- Cookiecutter has wider Python-community familiarity; new contributors don't need to learn a second tool.
- Cruft's `.cruft.json` is simpler than Copier's `.copier-answers.yml` for our needs.
- The template's existing audience already used cruft when this lineage was established.

Copier remains the alternative we'd reach for if cookiecutter or cruft stalled.

### Hatch new / poetry new / uv init

These commands generate single-file or minimal-layout starts. They don't carry CI scaffolding, vendored tooling, or update paths. Useful for prototypes, not for the "enterprise-ready package" use case the template targets.

### A custom shell or Python script

Some teams write a `bootstrap-project.sh` instead of using a templating tool. It works, but reinvents update tracking, questionnaire handling, and Jinja rendering — and locks the format into a bespoke shape no one else recognises.

### A scaffolding monorepo (one repo with all templates)

Considered for variants (CLI vs. library vs. service). Rejected because cruft handles variation through questionnaire branches (e.g. `git_hosting_service`, `integrate_dependency_track`) without forking the template. Variants live as code paths inside one repo.

## What we gave up

- **Per-file ownership tracking.** Cruft's diff is at the file level; it doesn't know "this section of pyproject.toml is template-owned, that section is yours." We compensate by structuring template-owned files so user edits land in predictable, non-overlapping locations (e.g. dependency groups vs. project metadata).
- **Multi-template composition.** Cruft tracks one template at a time. You can't `cruft update` from both this template and a separate `docs-only` template in the same project.

## See also

- [Design principles](design-principles.md) — what the template chose to opinionate.
- [Update an existing project with cruft](../how-to/update-existing-project-with-cruft.md) — the practical update flow.
