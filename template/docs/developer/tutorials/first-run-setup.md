# First-run setup

This is the first thing to do after this project was generated. By the end of it you'll have a green test run and a built wheel.

## You need

- [`uv`](https://docs.astral.sh/uv/) on your PATH.
- A shell. macOS/Linux: bash or zsh. Windows: PowerShell or git-bash.

You do *not* need to pre-install Python — uv will fetch the versions declared in `.python-version`.

## Step 1 — Bootstrap

> **Note:** bootstrap runs automatically as a `pre` task of every other command, so running it manually is optional — it's safe to skip straight to Step 2.

```bash
./workflow.cmd bootstrap
```

This:

1. Creates uv-managed virtualenvs for the `dev`, `lint`, `test`, `document`, `quality`, and `security` dependency groups (see [Reference: dependency groups](../reference/dependency-groups.md)).
2. Asks to install pre-commit hooks into `.git/hooks/`.
3. Drops a sentinel file (`_CI/.bootstrapped`) so re-runs are no-ops.

Re-running is safe and fast. Pass `--force` to repeat the setup.

## Step 2 — Format, then lint

```bash
./workflow.cmd format
./workflow.cmd lint
```

`format` runs `ruff format` and `ruff check --select I --fix` (import sort). `lint` runs ruff, pylint, ty (the type checker), complexipy, and commitizen. On a freshly-generated project all checks should be clean and pylint should rate the codebase 10.00/10.

## Step 3 — Test

```bash
./workflow.cmd test
```

This runs pytest with coverage and parallel execution via xdist. The default project ships one smoke test for the example `hello()` function — it should pass and report 100% coverage.

## Step 4 — Build

```bash
./workflow.cmd build
```

Produces a wheel and an sdist under `dist/`. You can `uv pip install dist/<your-package>-*.whl` into a throwaway venv to confirm it imports.

## Step 5 — Fill in the badges, once

```bash
./workflow.cmd preflight --write
```

`preflight` is the gate: formatting, the linters, the type checker, pyscn, the test matrix on
every interpreter in your range, the wheel, and the README badges against what those tools just
measured. The pre-push hook and the CI pipeline run it bare, where it compares and fails on
anything out of date.

`--write` is needed here because a generated README ships `coverage-unknown` and `pyscn-not
rated` — nothing has measured them yet, so the first bare run would fail on badges nobody could
have filled in. Commit the result and the bare command is the one you want from then on;
[Skip a check, once](../how-to/skip-a-check.md) covers what to do when it blocks you.

Run it once more after you add the remote:

```bash
git remote add origin <your-repository-url>
./workflow.cmd preflight --write
```

The build badge's URL is derived from `origin`, so until there is one it stays
`build-unknown`. Nothing fails over it — that badge is written and never checked, being a fact
about your clone rather than about the code — but it also will not fill itself in later.

## You're ready

You now have the loop you'll run hundreds of times: write code, `format`, and `preflight`
before you push. The individual commands above are there for when you want one tool's answer on
its own. Places to go next:

- **Make a real change** — write a function, then [Make your first release](make-your-first-release.md).
- **Add dependencies** — [Add a dependency](../how-to/add-a-dependency.md).
- **Document it** — [Document your project](../how-to/document-your-project.md) shows how to write docs for
  your software and get an API reference from your docstrings.
- **Understand what just happened** — [The scaffold](../index.md) tours the tooling
  (uv, the `_CI` task runner, testing, security) and links the template's docs for the full detail.
