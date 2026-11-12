# ADR-0045: One home per rationale

- **Status**: accepted
- **Date**: 2026-11-12

## Context

The same reasoning was written out in full in more than one place. Why the audit does not run
on every push stood in the shipped security explanation, in the triage how-to, in the audit
workflow's header and in the GitLab pipeline's job comment. Why there is one gate job rather
than lint, test and build jobs stood in the design principles, in the CI workflow's header and
in the GitLab pipeline. "Flags add, they never subtract" stood in the design principles and in
the flags reference. The one-registry rule stood in the design principles and in the task
catalog. Each copy was a paragraph, and each paragraph aged on its own: the shipped security
page still said a fork's pull request triggered no audit three commits after ADR-0041 made
it trigger one, because the parent copy had been updated and the shipped copy had not.

A word-shingle comparison of every paragraph in the parent and shipped docs found these and
little else; the remaining overlaps were the intentional shipped copies (ADR-0007), the decision
records against the pages that synthesise them, and see-also lists.

## Decision

Each rationale has one home, and it is the explanation page for its subject: the design
principles for the gate and its flags, the security model for the audit's timing, the
dependency-groups reference for the resolution boundary. Every other place that mentions the
rule, whether a reference page, a how-to, a workflow header or a configuration comment, states
the rule in a sentence and points at the home: a link in a page, a path and heading in a
comment.

The home has to be a page that ships with the generated project when the pointer does. A
workflow comment in a generated project cannot point at a decision record, since the records
do not ship, so it points at the shipped explanation page, which links to the record.

Tutorials are exempt. A tutorial restating a rule in the sentence where the reader meets it is
teaching, not a second home, and the two tutorials that say what Conventional Commit prefixes
drive are left alone.

## Consequences

- Four workflow and pipeline headers, one `pyproject.toml` comment, one reference page, one
  how-to and the task catalog each lost a paragraph and gained a pointer.
- A rule that changes is changed in one page. The pointers do not age, because they say only
  that the rule exists and where it is explained.
- The stale fork sentence in the shipped security page is fixed, and it was the kind of drift
  the heading-subset invariant between the parent and shipped copies cannot see. A task that
  syncs the shipped rationale pages from the parent is the next decision in this area.

## References

- [ADR-0044](0044-docstrings-state-the-rule-and-name-the-record.md), the same division for
  docstrings.
- [ADR-0007](0007-diataxis-with-shipped-rationale-pages.md), for the copies that are meant to
  exist.
