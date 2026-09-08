# Skip a check, once

You are mid-thought and the commit hook will not let you save, or the push is blocked by
something you will fix in the next commit anyway. In the order to reach for them:

## Skip one hook by name

```bash
SKIP=staged git commit -m "wip: half a thought"
SKIP=preflight git push
```

`SKIP` is pre-commit's own variable and takes hook `id`s from `.pre-commit-config.yaml`; the
ones this template ships are `lint-commit`, `staged`, `preflight` and `security-overrides`. It
takes a list:

```bash
SKIP=staged,security-overrides git commit -m "…"
```

Every hook you did not name still runs, and pre-commit prints `Skipped` next to the one you
did, so the log records what you suspended.

## Fix it instead, if it is quick

The commit hook only ever complains about the files you staged, and formatting is one command:

```bash
./workflow.cmd format --paths="$(git diff --cached --name-only)"
git add -u
```

Scoped to what you staged, because `format` over the whole tree reformats files you never
looked at, and `git add -A` would then fold them into this commit.

For a blocked push, run the gate directly — it says everything that is wrong in one pass and
names the fix for each:

```bash
./workflow.cmd preflight
```

A stale badge, for instance, is `./workflow.cmd preflight --write` and a commit.

## `--no-verify`, and what it costs

```bash
git commit --no-verify -m "…"
git push --no-verify
```

This switches off *every* hook at that stage, including the commit-message check and, on push,
the entire gate — and nothing afterwards tells you what was skipped. `SKIP` with a list is
almost always what you wanted.

## What skipping does not do

CI runs `./workflow.cmd preflight` on every push — the same command the pre-push hook runs — so
a skipped check is deferred rather than avoided. You hear about it from the pipeline instead, a
few minutes later and in front of everyone on the pull request.

That is the design: the hooks tell you sooner, and they are not the only thing between a mistake
and the main branch, which is what makes it safe to skip one when you need to.
