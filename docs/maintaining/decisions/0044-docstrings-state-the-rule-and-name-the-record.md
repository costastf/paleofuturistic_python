# ADR-0044: Docstrings state the rule and name the record

- **Status**: accepted
- **Date**: 2026-11-12

## Context

Before the decision log existed, the task modules were where the template's reasoning lived.
A docstring that explained a rule also told how the rule came about: the three passes it took
to find every writer of `reports/coverage.json`, the two narrower audits that saw less than
the lockfile, the retry logic that keyed on a traceback and would have gone inert the day
pip-audit printed a message instead. That was the right place while it was the only place.

With ADR-0001 to ADR-0043 written, the same stories stood in two places. A docstring ships
into every generated project and is read by a developer who wants to know what the task does
and why it refuses what it refuses; the evolution of the template is a maintainer's concern,
and the log holds it with dates and commits. Two copies also drift: the docstring's version of
a story is never updated when a record is.

## Decision

A docstring or a configuration comment states the current rule, and the reason for it where
the reason is not obvious from the code. Where the reason has a record, the docstring names
it as `ADR-NNNN` in one sentence and stops. The history, the alternatives that were tried and
what they got wrong, stays in the record.

Mechanism stays in the docstring. How `unpushed_range` searches its candidates, why
`coverage combine` is a union, what `apply_badge` returns and when: a reader of the code
needs those beside the code. What leaves is the narrative of how the mechanism was arrived
at.

The invariant suite already resolves every `ADR-NNNN` mentioned anywhere in the repository to
a file, so a docstring cannot name a record that does not exist.

## Consequences

- The longest docstrings lost their history paragraphs and gained a record number. The rule
  each one states did not change.
- A maintainer who wants the story follows the number; a developer who wants the rule reads
  the docstring and is not detained by the story.
- A future change that moves a rule updates the docstring's sentence and writes a record; it
  does not append a paragraph to the docstring.

## References

- [Decision records](index.md), whose introduction states the same division.
