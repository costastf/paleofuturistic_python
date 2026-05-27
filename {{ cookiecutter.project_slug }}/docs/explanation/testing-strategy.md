# Testing strategy

The template layers three things to test your code: pytest for the test runner, coverage for what got executed, and tox for the multi-version matrix. Each does one job.

## Layer 1 — pytest

Why pytest and not unittest:

- **Fixtures**. Sharable, composable test setup.
- **Parametrization**. One test, many input rows.
- **Markers**. `@pytest.mark.slow`, `@pytest.mark.integration`, sliced via `-m`.
- **Plugin ecosystem**. xdist (parallel), coverage, hypothesis, asyncio, ...

The template ships pytest + a small set of plugins (coverage, xdist, html, env, metadata). Discover with `pytest --markers` after bootstrap.

## Layer 2 — Coverage

`pytest-cov` runs alongside pytest. The template tracks branch coverage (not just line coverage) and writes HTML + JSON reports under `reports/`.

`pyproject.toml`'s `[tool.coverage.report]` has `fail_under` set, and the test task **ratchets** this value upward after each green run: if your latest coverage was 87% and `fail_under` was 80%, the task bumps `fail_under` to 87% and commits. The bar only goes up.

Lowering `fail_under` is a deliberate, reviewable change — it shows up in the diff. Coverage regressions can't slip in silently.

## Layer 3 — tox

tox + tox-uv runs the test suite against every Python version in the project's range. Configured in `pyproject.toml`'s `[tool.tox]`, generated from `min_python_version` / `max_python_version` at template-render time.

`./workflow.cmd test` runs only one Python version (whichever the active uv venv resolved to). The full matrix runs in CI per shipped workflow, or locally via `uv run tox`.

See [Run tests for one Python version](../how-to/run-tests-for-one-python-version.md) for the practical commands.

## What we don't ship

- **A testing pyramid.** The template doesn't pre-create unit/integration/e2e folders. The example smoke test lives directly in `tests/`. Structure your tests how your project warrants.
- **Hypothesis or other property-based tooling.** Add it as a `test` group dep if you want it.
- **Mutation testing.** Mutmut or cosmic-ray. Add them as a `quality` group concern if you reach for them.
- **A "tests" service in `docker-compose`.** The deps cache image (`Dockerfile.deps`) is for CI deps, not for app testing.

## Smoke tests vs. real tests

The template generates one smoke test per project — a single `test_hello.py` that exercises the example `hello()` function. Keep it or delete it; either is fine. The point is to have the test infrastructure proven before you write anything else.

## Parallel execution

`pytest-xdist` runs tests across CPU cores by default (`-n auto` in the template's pytest config). Some tests don't play well with parallelism — anything touching the filesystem in a fixed location, or relying on shared global state.

For those, add `@pytest.mark.serial` and a corresponding `-m "not serial"` / `-m serial` two-pass setup. The template doesn't ship this scaffolding because most projects don't need it.

## Coverage of `_CI/`

The template treats `_CI/` as part of your codebase for linting purposes but **not** for test coverage. The CI tooling isn't reasonably unit-testable — its job is to glue together external commands. Coverage of `_CI/` is implicitly via the workflow tasks running successfully end-to-end on every commit.

## See also

- [Run tests for one Python version](../how-to/run-tests-for-one-python-version.md) — the practical commands.
- [Dependency groups](../reference/dependency-groups.md) — what's in the `test` group.
