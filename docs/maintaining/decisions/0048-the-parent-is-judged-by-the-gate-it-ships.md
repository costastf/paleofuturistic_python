# ADR-0048: The parent is judged by the gate it ships

- **Status**: accepted
- **Date**: 2026-11-16

## Context

ADR-0016 settled the lint gate a generated project gets: ruff with everything selected, the
formatter, pylint for what ruff lacks, ty for types, complexipy and the pyproject validator. The
repository that ships that gate ran ruff and the formatter over itself, since commit `65547fd`
of 2026-08-07, and its lint task said so in its docstring: pylint, ty and complexipy were not
wired up yet.

The first pylint run over the parent reported 48 findings and the first ty run 28. Most were
style the template's own disable list already names, but some were not. Four places loaded a
module by path without checking that the spec or its loader existed. The packaging suite read
`PKG-INFO` out of an sdist through a method that returns None for a directory member. A
regular-expression match was dereferenced unchecked. One assertion tested a non-empty string
literal for truth. Two `ast` readers called `.elts` and `.args` on nodes that need not have
them. Each is the kind of error the generated gate catches on the first commit.

## Decision

`./workflow.cmd lint` in this repository runs ruff, the formatter, pylint and ty, over `_CI/`,
`tasks_render.py` and `tests/`, under the same pins and the same rule set a generated project
gets.

The root `pyproject.toml` carries the template's pylint disable list and ty environment, minus
what has no counterpart here: there is no `src/` to put on pylint's path, and no module touches
the cyclonedx classes the template's ty overrides are scoped to. The three pins in the `lint`
group are the template's, and an invariant holds them equal, so bumping one side without the
other fails the suite rather than quietly judging the two by different versions.

Where the parent's code departs from what the rules want, the departure is written down at the
site: pytest fixtures redefine outer names by design, so the two test modules that consume
them disable that one message with the reason; `_CI` is not a snake-case module name because
the launcher and every generated project spell the directory that way; the gate module is
over pylint's line budget because one module per subject is the rule and the gate is the
largest subject.

complexipy and `validate-pyproject` stay out. The validator checks a package's metadata and
this repository publishes no package; its `pyproject.toml` is tooling configuration. complexipy
would set a complexity budget for test code, which the template has no opinion on yet. The gap
is two named steps rather than three.

## Consequences

- A change to the parent is held to the standard it ships. The findings above are fixed in
  the same commit, and the next one of their kind fails locally and in CI's `lint` job.
- `lint` is slower by a pylint and a ty run over some twenty modules, locally and in CI's
  `lint` job.
- The parent's task registry casts each function to `Task` when registering it, as the
  template's modules do, because invoke's `@task` is untyped and ty reads the decorated name
  as a function.
- Four load-by-path sites became one `load_module` helper in the invariant support module and
  a guard each in `tasks_render.py`, `maintain.py` and `conftest.py`. The resolver loader in
  `tasks_render.py` now reports a missing module the same way it reports an unreadable one.

## References

- [ADR-0016](0016-ruff-replaces-black-isort-and-flake8.md), the gate this one applies to its
  author.
- [ADR-0047](0047-tests-locate-generated-code-by-syntax.md), whose helpers the ty findings in
  the `ast` readers were fixed through.
- [Test the template](../how-to/test-the-template.md).
