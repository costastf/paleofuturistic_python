# ADR-0056: Fenced code nests in lists

- **Status**: accepted
- **Date**: 2026-11-17

## Context

Both sites are built by properdocs, an mkdocs fork, with python-markdown's own `fenced_code`
extension, which reads a fence at the top level only. A fenced block indented under a
numbered step, the shape every how-to with steps uses, rendered as prose: the maintainer
how-to on extending the template tasks had two such blocks and the built page held no
`<pre>` at all. Five pages across the two sites carry that shape today, and nothing in the
build said anything.

## Decision

Both site configs enable `pymdownx.superfences`, which nests fences inside lists and other
blocks. The extension comes from pymdown-extensions, pinned at 12.3: in a generated
project's `document` dependency group, where properdocs and its theme are pinned, and in the
parent's `[tool.properdocs]` table, from which `document.*` composes its `uvx` command, so the
two sides run the same version. 13.0, two days newer, requires Python 3.11.5, and the
template's lowest supported floor is 3.11, so a generated lock could not resolve it.

Nothing else from pymdown-extensions is enabled. `attr_list` and explicit heading ids were
considered for the digit-leading headings and rejected for a convention the test suite
holds instead, since the ids then need no escaping anywhere.

## Consequences

- Fenced code inside list items renders as code on both sites. Existing pages need no edit.
- The docs toolchain grew one pinned dependency, present in a generated project's lock and
  SBOM through the `document` group, and in the parent's `uvx` invocation.
- A page whose nested fence still renders as prose is a regression in the extension or the
  config, not an authoring mistake, and the maintainer how-to is the page to check it on.

## References

- [ADR-0007](0007-diataxis-with-shipped-rationale-pages.md), the two sites this applies to.
- [Extend the template tasks](../how-to/extend-the-template-tasks.md), the page whose nested
  fences showed the defect.
