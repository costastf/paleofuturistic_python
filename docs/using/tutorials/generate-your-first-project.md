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
git init -b main
git add --all
git commit -m "chore: initial commit"
./workflow.cmd bootstrap
```

The bootstrap command installs uv-managed virtualenvs for every dependency group and registers pre-commit hooks (if you select yes, which we highly recommend).
The command is idempotent — running it again is a no-op until you pass `--force`.
We let you commit the scaffold before bootstrapping, because otherwise the pre-commit hook would validate the whole scaffold.
This is time consuming and not necessary, which you can validate by running `git status` after bootstrapping.

## Step 3 — Run the QA checks

These commands are the heartbeat of every project this template generates:

```bash
./workflow.cmd format    # format with Ruff (also sort imports, otherwise a normal ruff format)
./workflow.cmd lint      # lint with Ruff check, pylint, ty (type checker), complexipy, commitizen
./workflow.cmd test      # test with pytest (in parallel with xdist using the active Python interpreter)
./workflow.cmd quality   # scan code quality with pyscn
./workflow.cmd build     # produce a wheel + sdist in dist/ and export an SBOM
./workflow.cmd secure    # alert on vulnerable dependencies with pip-audit (also produce an SBOM and lint pip-audit security overrides)
```

You should see a passing test for the example `hello()` function and a wheel appear under `dist/`.
Some of the other QA tools also produce output you can look into later.

The really fast checks (ruff format/check, pylint, complexipy) which can run on only files git-staged are bundled in a one handy command: `./workflow.cmd develop.pre-commit`.
You are probably not surprised to hear these commands are already set to run before every commit with pre-commit.
With the pre-commit check (both CLI and hook) format will not edit your files as it does when you invoke it stand-alone.
Your commit message and SBOM security overrides are also checked before landing a commit.

Now run:

```bash
./workflow.cmd preflight --write
```

This is a more robust check on your project.
It will perform all checks above, except for the pip-audit from `secure`, because that is not related to code changes and does not give deterministic results.
(Today's green might be red tomorrow for pip-audit.)
If you want those checks as well, then add the flag `--audit-dependencies`.

The `--write` flag makes the command update the badges in the README.md based on the state of your project.
(The README is synched to your docs' index by default.)
A fresh project needs the `--write` on first run to set the badges to a correct value.
The default use is without that flag.
Then it will fail on stale badges.

Next to that, preflight runs pytest over all Python interpreters (with tox) and checks if the documentation renders correctly.
Preflight is also the command that executes before making a git push; more on that later.

## Step 4 — See the docs

Run the following command:

```bash
./workflow.cmd document
```

A browser tab opens with the generated project's documentation — its own Diátaxis-structured site, ready to extend.
The badges should reflect the state of your project if you just ran `preflight`.

## Step 5 — Commit using Conventional Commits

Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/) — the lint step rejects anything that doesn't parse.
Start each message with a type prefix:

```bash
git add -A
git commit -m "chore: bootstrap project"
```

Note the relevant checks from pre-commit running before the commit lands.
The prefixes drive the **release notes**: commitizen reads the commit history when generating the changelog and groups your commits by prefix (`feat:` under "Features", `fix:` under "Bug Fixes", etc.).
(The prefix does **not** drive the version bump — you'll choose that explicitly in a later step.)

## You're done

You have a fully scaffolded Python project with tests, linting, packaging, and docs all wired up.

**Next:** [From zero to a published package](from-zero-to-published-package.md).
