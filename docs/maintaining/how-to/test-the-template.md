# Test the template

The template ships four test entry points; pick the one that matches the level of confidence you need. All commands run **from this repo**, not from a generated project.

## The four entry points

| Command | Scope |
|---------|-------|
| `./workflow.cmd test.invariants` | Fast pytest layer — generates each matrix cell once and asserts structural invariants (no inner toolchain). Best signal-per-second. |
| `./workflow.cmd test` | Generate the template with default context and run the full inner QA cycle (`format`, `lint`, `test.tox`, `build`, `document`). |
| `./workflow.cmd test.combo --git-hosting-service <github\|gitlab> [--no-integrate-dependency-track] [--no-integrate-pages]` | Same as `test`, but for one explicit matrix cell. Use to reproduce a single CI failure locally. |
| `./workflow.cmd test.matrix` | Run every cell of the cartesian product; per-cell logs land in `reports/matrix/`. Defaults to sequential — CI parallelizes by fanning out across runners instead. |

## Choosing between them

- **While iterating**, run `test.invariants`. It finishes in a fraction of the time of a full cell and catches structural mistakes (missing conditional files, nav entries pointing nowhere, forbidden content shipping).
- **Before pushing**, run `test` once to prove the default-answers project passes its own QA cycle end to end.
- **When CI fails on one cell**, copy that cell's knobs into `test.combo` and reproduce it locally.
- **Before a release or a risky refactor**, run `test.matrix` and check `reports/matrix/` for per-cell logs.

## What CI runs

`.github/workflows/template-matrix.yaml` runs `test.invariants` plus a fanned-out `test.combo` per matrix cell on every push to `main` and every pull request. Each cell runs the generated project's full QA cycle, so the generated docs build (including nav/link integrity) is verified for every knob combination.

## Skipping a known CVE

The inner `build` step runs a security audit that can fail on a freshly published CVE unrelated to your change. To skip known CVEs during template testing:

```bash
TEMPLATE_SECURITY_OVERRIDE="CVE-2025-71176" ./workflow.cmd test
```

## Adding a new invariant

Structural assertions live in `tests/test_template_invariants.py`; each test receives one generated project per matrix cell via the `generated_project` fixture. Adding an assertion is one new `test_*` function. Adding a new combo axis means editing `matrix_combos()` in `_CI/tasks/configuration.py` — both the pytest suite and the Invoke matrix runner pick it up automatically.

## See also

- [Testing strategy](../../using/explanation/testing-strategy.md) — the test layers inside a *generated* project.
- [Make your first template change](../tutorials/make-your-first-template-change.md) — the edit-test loop, end to end.
