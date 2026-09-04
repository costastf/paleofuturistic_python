<!-- canonical: synced from docs/using/explanation/testing-strategy.md in the paleofuturistic_python template repo. Edit there first. -->
# Testing strategy

The scaffold layers three things to test this project's code: pytest for the test runner, coverage for what got executed, and tox for the multi-version matrix. Each does one job.

## Layer 1 — pytest

Why pytest and not unittest:

- **Fixtures**. Sharable, composable test setup.
- **Parametrization**. One test, many input rows.
- **Markers**. `@pytest.mark.slow`, `@pytest.mark.integration`, sliced via `-m`.
- **Plugin ecosystem**. xdist (parallel), coverage, hypothesis, asyncio, ...

The scaffold ships pytest + a small set of plugins (coverage, xdist, html, env, metadata). Discover the registered markers with `./workflow.cmd test.pytest --args="--markers"` after bootstrap.

## Layer 2 — Coverage

`pytest-cov` runs alongside pytest. The scaffold tracks branch coverage (not just line coverage) and writes HTML + JSON reports under `reports/`.

`pyproject.toml`'s `[tool.coverage.report]` has `fail_under` set, and the test task **ratchets** this value upward after each green run: if the latest coverage run was 87% and `fail_under` was 80%, the task bumps `fail_under` to 87%. Once engaged, the bar only goes up — lowering `fail_under` is a deliberate, reviewable change that shows up in the diff.

### Dormant during scaffold

The ratchet starts **dormant**. The smoke test (`def test_sanity` in `tests/test_<slug>.py`) drives the scaffolded project to 100% coverage on its very first run; if the ratchet engaged on that signal, the first real change would crash the build at a 100% floor. So the test task checks for the presence of `def test_sanity` and, while it's still there, prints a status line on every run explaining the dormant state and how to engage:

```
[ratchet] coverage=100% — scaffold still pristine (test_sanity present); ratchet dormant
[ratchet]   ratchet engages when you remove `test_sanity` in tests/test_<slug>.py
[ratchet]   to engage immediately, set [tool.test-ratchet] mode = "strict" in pyproject.toml
```

The moment `test_sanity` is deleted or renamed — i.e., the moment real tests start getting written — the ratchet engages and works exactly as described above. Once any non-zero `fail_under` is written, dormancy is over for good; re-adding `test_sanity` later doesn't reactivate it.

If this scaffold was seeded into a codebase that's already covered, set `[tool.test-ratchet] mode = "strict"` in `pyproject.toml` to bypass the dormancy check entirely.

Coverage regressions still can't slip in silently — they just can't slip in *or out* during the scaffold phase.

## Layer 3 — tox

tox + tox-uv runs the test suite against every Python version in the project's range. Configured in `pyproject.toml`'s `[tool.tox]`, generated from the Python version range chosen at generation time.

**Coverage across the matrix is a union, not an average.** Each env writes its own coverage data (`.coverage.<envname>`, consumed by the combine) and its own reports (`reports/coverage.<envname>.json`, `reports/tests.<envname>.html`), and `test.tox` then runs `coverage combine` to produce the single `reports/coverage.json` that the badge and the ratchet read. A line counts as covered if *any* interpreter executed it.

The gate stops there, at the JSON: `preflight` produces what it consumes and nothing else, so
it renders no browsable report — the same reason it asks pyscn for JSON only. `./workflow.cmd
test.coverage` renders the combined HTML from whatever the last run measured, and
`./workflow.cmd test.view` runs the tests and opens it.

That is the only correct reading of a version matrix, and version-gated code shows why:

```python
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib
```

Under the oldest interpreter the `else` runs; under the newer ones the `if` does. No single env can cover both, so every env reports a miss on code the matrix as a whole exercises completely. On a scaffold with one such branch, each env reports 84.6% with one missing line and one missing branch, while the combined report is 100% with none — the union is the honest number, and averaging the percentages would just be 84.6% again for code that is fully exercised.

What the union does *not* tell you is that a line reached only under the newest interpreter also works under the oldest. Coverage never told you that — it measures reach, not correctness, and the tests check the latter on every interpreter.

One consequence worth knowing: because the ratchet bumps `fail_under` against the union, trimming `env_list` later can genuinely lower measured coverage and fail the next run. That is the ratchet working — coverage really did drop — and lowering the bar is a deliberate, reviewable change, as it is in every other case.

`./workflow.cmd test` runs only one Python version (whichever the active uv venv resolved to). The full matrix runs in CI per shipped workflow, or locally via `./workflow.cmd test.tox` — see [Run tests for one Python version](../how-to/run-tests-for-one-python-version.md) for slicing it.

## What we don't ship

- **A testing pyramid.** The scaffold doesn't pre-create unit/integration/e2e folders. The example smoke test lives directly in `tests/`. Structure tests how the project warrants.
- **Hypothesis or other property-based tooling.** Add it as a `test` group dep if wanted.
- **Mutation testing.** Mutmut or cosmic-ray. Add them as a `quality` group concern if the project reaches for them.
- **A "tests" service in `docker-compose`.** The deps cache image (`Dockerfile.deps`) is for CI deps, not for app testing.

## Smoke tests vs. real tests

The scaffold generated one smoke test — a `tests/test_<slug>.py` that exercises the example `hello()` function with two functions: `test_sanity` (an `assert True` placeholder) and `test_integration` (the actual call). Keep them or delete them; either is fine, but `test_sanity` doubles as the [ratchet dormancy marker](#dormant-during-scaffold), so removing it engages the ratchet.

## Parallel execution

`pytest-xdist` runs tests across CPU cores by default (`-n auto` in the pytest config). Some tests don't play well with parallelism — anything touching the filesystem in a fixed location, or relying on shared global state.

For those, add `@pytest.mark.serial` and a corresponding `-m "not serial"` / `-m serial` two-pass setup. The scaffold doesn't ship this scaffolding because most projects don't need it.

## Coverage of `_CI/`

The scaffold treats `_CI/` as part of the codebase for linting purposes but **not** for test coverage. The CI tooling isn't reasonably unit-testable — its job is to glue together external commands. Coverage of `_CI/` is implicit via the workflow tasks running successfully end-to-end on every commit.

## See also

- [Run tests for one Python version](../how-to/run-tests-for-one-python-version.md) — the practical commands for the version matrix.
- [Design principles](design-principles.md) — why the scaffold uses dependency groups instead of extras.
