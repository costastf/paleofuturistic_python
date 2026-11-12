<!-- canonical: rendered from docs/using/explanation/testing-strategy.md in the paleofuturistic_python template repo by `./workflow.cmd maintain.sync-docs`. Edit there, not here. -->
# Testing strategy

The template layers three things to test this project's code: pytest for the test runner, coverage for what got executed, and tox for the multi-version matrix. Each does one job.

## Layer 1 — pytest

Why pytest and not unittest:

- **Fixtures**. Sharable, composable test setup.
- **Parametrization**. One test, many input rows.
- **Markers**. `@pytest.mark.slow`, `@pytest.mark.integration`, sliced via `-m`.
- **Plugin ecosystem**. xdist (parallel), coverage, hypothesis, asyncio, ...

The template ships pytest + a small set of plugins (coverage, xdist, html, env, metadata). Discover the registered markers with `./workflow.cmd test.pytest --args="--markers"` after bootstrap.

## Layer 2 — Coverage

`pytest-cov` runs alongside pytest. The template tracks branch coverage (not just line coverage) and writes the JSON report the badge and the ratchet read to `reports/`. `./workflow.cmd test.coverage` renders the browsable HTML when you want it.

`pyproject.toml`'s `[tool.coverage.report]` has `fail_under` set, and `preflight --write` (or `test.tox --write`) **ratchets** this value upward after a green matrix run: if the run measured 87% and `fail_under` was 80%, it bumps `fail_under` to 87%. The bare `preflight`, the pre-push hook and CI only compare. Once engaged, the bar only goes up — lowering `fail_under` is a deliberate, reviewable change that shows up in the diff.

**What a raised bar looks like when it stops you.** The floor is a property of the tree, so
`preflight` fails a push whose coverage sits below it — including a push that only moved code
around, or one that added a module faster than its tests. The run names the number it measured
and the floor it missed. Two honest ways out: cover the new code, or lower `fail_under` in the
same commit, where a reviewer sees the bar move. Nothing in the workflow lowers it for you.

### Dormant during scaffold

The ratchet starts **dormant**. The smoke test (`def test_sanity` in `tests/test_<slug>.py`) drives the scaffolded project to 100% coverage on its very first run; if the ratchet engaged on that signal, the first real change would crash the build at a 100% floor. So the ratchet (run by `preflight` and `test.tox`) checks for the presence of `def test_sanity` and, while it's still there, prints a status line on every run explaining the dormant state and how to engage:

```
[ratchet] coverage=100% — scaffold still pristine (test_sanity present); ratchet dormant
[ratchet]   ratchet engages when you remove `test_sanity` in tests/test_<slug>.py
[ratchet]   to engage immediately, set [tool.test-ratchet] mode = "strict" in pyproject.toml
```

The moment `test_sanity` is deleted or renamed — i.e., the moment real tests start getting written — the ratchet engages and works exactly as described above. Once any non-zero `fail_under` is written, dormancy is over for good; re-adding `test_sanity` later doesn't reactivate it.

If the template is being seeded into a codebase that's already covered, set `[tool.test-ratchet] mode = "strict"` in `pyproject.toml` to bypass the dormancy check entirely.

Coverage regressions still can't slip in silently — they just can't slip in *or out* during the scaffold phase.

## Layer 3 — tox

tox + tox-uv runs the test suite against every Python version in the project's range. Configured in `pyproject.toml`'s `[tool.tox]`, generated from `min_python_version` / `max_python_version` at template-render time.

**Coverage across the matrix is a union, not an average.** Each env writes its own coverage data (`.coverage.<envname>`, consumed by the combine) and its own report (`reports/coverage.<envname>.json`); `test.tox` then runs `coverage combine` to produce the single `reports/coverage.json` the badge and the ratchet read. A line counts as covered if *any* interpreter executed it.

The [QA gate](design-principles.md#the-qa-gate) stops at that JSON:
`preflight` produces what it consumes and nothing else, so it
renders no browsable report — the same reason it asks pyscn for JSON only. `./workflow.cmd
test.coverage` renders the combined HTML from whatever the last run measured, and
`./workflow.cmd test.view` runs the tests and opens it.

A union is the only correct reading of a version matrix, and version-gated code shows why:

```python
if sys.version_info >= (3, 13):
    from warnings import deprecated
else:
    from typing_extensions import deprecated
```

Under py311 and py312 the `else` runs; under py313+ the `if` does. No single env covers both, so each reports a miss on code the matrix as a whole exercises completely, while the combined report counts both arms as covered. Averaging the percentages would understate code that is fully exercised.

The union does not tell you that a line reached only under py315 also works under py311. Coverage measures reach, not correctness; the tests check the latter on every interpreter.

One consequence: because the ratchet bumps `fail_under` against the union, trimming `env_list` later can genuinely lower measured coverage and fail the next run. That is the ratchet working, and lowering the bar is a deliberate, reviewable change as it is everywhere else.

`./workflow.cmd test` runs only one Python version (whichever the active uv venv resolved to). The full matrix runs in CI per shipped workflow, or locally via `./workflow.cmd test.tox` — see [Run tests for one Python version](../how-to/run-tests-for-one-python-version.md) for slicing it.

## What we don't ship

- **A testing pyramid.** The template doesn't pre-create unit/integration/e2e folders. The example smoke test lives directly in `tests/`. Structure tests as the project warrants.
- **Hypothesis or other property-based tooling.** Add it as a `test` group dep if wanted.
- **Mutation testing.** Mutmut or cosmic-ray. Add them as a `quality` group concern if a project reaches for them.
- **A "tests" service in `docker-compose`.** The deps cache image (`Dockerfile.deps`) is for CI deps, not for app testing.

## Smoke tests vs. real tests

The template generates one smoke test per project — a `tests/test_<slug>.py` that exercises the example `hello()` function with two functions: `test_sanity` (an `assert True` placeholder) and `test_integration` (the actual call). Keep them or delete them; either is fine, but `test_sanity` doubles as the [ratchet dormancy marker](#dormant-during-scaffold), so removing it engages the ratchet.

## Parallel execution

`pytest-xdist` runs tests across CPU cores by default (`-n 4` in the template's pytest config). Some tests don't play well with parallelism — anything touching the filesystem in a fixed location, or relying on shared global state.

For those, add `@pytest.mark.serial` and a corresponding `-m "not serial"` / `-m serial` two-pass setup. The template doesn't ship this scaffolding because most projects don't need it.

## Coverage of `_CI/`

The template treats `_CI/` as part of the codebase for linting purposes but **not** for test coverage. The CI tooling isn't reasonably unit-testable — its job is to glue together external commands. Coverage of `_CI/` is implicitly via the workflow tasks running successfully end-to-end on every commit.

## See also

- [Run tests for one Python version](../how-to/run-tests-for-one-python-version.md) — the practical commands for the version matrix.
- [Design principles](design-principles.md) — why the template uses dependency groups instead of extras.
