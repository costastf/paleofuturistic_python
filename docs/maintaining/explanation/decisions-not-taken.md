# Decisions not taken

Things a reviewer has proposed more than once, that the template deliberately does not do. Each
entry says what would change the answer, so the question can be reopened with evidence rather
than re-argued from scratch.

## Fork pull requests run no pipeline

The gate workflow triggers on `push` only. A pull request from a fork therefore runs nothing:
no `preflight`, no dependency audit. The scheduled audit covers the dependencies after a merge,
and a maintainer pushing the branch runs the full gate.

**Why not.** Adding `pull_request` is one line, but it is a policy change rather than a
workflow fix — a fork's code would then execute the workflow file in this repository, and the
hardening advice that surrounds it (required status checks, restricted tokens, tag protection)
would need to be written for two trust levels instead of one. The current work is about the
generated project's own development loop, and that scope is full.

**What would change it.** A template user accepting external contributions. The fix and its
documentation belong together: `on: pull_request` plus `push: branches: [main]` so same-repo
pull requests do not run the matrix twice per push, and a rewrite of
[Harden the GitHub repository](../../using/how-to/harden-github-repository.md) to say which
checks can be required when some of them cannot run on a fork.

**Known consequence in the meantime.** That hardening page tells you to require status checks.
Requiring one that never reports on a fork's pull request hardens the repository into one that
cannot merge external contributions. The page warns about the path-filtered audit; the same
caveat applies to the gate itself.

## Commit-message linting looks only at what a push adds

`lint.commitizen` checks `@{upstream}..HEAD`, falling back to the remote's default branch and
then to the last commit.

**Why not all of history.** `cz check --rev-range HEAD` reads every reachable commit, so one
message that predates the convention fails every run from then on — a squashed import, history
from before the template was applied, a `--no-verify` from last year. The only way past it is
`SKIP=preflight`, which drops the entire gate, and the honest alternative is rewriting
published history. A push is answerable for the commits it adds; that is the range.

**Consequence to know.** A shallow clone resolves neither the tracking branch nor
`origin/HEAD`, so CI checks the tip commit's message alone. That is the tip it was handed, and
the hook has already seen the rest. The two are not checking an identical set, which is the one
place the "the pipeline runs the same command" property is narrower than it sounds.

## Badge URLs name the default branch

The build/pipeline badge URL contains `main` and the workflow filename, written once from
`git remote get-url origin`.

**Why not derive the branch.** The shipped workflows name `main` too — `branches: [main]`,
`?branch=main` — so a project on `master` has a pipeline to rename before it has a badge to
rename. Deriving one value while the other five stay literal buys nothing.

**What would change it.** Making the default branch a copier question, at which point every
literal follows from it and the badge is no different from the rest.

## The gate does not stop at the first failure

`run_scope` runs every step and exits once at the end, so about 90% of a *failing* run happens
after the verdict is known.

**Why not.** One run reports everything you have to fix. A gate that stops early makes you
re-run to discover the next problem, and the steps are ordered cheapest-first already, so a
formatting failure is reported in seconds even though the run continues. The derived-value
steps *are* skipped after a failure, because the reports they are computed from were never
produced.

**What would change it.** A measured complaint about wall-clock on a real project, not a
scaffold. The mechanism is already there — `run_scope` skips steps — so it is a policy change
of a few lines if the trade ever flips.

## pyscn's badge and pyscn's gate disagree

`preflight` runs `pyscn analyze --json` for the badge and `pyscn check` for the gate. The first
computes a lenient aggregate that can grade a module `A` while the second rejects it.

**Why not pick one.** Neither can do the other's job: `check` reports pass or fail and produces
no grade, `analyze` produces a grade and never fails. Both cost about 0.07s on a scaffold.

**What would change it.** pyscn growing a mode that fails *and* grades, or the divergence
confusing someone in practice — a README claiming `A` on a tree the gate rejects is defensible
but not obvious.

## See also

- [Design principles](design-principles.md) — the choices the template does make.
- [The CI tasks architecture](the-ci-tasks-architecture.md) — how the registry, the hooks and
  the pipeline relate.
