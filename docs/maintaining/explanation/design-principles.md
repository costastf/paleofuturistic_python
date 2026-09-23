# Design principles

The template is opinionated. The choices below were made deliberately, not by accumulation — each replaces something an earlier revision relied on.

## Pipelines run template commands only

Every CI step is a `./workflow.cmd <task>` call — no inline `uv …`, `pip install …`, ad-hoc `properdocs …`, or other business logic in YAML. Behaviour changes happen in `_CI/tasks/`; workflow files are glue.

Two side-effects of this rule earn the rule a section of its own:

**Parity.** What CI runs is exactly what you can run locally. Debugging a failing CI step means running the same `./workflow.cmd` command on your laptop. No "but it worked on my machine" gap, no separate path to maintain.

**And those commands lean on tracked dependencies.** When a `properdocs` / `uv` / `pytest` invocation can do a CI step, we prefer it over a GitHub Action, because every Python dependency is pinned in `uv.lock` and surfaces in the project SBOM. Action dependencies are hidden inside `uses:` references and never appear in the supply-chain picture. Concretely: `properdocs gh-deploy` over `actions/upload-pages-artifact` + `actions/deploy-pages`; `./workflow.cmd test` over inline `pytest` invocations; and so on. Two scaffolding actions are unavoidable (`actions/checkout` to fetch the repo, `astral-sh/setup-uv` to bootstrap the toolchain itself when the deps image isn't used) — beyond that, prefer commands.

## The QA gate

The **QA gate** is not a command; it is the role a command plays. `preflight` with no flags is the gate: it
runs every check, compares every derived value against what the tools just measured, writes nothing,
and exits non-zero if anything is wrong or out of date. "The gate" is the short form used from here
on; the individual tools it runs — `format`, `lint`, `test`, `quality`, `build` — are the QA checks. That is what the pre-push hook runs and what
the CI pipeline runs, character for character. The commit hook runs the part of the same declaration
that can be judged from the files you staged.

Give `preflight` the `--write` flag and it stops being a gate: the same steps run, but the derived
files are updated instead of compared.

Eight rules hold this together, and they fall into two kinds. The first kind is about how the checks
run. The second is about who may write the values the checks later compare — which belongs here
because it is what makes comparing meaningful: a gate can only hold a badge to a measurement if
exactly one thing ever writes that badge, and only from a run that measured it.

### How the checks run

**One registry, three consumers.** `STEPS` in `_CI/tasks/preflight.py` declares every check once,
with its scope, its path filter and whether it writes. The commit hook, the pre-push hook and the CI
job read that declaration rather than keeping their own lists, so a check added there reaches all
three without editing three files — and two lists of checks can never disagree about what "green"
means.

**Scope decides the tier.** A check that answers correctly from the staged files alone runs on every
commit; one that needs the whole program runs on push. ty needs the callers of a changed signature,
pyscn needs every file to know what is dead or duplicated, the matrix needs the suite on every
interpreter, and a wheel builds from the whole tree or not at all. This is a rule about correctness
rather than speed: a whole-program check narrowed to a diff does not run faster, it answers wrongly.

**One run reports everything you must fix.** Steps keep running after one fails, and the run exits
non-zero at the end. A gate that stops at the first failure makes you re-run to discover the second,
and the steps are ordered cheapest-first so the verdict itself is early even when the run is not.

**The gate produces what the gate consumes.** Every report a gate run writes has a reader inside that
run — the coverage JSON the badge reads, the pyscn JSON the grade comes from. Nothing renders a
browsable HTML report that no hook and no pipeline opens; `test.coverage` and `quality.pyscn-analyze`
produce those on demand, for a human who asked.

### Who may write what the checks measure

**Verifying is the default; writing is a flag.** The bare command compares; `--write` updates. So the
gate needs no flag, and reproducing a pipeline failure means typing what you see in the log. The
general form is about names: a command named for an inspection may not modify the tree, and one named
for a mutation may — which is why `format` and `release.bump` write without being asked and nothing
else does.

**A derived value is written by whatever measured it.** The coverage badge is written by the command
that ran the matrix, the pyscn badge by the command that produced the grade, the version badge by the
command that bumps the version. No task refreshes a value it did not compute, because a value copied
from a report nobody just produced is a claim about a tree that may no longer exist.

**A name carries a scope.** `reports/coverage.json` means coverage across every interpreter in
`env_list`; `reports/coverage.py310.json` means one of them; `coverage.local.json` means whichever one
a bare `pytest` happened to use. Whatever writes one of those names has to be running at that scope,
because the readers cannot tell — the badge and the ratchet read a filename, not a provenance.

**Flags add; they never subtract.** The bare command is the narrow, read-only one: `--write` updates
derived files, `--audit-dependencies` adds a step. No flag makes a gate check less, a gate you can
quietly weaken being one that stops meaning anything. `env_list` in `pyproject.toml` is what shortens
the test matrix, and it shortens CI with it.

One consequence of the two kinds meeting: the derived-value steps are skipped once anything has
failed, in either mode. A badge computed from a tree that just failed its checks asserts something
untrue about it, so there is nothing for `--write` to write and nothing for the gate to compare.

Together these are what make one command mean the same thing in three places.

## uv is the only tool you install

Earlier revisions asked users to install Python, then `pipx`, then `tox`, then `pre-commit`, then `commitizen`. Today, every one of those is a uv-managed dependency group inside the generated project. You install uv; uv installs the rest.

**Tradeoff:** the template is now bound to uv's lifecycle. If uv goes away or changes lock format incompatibly, the template needs work. We accept that risk because uv has compressed the toolchain to a single binary that's fast enough to run on every commit.

## Why groups, not extras

The template used to put dev tools under `[project.optional-dependencies]` (PEP 621 extras). Those work but they conflate two ideas:

- **Optional features** of the library (e.g. an `excel` extra for openpyxl support).
- **Internal dev concerns** (lint, test, docs).

[PEP 735 dependency groups](https://peps.python.org/pep-0735/) — uv's first-class support for them — are explicitly for the second category. They never ship in the wheel and are never user-installable via `pip install <pkg>[<extra>]`. Cleaner contract, less to explain to users.

## Ruff replaces Black + isort + flake8 (and most of pylint)

One tool, one config block, one cache. Ruff doesn't yet cover everything pylint does — so pylint stays, but only for the checks Ruff doesn't have. We expect pylint's role to shrink as Ruff grows.

## ty replaces mypy

[ty](https://github.com/astral-sh/ty) is Astral's type checker, written in Rust. It's faster than mypy and shares the Ruff/uv codebase's quality bar. Mypy compatibility issues still surface occasionally; we accept that trade for the speed and consistency.

## pytest, not unittest

The original lineage used `python -m unittest`. We moved to pytest for fixtures, parametrization, coverage integration, and parallel execution via xdist. Unittest test classes still work — pytest discovers them.

## Conventional Commits drive the release notes

Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/) — the lint step rejects anything that doesn't parse. We use them for **automatic release notes**: [commitizen](https://commitizen-tools.github.io/commitizen/) reads the commits since the last tag and groups them by prefix (`feat:`, `fix:`, etc.) into a generated changelog.

We do **not** use commitizen's autorelease mode. The version bump is an explicit choice you make at release time: `./workflow.cmd release -i <major|minor|patch|…>`. Commit prefixes inform changelog structure, not the version number.

## properdocs (not vanilla mkdocs), with mkdocstrings for API docs

properdocs is mkdocs with a curated plugin set. mkdocstrings reads the source directly — no `.rst` files in the middle. Sphinx is more capable; we don't need that capability here.

## SBOMs ship inside the wheel

Every release composes a CycloneDX 1.7 SBOM covering four sources — runtime dependencies (from `uv export --no-dev` against the lockfile), dev / lint / test / docs / quality / security groups (the lockfile minus the runtime set), vendored CI tooling (every package in `_CI/lib/vendor.txt`), and the chosen host's pipeline components (GitHub Actions `uses:` refs or GitLab CI `image:` refs). Each component carries an SPDX-identified licence, a SHA-256 hash where the lockfile provides one, and an external_reference pointing at its upstream page. CycloneDX `scope` (`required` / `optional` / `excluded`) distinguishes what ships in the wheel from what builds it. A two-level dependency graph (project → runtime + dev + a synthetic `build-environment` → vendored + pipeline) makes "what's in the wheel" vs "what built the wheel" walkable from the root bom-ref.

The SBOM is validated against the CycloneDX 1.7 JSON schema and written to `src/<project_slug>/sbom.cdx.json`, which `uv build` automatically ships **inside the wheel** rather than next to it. A downstream consumer extracts it with `unzip -p <wheel> <project_slug>/sbom.cdx.json` or `importlib.resources` — the SBOM travels with the artefact instead of needing to be re-correlated post-release.

The cost is one Python module (`_CI/tasks/sbom.py`) and one extra build step; the benefit is that supply-chain questions have an answer the day someone asks them, without depending on a separate registry or pinned cyclonedx-cli binary.

## Vendored CI tooling

`_CI/lib/vendor/` ships Invoke + its dependencies committed to the repo. `./workflow.cmd` works on a fresh clone with only uv installed — no `pip install invoke` step, no version drift between contributor machines. The vendoring cost is bytes in the repo; the benefit is that the dev cycle is the same on day one as on day one thousand.

## Diátaxis for our own docs

The four sections — Tutorials, How-to, Reference, Explanation — exist because the template's documentation has historically conflated "I want to start" with "I want to understand", and readers got annoyed at both. Diátaxis splits the audiences. This page is in *Explanation* because it tells you *why*; it won't show you *how* to change anything.

## What we deliberately do not do

- **No framework choice.** This is a library scaffold. It does not know about FastAPI, Django, or Click. Add what you need.
- **No monorepo support.** One package, one repo. If you want a monorepo, use a different template.
- **No Python below the project's chosen `min_python_version` (as low as 3.10).** `tomllib` is imported via a 3.10-compatible fallback, so it's no longer a reason to require a higher floor.
- **No GitHub-only or GitLab-only assumptions in the dev cycle.** Host-specific code lives in `_CI/tasks/<host>.py`; the rest of the workflow runs identically.

## See also

- [Why copier?](why-copier.md) — why we picked the template format we did.
- [History and lineage](history-and-lineage.md) — what this template was forked from and why.
