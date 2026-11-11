# Generated project tree

An annotated tour of what copier creates. Tree is for a project named `example_project` with `git_hosting_service=github` and `integrate_pages=true`. Differences for `gitlab` and Pages-off variants are noted inline.

```
example_project/
├── .copier-answers.yml          Copier state — template URL + answers + revision
├── .gitignore                   Includes .pypirc, dist/, reports/
├── .pre-commit-config.yaml      Hooks: lint-commit, staged, preflight (pre-push), security-overrides
├── .security-overrides          pip-audit allow-list (vuln id → expiry)
├── .github/                     GitHub Actions workflows (absent if gitlab)
│   └── workflows/
│       ├── build-deps-image.yaml
│       ├── continuous-integration.yaml
│       ├── pages.yaml           (Only if integrate_pages=true)
│       ├── publish.yaml
│       └── security-audit.yaml
├── .gitlab-ci.yml               (Only present if git_hosting_service=gitlab)
├── _CI/                         Portable CI tooling — vendored Invoke + tasks
│   ├── README.md                Tooling design doc
│   ├── info.py                  Stdlib-only reader of pyproject values for the deps image
│   ├── uv_release.py            Stdlib-only uv release resolver behind develop.bump-uv
│   ├── pyproject.toml           Ruff config for _CI/ and the vendored extra
│   ├── lib/
│   │   ├── patches/             The two hand-maintained edits to the vendored tree
│   │   ├── vendor.txt           Pinned vendored dependency list
│   │   └── vendor/              Vendored Invoke (committed)
│   └── tasks/
│       ├── __init__.py          Namespace aggregation + bootstrap wiring
│       ├── bootstrap.py         bootstrap task (first-run setup)
│       ├── build.py             uv build + twine check + check-wheel-contents
│       ├── configuration.py     Shared constants (paths, env vars, settings)
│       ├── container.py         Deps container image; imports from <host>.py
│       ├── develop.py           pre-commit hooks, uv pin, pylock export
│       ├── document.py          properdocs build/view
│       ├── format_.py           ruff format + import sort
│       ├── github.py            (Only if git_hosting_service=github)
│       ├── gitlab.py            (Only if git_hosting_service=gitlab)
│       ├── lint.py              ruff/validate-pyproject/pylint/ty/complexipy/commitizen
│       ├── local.py             Your own tasks; never overwritten by copier update
│       ├── preflight.py         Step registry; preflight + preflight.staged
│       ├── quality.py           pyscn
│       ├── release.py           Validate, bump, changelog, dist, attest, publish, detect, tag, ship
│       ├── sbom.py              CycloneDX SBOM composition
│       ├── secure.py            pip-audit, SBOM extract and validate
│       ├── shared.py            @logged, @run, execute(), run_steps(), apply_badge()
│       └── test.py              pytest + coverage
├── Dockerfile.deps              Single-stage deps-cache image
├── LICENSE                      Selected at generation time
├── README.md
├── docs/                        Diátaxis-structured properdocs site
│   ├── index.md
│   ├── tutorials/
│   ├── how-to/
│   ├── reference/
│   ├── explanation/
│   └── developer/               The scaffold's own manual, incl. packaging specs, Trusted Publishing, attestations
├── properdocs.yml               Docs config + mkdocstrings setup
├── pyproject.toml               Project (+ [project.urls] if repository_url) + dependency groups + tool configs
├── reports/                     Generated reports, gitignored (coverage, pyscn, pylock.toml)
├── src/
│   └── example_project/
│       ├── __init__.py          Re-exports + LOGGER setup
│       └── example_project.py   Main module with example hello() function
├── tests/
│   └── test_example_project.py  Smoke test for hello()
├── uv.lock                      Locked dependency graph
└── workflow.cmd                 Polyglot launcher (sh on Unix, cmd on Windows)
```

## File ownership

| Owner | Files |
| --- | --- |
| **You** | `src/`, `tests/`, `README.md`, `docs/` (after first edit), `.security-overrides` (curated list) |
| **The template** | `_CI/`, `pyproject.toml`'s framework sections, `Dockerfile.deps`, `workflow.cmd`, CI workflow files |
| **Tooling** | `uv.lock` (managed by uv), `.copier-answers.yml` (managed by copier), `dist/` (build output) |

The template-owned files are the ones `copier update` will reach for. Customising them is fine but introduces merge work on every update.

## See also

- [Copier questions](copier-questions.md) — which answer creates which directories.
- [Generation internals](../../maintaining/reference/generation-internals.md) — what happens after the tree is laid down.
