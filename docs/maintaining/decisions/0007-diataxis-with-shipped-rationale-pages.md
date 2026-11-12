# ADR-0007: Diátaxis for both sites, with the rationale pages shipped

- **Status**: accepted
- **Date**: 2026-07-28
- **Record written**: 2026-11-11 (backfilled)

## Context

The documentation was one walkthrough that mixed "I want to start" with "I want to understand",
and it served two audiences at once: people generating projects from the template and people
maintaining the template. Generated projects, meanwhile, got docs that linked to this
repository's published site for the rationale, which broke offline and pinned every project to a
URL the template does not control.

## Decision

Two documentation sites, each organised by [Diátaxis](https://diataxis.fr/):

- This repository's site has two areas, *Using the template* and *Maintaining the template*,
  each with tutorials, how-to, reference and explanation.
- A generated project's site has the project's own four sections plus a *Developer* section
  documenting the inherited scaffold, so a project's docs stay about the project.

Six explanation pages exist twice. The canonical copy lives here; the shipped copy is an
adaptation addressing the project developer, opens with a `<!-- canonical: … -->` marker, and
may knob-gate passages with jinja. An invariant checks the marker and that the shipped page's
headings are a subset of the canonical page's. Decision records are not shipped; the shipped
explanation pages link to them on the published site.

## Consequences

- Each new page has a home decided by what the reader needs, and a reader can tell which site
  they are on by whether the subject is the template or their project.
- The six pages were synced by hand until ADR-0046: heading drift was caught, prose drift was
  not, and the 2026-11-11 audit found some. `maintain.sync-docs` now renders them.
- The generated task catalog is checked against the registered tasks, and every page in a
  generated nav must exist, so the shipped docs cannot name a task or page that is gone.

## References

- Commit `5531689`, "split documentation by persona across template and generated project".
- [Keep shipped docs in sync](../how-to/sync-shipped-docs.md),
  [Design principles: Diátaxis for our own docs](../explanation/design-principles.md#diataxis-for-our-own-docs).
