# Generate your first project

This tutorial walks you from an empty directory to a working Python project generated from this template, in about ten minutes. You will not customise anything — the goal is to see the whole cycle once.

## Prerequisites

You need [`uv`](https://docs.astral.sh/uv/) installed. uv is the only tool you need; it can run copier for you and will manage every other tool the generated project uses.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Step 1 — Generate the project

Pick an empty directory and run:

```bash
uvx copier copy --vcs-ref latest --trust https://github.com/schubergphilis/paleofuturistic_python <destination-dir>
```

`--trust` is required because the template runs a post-copy task.
`--vcs-ref` is optional, but for stability we recommend only using actual tagged and released versions of this template.

You will be asked a series of questions.
Press Enter to accept the defaults for every one — they're documented in [Copier questions](../reference/copier-questions.md).
Three answers worth thinking about:

- `project_name` — pick something memorable; everything else is derived.
- `git_hosting_service` — `github` (default) or `gitlab`; see [Choose a git host](../how-to/choose-a-git-host.md).
- `license` — defaults to Apache-2.0; pick whatever fits.

When the command finishes you'll have a complete Python project inside `<destination-dir>`.

## Step 2 — Bootstrap it

```bash
cd <your-project-slug>
./workflow.cmd bootstrap
```

This installs uv-managed virtualenvs for every dependency group and registers pre-commit hooks. It's idempotent — running it again is a no-op until you pass `--force`.

## Step 3 — Run the QA checks

These commands are the heartbeat of every project this template generates:

```bash
./workflow.cmd format    # Ruff format + import sort
./workflow.cmd lint      # Ruff check, pylint, ty (type checker), complexipy, commitizen
./workflow.cmd test      # pytest with coverage and parallel execution
./workflow.cmd quality   # pyscn code quality check
./workflow.cmd build     # Produce a wheel + sdist in dist/ (also runs pip-audit and exports SBOM)
```

You should see a passing test for the example `hello()` function and a wheel appear under `dist/`.
Some of the other QA tools also produce output you can look into later.

## Step 4 — See the docs

```bash
./workflow.cmd document
```

A browser tab opens with the generated project's documentation — its own Diátaxis-structured site, ready to extend.

## Step 5 — Commit using Conventional Commits

Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/) — the lint step rejects anything that doesn't parse.
Start each message with a type prefix:

```bash
git add -A
git commit -m "chore: bootstrap project"
```

The prefixes drive the **release notes**: commitizen reads the commit history when generating the changelog and groups your commits by prefix (`feat:` under "Features", `fix:` under "Bug Fixes", etc.).
(The prefix does **not** drive the version bump — you'll choose that explicitly in a later step.)

Now that you have git properly setup in your project you can execute the following command to perform all QA checks from step 3:

```bash
./workflow.cmd develop.pre-commit
```

This command also runs before any commit is made.

## You're done

You have a fully scaffolded Python project with tests, linting, packaging, and docs all wired up.

**Next:** [From zero to a published package](from-zero-to-published-package.md).
