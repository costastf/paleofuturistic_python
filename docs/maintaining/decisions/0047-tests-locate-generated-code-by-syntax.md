# ADR-0047: Tests locate generated code by syntax

- **Status**: accepted
- **Date**: 2026-11-16

## Context

Many invariants assert something about one function in a generated task module: that
`combine_coverage` is the one place the coverage floor is enforced, that `run_scope` skips the
derived writes after a failure, that the on-demand `test.coverage` task writes no badge. Such an
assertion needs the function's text and nothing else, since "exists somewhere in the file" is a
weaker claim, and an ordering or an absence means nothing outside one body.

Thirty-seven tests cut that text out with string slices: from `def name` or `@logged('name')`
up to the next `\ndef `, `\n@`, `\n@task` or `\nSTEPS`, and in three cases up to the end of the
file. The end delimiter is the layout of the file at the time the test was written. Two slices
had already gone wrong by the time this was looked at. The `combine_coverage` slice bounded by
`\n@task` ran through `tox_matrix`, which carries only `@logged`, so the test that says the
combine merges the data would have kept passing with the merge moved into the matrix. The
import check `'tox' in imported_from_test` passed because the line it sliced contained
`tox_matrix`; the function it meant to find was never imported under that name. The
`run_scope` and `test` aggregator slices were the rest of their files, correct only while
each function stayed last.

## Decision

A test locates generated code by its syntax tree, never by string position.

`support.py` parses a module once and offers four lookups: `function_source(text, name)` is
the text of one definition from its first decorator to its last line, `task_source(text, name)`
is the function whose `@logged` decorator names the task, `parameter_defaults(node)` is a
signature as a mapping of parameter to default source, and `module_imports(text)` is every
import statement that runs at startup, under a module-level `if` or `try` included and inside
a function excluded. Each lookup raises by name when the definition is gone.

What a test asserts over the located text is unchanged. `'coverage combine' in combine` is
still a substring check. The lookup fixes what the text is, so the assertion means what the
test's name says, and that is where the fragility was.

Markdown, YAML and TOML have no syntax tree worth the name here, and the tests that slice them
keep doing so.

## Consequences

- Adding a helper between two tasks, dropping a decorator or reordering a module no longer
  moves what a test reads. ADR-0042 and ADR-0043 each added a function to a task module, and
  an edit of that shape is what a slice bounded by its neighbour is exposed to.
- A renamed function fails the suite with `LookupError: no top-level function 'old'`, naming
  the test's own stale expectation, rather than with an assertion message about a body that
  belongs to a different function.
- The import assertion in the coverage-floor test now names `tox_matrix`, the function the
  registry runs, where it used to pass on a substring.
- `tests/invariants/test_support.py` covers the helpers over a hand-written module, so a change
  to how they bound a definition is tested without generating a project.

## References

- [Test the template](../how-to/test-the-template.md), which names the helpers.
- [ADR-0042](0042-refresh-deps-moves-the-boundary-and-the-pins-together.md) and
  [ADR-0043](0043-the-gitlab-deps-tag-is-computed-by-the-launcher.md), edits of the shape the
  slices were exposed to.
