# ADR-0051: The complexity bar is 8, and the parent holds it

- **Status**: accepted; narrows ADR-0048
- **Date**: 2026-11-17

## Context

A generated project's `lint.complexipy` ran complexipy over `src/` with no flag, so the bar
was the tool's default of 15. The parent did not run it at all: ADR-0048 left it out because
"complexipy would set a complexity budget for test code, which the template has no opinion on
yet".

A scan of everything this repository owns, the vendored trees excluded, found 33 functions
above 8 and three above 15. The three above 15 were all readers in the invariant suite's
support module and the docs renderer; the parent's own tooling was over the bar it shipped.
Taking the 33 down, one module per commit, left every plain `.py` function at 8 or under and
gave the template its opinion: a function in tooling or in tests splits at the same point one
in `src/` does.

The scan had read only `.py` files. The template's eight `.jinja` task modules, which
complexipy skips, held seven more functions above 8, the audit's lockfile reader at 19 among
them. A review found them the same day; they were decomposed, and the parent's check now
reads those modules with their tags stripped.

## Decision

The bar is 8. A generated project's `lint.complexipy` passes `--max-complexity-allowed 8`,
over `src/` as before. The parent's `./workflow.cmd lint` runs complexipy under the same pin
and the same bar over the paths its other checks read, `_CI/`, `tasks_render.py` and
`tests/`, and over the template's own `_CI` modules as well: `_CI/tasks/`, `info.py` and
`uv_release.py`, named one by one so the vendored tree under `template/_CI/lib` stays out.

The `.jinja` task modules are read too. Before the check runs, each is copied under
`reports/stripped-tasks/` with every block tag removed and every expression replaced by a
name, so both arms of a template `if` are counted and what an expression renders to, a string
the complexity does not depend on, is not. The copies are rebuilt on every run.

The pin joins the `lint` group and the invariant that holds the parent's lint pins equal to
the template's covers it.

## Consequences

- The next function over 8 fails locally and in CI's `lint` job, on either side, the `.jinja`
  task modules included.
- The generated gate still reads `src/` alone, so a project that edits its own `_CI/tasks/`
  past the bar is not told by its gate. Widening it to `_CI/tasks/` would also widen the
  commit-stage filter and is not decided here.
- The pyproject validator is now the only step of a generated project's `lint` the parent
  does not run.

## References

- [ADR-0048](0048-the-parent-is-judged-by-the-gate-it-ships.md), which this narrows: the
  parent now runs complexipy too.
- [ADR-0016](0016-ruff-replaces-black-isort-and-flake8.md), which put complexipy in the gate.
