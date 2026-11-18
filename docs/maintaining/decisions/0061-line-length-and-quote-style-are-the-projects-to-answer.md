# ADR-0061: Line length and quote style are the project's to answer

- **Status**: accepted; reverses two of the three rulings in ADR-0059
- **Date**: 2026-11-18

## Context

ADR-0059 kept the line length, the quote style and the docstring convention as the template's
own, on the reasoning that three more answers to carry forward on every update were not worth
a formatting block nobody wants changed. The maintainer wanted the choice back for the first
two: 120 columns and single quotes are the template's taste, and a project that disagrees was
left editing the generated file and resolving that line at every update.

Making them questions has a trap. The shipped sources, `src/`, `tests/` and the tooling under
`_CI/tasks/`, are written at 120 columns with single quotes. A project that answered 88 and
double would fail its own `lint` on the formatter before its first commit, and at 88 the
tooling fails E501 on 603 lines, comments and strings the formatter does not rewrap, which
no answer should be able to break.

Ruff resolves the closest `pyproject.toml` with a `[tool.ruff]` table for each file, and
`_CI/pyproject.toml` has one. Pylint reads one configuration from the project root.

## Decision

`line_length` (79 to 320, the range ruff accepts) and `quote_style` (`single` or `double`)
are copier questions, defaulting to 120 and single, so an earlier project that keeps the
defaults sees no change.

They govern `src/` and `tests/`. The render hook formats both trees with the ruff the lint
group pins, read back out of the rendered `pyproject.toml`, right after copier writes the
files, so the project's code meets its own gate from the first commit. `_CI/` keeps the
template's 120 columns and single quotes through its own `pyproject.toml`: the shipped tooling
is the template's and is updated by it, and ruff resolves that file for the tree whatever the
root says.

Pylint's `line-too-long` is off in the generated configuration, and `max-line-length` is gone
with it: pylint would hold every tree to the root's width, and ruff's E501 already checks each
tree at its own. One checker, one width per tree.

The docstring convention stays as ADR-0059 ruled. Fourteen shipped modules carry Google
sections, the docstring rules have no autofix that could rewrite them, and a numpy project
would fail its own lint on code it did not write.

## Consequences

- A project generated with the defaults is byte-for-byte what it was, except the pylint
  block, which loses a dead width and gains a disabled rule.
- Generation runs one more subprocess, `uvx ruff@<pin> format src tests`, which is a no-op
  on the defaults. It runs on `copier copy` only, as the whole hook does; a project changing
  its answer on `copier update` runs `./workflow.cmd format` itself, and the upgrade how-to
  says so.
- `_CI/pyproject.toml` no longer has to agree with the root's width. Its comment used to say
  it must, because pylint would reject what ruff accepted; with `line-too-long` off, that band
  cannot open.
- An invariant generates a project answering 88 and double and runs ruff's format check and
  lint over it, with the tooling asserted untouched.

## References

- [ADR-0059](0059-formatting-conventions-are-not-configurable.md), which this reverses in
  part.
- [ADR-0016](0016-ruff-replaces-black-isort-and-flake8.md), which set the default width.
- [ADR-0055](0055-generation-runs-no-shell.md): the format pass is a fixed argument list in
  the one Python task, as the lock is.
