# Invoke task catalog

Every task callable via `./workflow.cmd <namespace>.<task>`. Tasks are defined in `_CI/tasks/<module>.py` and registered in `_CI/tasks/__init__.py`.

## Top-level shortcuts

The shortcuts below resolve to a namespace's default task (the one added with `default=True`).

| Task | Default of | What it does |
| --- | --- | --- |
| `bootstrap` | `develop.bootstrap` | First-run setup; idempotent. Pass `--force` to re-run. |
| `format` | `format.ruff` | Ruff format + import sort. |
| `lint` | `lint.all` | Runs ruff, pylint, ty, complexipy, commitizen. |
| `test` | `test.all` | pytest with coverage and xdist. |
| `build` | `build.package` | Security checks + `uv build`. |
| `release` | `release` | Validate, branch, bump, changelog, push, open PR/MR. |
| `quality` | `quality.pyscn-analyze` | pyscn static analysis with HTML report. |
| `secure` | `secure.all` | pip-audit + SBOM generate + (optional) DT upload. |
| `document` | `document` | properdocs build + view in browser. |
| `container` | `container.publish` | Build deps image; in CI pushes to the registry. |

## `develop` — local dev environment

| Task | Args | What it does |
| --- | --- | --- |
| `develop.bootstrap` | `--force` | Run all bootstrap steps. Idempotent. |
| `develop.pre-commit` | `--install` / `--uninstall` / `--update` | Manage pre-commit hooks. |

## `format`, `lint`, `test`, `quality`

| Task | What it does |
| --- | --- |
| `format.ruff` | `ruff check --select I --fix` + `ruff format`. |
| `lint.ruff` | `ruff check`. |
| `lint.pylint` | `pylint src/ _CI/tasks/ tests/`. |
| `lint.ty` | `ty check src/ _CI/tasks/ tests/`. |
| `lint.complexipy` | Cognitive complexity check on `src/`. |
| `lint.commitizen` | Validate commit messages since last tag. |
| `test.pytest` | pytest with coverage, xdist, HTML reports. |
| `test.coverage` | Print coverage report from the latest run. |
| `test.view` | Open HTML test + coverage reports in browser. |
| `quality.pyscn-analyze` | Full pyscn analysis with HTML report. |
| `quality.pyscn-check` | CI-friendly pass/fail quality gate. |

## `release` — versioning and publishing

| Task | Args | What it does |
| --- | --- | --- |
| `release` | `-i <type>`, `--no-push` | Full release flow: validate, branch, bump, changelog, push, open PR/MR. |
| `release.validate` | — | Working-tree-clean and in-sync-with-origin checks. |
| `release.bump` | `-i <type>` | `cz bump` with the given increment (major/minor/patch/alpha/beta/rc). |
| `release.changelog` | `--write` | Generate changelog. `--write` persists and commits. |
| `release.push` | — | `git push` + `git push --tags`. |
| `release.publish` | — | Build + `uv publish` + SBOM upload (if DT enabled). Invoked from CI on release-tag merge. |
| `release.clean` | — | Remove `dist/` and `sbom.json`. |
{%- if cookiecutter.integrate_dependency_track %}
| `release.sbom-upload` | — | Extract and upload SBOM to Dependency Track. |
{%- endif %}

## `secure` — pip-audit, SBOM, Dependency Track

| Task | Args | What it does |
| --- | --- | --- |
| `secure.audit` | — | pip-audit honoring `.security-overrides`. |
| `secure.sbom-extract` | `--write` | Compose a CycloneDX 1.6 SBOM (runtime deps + `_CI/lib/vendor.txt` + chosen-host pipeline components). Prints to stdout; with `--write` lands at `src/<slug>/sbom.cdx.json` so `uv build` ships it inside the wheel. |
| `secure.sbom-validate` | — | Validate the SBOM against the CycloneDX 1.6 JSON schema (runs the validator in a clean `uv run python` subprocess so the venv-installed `jsonschema` wins over the older vendored one). Re-runs sbom-extract first if the file is missing. |
{%- if cookiecutter.integrate_dependency_track %}
| `secure.sbom-upload` | — | Generate SBOM, write to `src/<slug>/sbom.cdx.json`, POST to Dependency Track. |
{%- endif %}

## `container` — OCI deps image

| Task | What it does |
| --- | --- |
| `container.build` | Build `{{ cookiecutter.project_slug }}-deps:latest` locally. |
| `container.publish` | In CI: push to the chosen host's registry. Locally: build only. |

## Shared helpers (not tasks)

Functions in `_CI/tasks/shared.py` (notably the `@logged` decorator, the `IndentingStream` plumbing, `execute`, `run_steps`) are used *by* tasks and not directly callable. See [The _CI tasks architecture](../explanation/the-ci-tasks-architecture.md).

Host-specific helpers live in `_CI/tasks/{{ cookiecutter.git_hosting_service }}.py` and are imported by `container.py` and `release.py` via a Jinja-substituted import.
