# Keep shipped docs in sync

Six explanation pages exist twice: the canonical copy in this repo's docs and a shipped copy that lands in every generated project's *Developer → Explanation* section, so project developers can read the rationale behind their scaffold offline. The shipped copy is rendered from the canonical page by `./workflow.cmd maintain.sync-docs`; it is never edited by hand.

| Canonical (this repo) | Shipped (generated projects) |
|---|---|
| `docs/maintaining/explanation/design-principles.md` | `template/docs/developer/explanation/design-principles.md` |
| `docs/maintaining/explanation/the-ci-tasks-architecture.md` | `template/docs/developer/explanation/the-ci-tasks-architecture.md` |
| `docs/using/explanation/how-uv-is-used.md` | `template/docs/developer/explanation/how-uv-is-used.md` |
| `docs/using/explanation/packaging-conformance.md` | `template/docs/developer/explanation/packaging-conformance.md` |
| `docs/using/explanation/sbom-and-security-model.md` | `template/docs/developer/explanation/sbom-and-security-model.md.jinja` |
| `docs/using/explanation/testing-strategy.md` | `template/docs/developer/explanation/testing-strategy.md` |

The mapping is `SHIPPED_RATIONALE_PAGES` in `_CI/tasks/configuration.py`.

## The loop

1. Edit the canonical page.
2. Run `./workflow.cmd maintain.sync-docs --write`.
3. Commit both files together.

`./workflow.cmd maintain.sync-docs` without `--write` names the shipped pages that differ from their render and exits 1. `tests/test_template_invariants.py::test_shipped_rationale_pages_are_rendered_from_canonical` asserts the same equality, so a canonical edit that was not rendered fails `test.invariants` until it is.

## What the render does

The shipped copy is the canonical page with:

- a `<!-- canonical: … -->` marker as its first line, naming the page it was rendered from;
- every `](../decisions/NNNN-slug.md)` link pointed at the published record, since the records do not ship;
- `](../../maintaining/explanation/` links made relative, since both pages live in one directory in a generated project;
- the audience rewording in `SHIPPED_WORDING` in `_CI/tasks/maintain.py`: "a generated project" becomes "this project", `<your_package>` becomes `{{ project_slug }}`, and so on;
- the directives below applied.

## The directives

All four are HTML comments, so this repo's site renders none of them.

| Directive | Effect in the shipped copy |
|---|---|
| `<!-- template-only -->` … `<!-- /template-only -->` on their own lines | The lines between are dropped. For sections and links that only make sense in this repo. |
| `<!-- shipped-only` … `-->`, body on the lines between | The body is inserted. For passages only a project developer needs, including ones that knob-gate with jinja. |
| `<!-- shipped: … -->` directly under a paragraph, list or code block | Replaces that whole block. Multi-line form: `<!-- shipped:` on its own line, the body, then `-->`. |
| `<!-- shipped-line: … -->` directly under one line | Replaces that one line. For a table row or a list item. |

A directive body may hold jinja; the shipped copy of the security page is a `.jinja` file for that reason. An HTML comment cannot contain `--`, so a body may not either.

## Why duplication instead of links

The shipped pages used to be links to this repo's published site. That made generated projects' docs break offline and pinned them to a URL the template doesn't control forever. Copier has no mechanism to include one source file in both sites, and the adaptation step (reframing, knob-gating) is work a blind include could not do. Rendering from directives keeps one source and makes the adaptation explicit. See [ADR-0046](../decisions/0046-shipped-pages-are-rendered-from-directives.md).

## See also

- [Design principles](../explanation/design-principles.md) — the largest of the synced pages.
