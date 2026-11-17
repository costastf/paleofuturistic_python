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
Taking the 33 down, one module per commit, left 477 functions with a maximum of 8 and gave
the template its opinion: a function in tooling or in tests splits at the same point one in
`src/` does.

## Decision

The bar is 8. A generated project's `lint.complexipy` passes `--max-complexity-allowed 8`,
over `src/` as before. The parent's `./workflow.cmd lint` runs complexipy under the same pin
and the same bar over the paths its other checks read, `_CI/`, `tasks_render.py` and
`tests/`, and over the template's own `_CI` modules as well: `_CI/tasks/`, `info.py` and
`uv_release.py`, named one by one so the vendored tree under `template/_CI/lib` stays out.

The pin joins the `lint` group and the invariant that holds the parent's lint pins equal to
the template's covers it.

## Consequences

- The next function over 8 fails locally and in CI's `lint` job, on either side.
- The template's `.jinja` task modules are not read by complexipy, which sees only `.py`
  files, and the generated gate reads `src/` alone, so those five modules are held by review
  rather than by a check. Widening the generated gate to `_CI/tasks/` would close that; it
  would also widen the commit-stage filter and is not decided here.
- The pyproject validator is now the only step of a generated project's `lint` the parent
  does not run.

## References

- [ADR-0048](0048-the-parent-is-judged-by-the-gate-it-ships.md), which this narrows: the
  parent now runs complexipy too.
- [ADR-0016](0016-ruff-replaces-black-isort-and-flake8.md), which put complexipy in the gate.
