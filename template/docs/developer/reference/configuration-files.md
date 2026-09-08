# Configuration files

Every config file shipped at the project root, what it's for, and what NOT to edit.

## `pyproject.toml`

The single source of truth for project metadata and tool configuration. Sections worth knowing about:

| Section | Owner | Notes |
| --- | --- | --- |
| `[project]` | You | Name, description, classifiers, scripts, dependencies. Edit freely. |
| `[project.scripts]` | You | Console entry points. Add a `__main__.py` and an entry under this section to ship a CLI. |
| `[dependency-groups]` | You | Add deps via `uv add --group <name>`. See [Dependency groups](dependency-groups.md). |
| `[tool.uv]` | Template | uv-specific settings, required uv version. Don't lower `required-version`. |
| `[tool.ruff]` | Template (rule list), you (line-length etc.) | Rule selection is opinionated; ad-hoc disables go in code with `# noqa`. |
| `[tool.pylint]` | Template | Strict-by-default. Per-message disables go in code. |
| `[tool.pytest.ini_options]` | Template (framework), you (markers) | Don't disable coverage; add markers as needed. |
| `[tool.coverage]` | Template | `fail_under` is ratcheted upward automatically once the ratchet engages. Don't lower it. |
| `[tool.test-ratchet]` | Template (knob), you (mode) | `mode = "auto-detect"` (default) keeps the coverage ratchet dormant while the scaffolded `test_sanity` is in place; `mode = "strict"` engages it on run #1. See [Testing strategy](../explanation/testing-strategy.md#dormant-during-scaffold). |
| `[tool.tox]` | Template (framework), you (`env_list`) | Generated from `min_python_version` / `max_python_version`. Each env writes its own reports and coverage data, which `test.tox` then combines — see [Testing strategy](../explanation/testing-strategy.md#layer-3-tox). Trimming `env_list` shortens the gate locally *and* in CI, which is why it is the only supported way to make the matrix cheaper. |
| `[tool.commitizen]` | Template | Conventional-Commits parser config used by `cz changelog` and the lint hook. The template does **not** use commitizen's autorelease — the bump is chosen explicitly via `./workflow.cmd release -i <type>`. |
| `[tool.docker-versions]` | Template | The one image `Dockerfile.deps` builds on, pinned by tag *and* digest. |

## `uv.lock`

Locked dependency graph. Managed by uv; never edit by hand. Commit it.

## `tox.ini`

Empty placeholder. Tox config lives in `pyproject.toml`'s `[tool.tox]`. The file exists because some IDEs (and older `tox` versions) expect it.

## `.pre-commit-config.yaml`

Hook definitions, split across three git stages:

| Stage | Hooks | Scope | Cost on a fresh project |
|---|---|---|---|
| `commit-msg` | commitizen (conventional-commit format) | the message | ~2s |
| `pre-commit` | `preflight.staged` — ruff format, ruff, pylint, complexipy | **staged files only** | ~2.9s |
| `pre-commit` | `.security-overrides` validation | that file, when staged | ~1.5s |
| `pre-push` | `preflight` — ty, commitizen, the docs build, pyscn, the tox matrix, the wheel, derived files | whole project | ~19s |

**The commit stage is one hook, one invocation.** Four hooks would have pre-commit partition
the staged files and run them concurrently, so a commit would get four verdicts about four
subsets of itself. One hook is one verdict about one file list, in the order the registry
declares — cheapest first, so a formatting slip is not something you wait for pylint to hear
about.

Which tools run there is decided by the step registry in `_CI/tasks/preflight.py`, not by this
file, and the registry holds the per-tool path filters too (complexipy is `src/` only; the rest
also cover `_CI/tasks/` and `tests/`), so a commit touching only `tests/` skips complexipy. The
one `files:` here is the union of them, and an invariant asserts it is never narrower than the
widest step's filter.

The hook entry is the bare `./workflow.cmd preflight.staged`, with `pass_filenames: false`,
because the task reads the index itself — so the line is the command you would type. That also
means `files:` here decides whether the hook *wakes*, not what it looks at: stage a `.py` and
the task reads the whole index, applying each step's own filter from the registry. A staged path
containing a space is refused with an explanation, `--paths` being space-separated throughout.

**What runs on pre-commit is what can be judged from the staged files alone.** That is a rule
about correctness, not speed. ty, pyscn, the docs build, the test matrix and the wheel are whole-program: a
changed signature surfaces as an error in its *callers*, a function only looks dead once you
know nothing else calls it, a passing changed test says nothing about the ones it broke, and a
package builds from the whole tree or not at all.
Narrowing any of them to a diff does not make it faster, it makes it answer wrongly — and
their cost scales with the size of the *project* rather than of the change, which is what
would have made commits slower and slower as the project grew. They moved to pre-push, where
they run once per push and leave commit latency flat.

**No hook writes anything.** Unformatted code fails the commit and names
`./workflow.cmd format`. A hook that applied formatting itself would make the automated entry
points behave differently from the command a person types, and would rewrite the *worktree*
while git is mid-commit — which suits a partially staged file badly, the formatter rewriting the
whole file including hunks deliberately left out of the index.

**The pre-push hook runs `preflight` with no flag, and that is the load-bearing part.**
Verifying is the default; `preflight --write` updates the badges and ratchets `fail_under`, and
a hook that wrote would abort the push having modified files the author never staged — which is
what teaches people `--no-verify`, and that disables every hook here at once.

It is also the exact command the whole CI pipeline runs, so nothing in the pipeline can reject
what your push accepted, and reproducing a failure means typing what you see in the log. That
parity is why there is no flag to make it run *less*: `env_list` in `pyproject.toml` is what
shortens the matrix, and it shortens CI with it.

Every underlying task remains callable on its own, which is the escape hatch when you want one
tool: `./workflow.cmd lint.pylint --paths="src/thing.py"`. Need to push past the gate once? See
[Skip a check, once](../how-to/skip-a-check.md) — `SKIP=preflight git push` leaves the other
hooks in place, unlike `--no-verify`. Every variable this workflow reads is listed in
[Environment variables and flags](environment-and-flags.md).

Edit to add hooks; don't remove the existing ones without thinking — they keep the main
branch clean.

## `.security-overrides`

Allow-list for pip-audit findings. Each entry is a single token, `<VULN_ID>[::YYYY-MM-DD]`,
with the justification in a `#` comment — anything after the id on the same line is not
part of the entry. See [Triage a security finding](../how-to/triage-a-security-finding.md).

## `.gitignore`

Standard Python + the project's own outputs (`reports/`, `site/`, `dist/`, `.deps-image`, `_CI/.bootstrapped`).

## `Dockerfile.deps`

Multi-stage build for the dependency-cache image. Reads `[tool.docker-versions]` from `pyproject.toml`. See [Build and push a container](../how-to/build-and-push-a-container.md).

## `properdocs.yml`

Docs site config. Sections worth knowing:

- `nav:` — the navigation tree.
- `theme:` — `mkdocs` theme with auto color mode.
- `watch:` — `src/` is watched so docstring edits live-reload via mkdocstrings.
- `plugins:` — `include-markdown` (pulls README into `index.md`) and `mkdocstrings` (API reference from Google-style docstrings).

## `workflow.cmd` and `workflow.cmd.bat`

Polyglot launcher: a shell script on Unix, a batch file on Windows. Resolves to `uv run python -m _CI.invoke -- <args>`. Don't edit.

## `.github/` or `.gitlab-ci.yml`

The chosen host's CI config (only one of these exists per project, per the `git_hosting_service` answer). The checks live in a single `preflight` job running `./workflow.cmd preflight` — the same command the pre-push hook runs — so there is nothing to keep in step with a second list. Edit to add jobs; leave that one alone if you want `copier update` to keep working.

## `.copier-answers.yml`

Copier's state file. Records the template URL, the revision, and your answers. Managed by copier — never edit it manually. To pull template updates into this project run `uvx copier update --trust` from the project root — see the [copier docs](https://copier.readthedocs.io/en/stable/updating/).
