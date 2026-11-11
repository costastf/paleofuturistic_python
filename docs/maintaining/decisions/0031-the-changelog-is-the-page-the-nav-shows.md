# ADR-0031: The changelog lives at `docs/reference/changelog.md`

- **Status**: accepted
- **Date**: 2026-11-10
- **Record written**: 2026-11-11 (backfilled)

## Context

Releases wrote the changelog to `docs/changelog.md`, a page no nav entry listed, while
*Reference → Changelog* showed a placeholder that never changed. Two files, one of them
invisible and the other one empty.

## Decision

`[tool.commitizen] changelog_file` and `CHANGELOG_FILE` in the tasks both name
`docs/reference/changelog.md`, the page the nav shows. The changelog is incremental: each
release adds its entries below the page's header, so the title and intro stay. A page with no
releases in it yet gets the whole history from the tags on the first run. `release.changelog`
stages that one file and commits it only when something changed.

## Consequences

- The `Changelog` entry in `[project.urls]` points at a page that exists.
- Projects updating past this change get their full history written into the new page on the
  next release and can delete the old file.

## References

- Commit `cb71599`, "write the changelog to the page the docs nav lists".
- [Upgrading past the changelog move](../../using/how-to/update-existing-project-with-copier.md#upgrading-past-the-changelog-move).
