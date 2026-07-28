# Keep shipped docs in sync

Five explanation pages exist twice: the canonical copy in this repo's docs and a shipped copy that lands in every generated project's *Developer → Explanation* section, so project developers can read the rationale behind their scaffold offline.

| Canonical (this repo) | Shipped (generated projects) |
|---|---|
| `docs/maintaining/explanation/design-principles.md` | `template/docs/developer/explanation/design-principles.md` |
| `docs/maintaining/explanation/the-ci-tasks-architecture.md` | `template/docs/developer/explanation/the-ci-tasks-architecture.md` |
| `docs/using/explanation/how-uv-is-used.md` | `template/docs/developer/explanation/how-uv-is-used.md` |
| `docs/using/explanation/sbom-and-security-model.md` | `template/docs/developer/explanation/sbom-and-security-model.md.jinja` |
| `docs/using/explanation/testing-strategy.md` | `template/docs/developer/explanation/testing-strategy.md` |

## The contract

- **Edit the canonical page first**, then propagate the change to the shipped copy.
- The shipped copies are *adaptations*, not byte copies: they address the generated project's developer ("your scaffold", "your project"), drop template-repo-only material, and may knob-gate sections with jinja (the SBOM page wraps its Dependency Track layer in `{% if integrate_dependency_track %}`).
- Every shipped copy opens with a `<!-- canonical: ... -->` HTML comment naming its source page. Keep it.
- Section structure must stay aligned: the shipped copy's `##` headings must be a subset of the canonical page's. `tests/test_template_invariants.py::test_shipped_rationale_pages_match_canonical` enforces both the marker and the heading subset, so a canonical edit that renames or removes a section fails `test.invariants` until the shipped copy follows.

## Why duplication instead of links

The shipped pages used to be links to this repo's published site. That made generated projects' docs break offline and pinned them to a URL the template doesn't control forever. Two hand-maintained copies with a drift ratchet is the pragmatic middle: copier has no mechanism to include one source file in both sites, and the adaptation step (reframing, knob-gating) is genuine work a blind include couldn't do.

## See also

- [Design principles](../explanation/design-principles.md) — the largest of the synced pages.
