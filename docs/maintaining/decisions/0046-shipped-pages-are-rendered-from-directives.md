# ADR-0046: Shipped pages are rendered from directives

- **Status**: accepted
- **Date**: 2026-11-12

## Context

ADR-0007 ships six explanation pages into generated projects as adaptations of the canonical
pages: the same reasoning addressed to the project developer, with links that resolve inside the
generated site and a few passages knob-gated on the git host. The adaptations were made by hand,
and the invariant between the two copies compared `##` headings. Prose drift passed it. ADR-0045
found a shipped page describing fork behaviour three commits out of date, and the 2026-11-11
audit had found more; ADR-0007 named a `maintain.sync-docs` task as the open follow-up.

A byte copy would not do: the shipped copy needs different links, a different opening sentence,
different see-also lists, and jinja in one place. A second hand-maintained file was the problem.

## Decision

The canonical page is the only source. It carries the adaptation as four directives, all HTML
comments so this repository's site renders none of them:

- `<!-- template-only -->` … `<!-- /template-only -->` drops the lines between from the shipped copy.
- `<!-- shipped-only … -->` inserts its body into the shipped copy.
- `<!-- shipped: … -->` replaces the block above it; `<!-- shipped-line: … -->` replaces the one
  line above it.

`maintain.sync-docs` renders every canonical page through `render_shipped`: the marker line, the
directives, decision links rewritten to the published site, cross-repository links made relative,
and a short wording table that turns "a generated project" into "this project" and
`<your_package>` into `{{ project_slug }}`. Without `--write` it names the stale copies and exits
1; with it, it writes them. The invariant asserts each committed shipped copy equals its render,
and a second test runs the grammar on a page small enough to read.

The rendered copies are committed, since copier reads the template tree as it is. They are
generated files that happen to be checked in, and their first line says so.

The audience wording is uniform rather than hand-tuned. The hand-made copies said "the scaffold"
where the canonical page says "the template"; the render keeps "the template", which is accurate
in both places, and the canonical page was rewritten to avoid "we", which a project developer
would read as their own team.

## Consequences

- Editing a canonical page and forgetting the shipped copy is a failed invariant with a one-line
  fix, not a page that quietly ages.
- The shipped pages now carry the record links, pointed at the published site, which ADR-0007
  intended and the hand copies had dropped.
- A canonical page is harder to read in source where directives cluster; the security page's
  provenance section is the worst case, one template-only region and one shipped-only region of
  twenty lines each. The rendered sites are unaffected.
- A directive body cannot contain `--`, an HTML comment's own limit.

## References

- [ADR-0007](0007-diataxis-with-shipped-rationale-pages.md), whose open follow-up this closes.
- [ADR-0045](0045-one-home-per-rationale.md), which found the drift.
- [Keep shipped docs in sync](../how-to/sync-shipped-docs.md), the how-to with the grammar.
