# ADR-0039: `repository_url` renders well-known `[project.urls]`, or nothing

- **Status**: accepted
- **Date**: 2026-11-10
- **Record written**: 2026-11-11 (backfilled)

## Context

PyPI shows a project's links in its sidebar, with an icon per label when the label is one of
the [well-known ones](https://packaging.python.org/en/latest/specifications/well-known-project-urls/).
A generated project had no `[project.urls]`, and a placeholder table would ship links that 404
on PyPI forever.

## Decision

An optional `repository_url` question, validated as empty or an https URL with a path. When
answered, `pyproject.toml.jinja` renders `Homepage`, `Source`, `Issues` and `Changelog`, with
the host's link shapes (`/issues` on GitHub, `/-/issues` on GitLab), plus `Documentation` and a
Pages `Homepage` when the project is on github.com with Pages enabled. A trailing slash or
`.git` is dropped so a pasted clone URL works. Left empty, no table ships; it can be answered on
a later `copier update` or added by hand.

## Consequences

- The matrix generates one URL per host so both link shapes are exercised; the empty case is a
  single extra generation in the invariants, not an axis.
- The packaging-specs tests check the rendered labels against the specification.

## References

- Commit `b1a48da`, "cover every PyPA packaging specification".
- [Copier questions: repository_url](../../using/reference/copier-questions.md#repository_url).
