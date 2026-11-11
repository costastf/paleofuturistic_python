# ADR-0029: Suppressions come from three sources, and the two outside the repository must expire

- **Status**: accepted
- **Date**: 2026-04-22 (the file), 2026-08-03 (validation and required expiry)
- **Record written**: 2026-11-11 (backfilled)

## Context

A pipeline needs to suppress a finding without committing anything, and a person wants the
reverse: a suppression that is reviewed with the code and resurfaces on a date. A suppression
passed in from outside the repository with no expiry would mute a finding forever with no code
change to review. And a scanner that matched id-shaped substrings let a mistyped expiry such as
`CVE-1::2020-1-1` through as a permanent suppression with the date fragments tacked on as extra
ids.

## Decision

Three sources, merged in precedence order and deduplicated by id: `secure.audit --ignore`, the
`<PROJECT>_SECURITY_OVERRIDE` environment variable, and the `.security-overrides` file. Every
entry is `<VULN_ID>[::YYYY-MM-DD]`, matched whole, with the justification in a `#` comment.
Entries from the two sources that leave no trace in the repository must carry an expiry.
Expired entries are reported and ignored. Whatever is applied is printed with its origin, so a
suppression injected through CI configuration still shows in the build log. An expiry further
out than a year is remarked on but allowed. `secure.validate-overrides` checks the file's syntax
as a commit hook whenever it is staged.

## Consequences

- A permanent suppression has to be in the file, where it shows in a diff.
- The scheduled audit is what brings an expiry round with nobody pushing (ADR-0013).
- The template's own matrix forwards its `.security-overrides` and `TEMPLATE_SECURITY_OVERRIDE`
  through the same variable, so the plumbing is exercised.

## References

- Commits `0f5c4b1` (the file), `32f6ba8` (validation, required expiry off-repo).
- *Triage a security finding* in the generated-project developer docs.
