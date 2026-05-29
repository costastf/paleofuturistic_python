# Generated project tree

An annotated tour of what copier creates. Tree is for a project named `example_project` with `git_hosting_service=github` and `integrate_dependency_track=true`. Differences for `gitlab` and DT-off variants are noted inline.

```
example_project/
├── .copier-answers.yml          Copier state — template URL + answers + revision
├── .gitignore
├── .pre-commit-config.yaml      Hooks: ruff, pylint, commitizen
├── .security-overrides          pip-audit allow-list (vuln id → expiry)
├── .github/                     GitHub Actions workflows (absent if gitlab)
│   └── workflows/
│       ├── build-deps-image.yaml
│       ├── continuous-integration.yaml
│       └── publish.yaml
├── .gitlab-ci.yml               (Only present if git_hosting_service=gitlab)
├── _CI/                         Portable CI tooling — vendored Invoke + tasks
│   ├── README.md                Tooling design doc
│   ├── bootstrap.py             First-run setup framework
│   ├── info.py                  Reader for [tool.docker-versions] in pyproject
│   ├── lib/
│   │   └── vendor/              Vendored Invoke + dependencies (committed)
│   └── tasks/
│       ├── __init__.py          Namespace aggregation + bootstrap wiring
│       ├── bootstrap.py         develop.bootstrap implementation
│       ├── build.py             uv build
│       ├── configuration.py     Shared constants (paths, env vars, settings)
│       ├── container.py         Deps container image; imports from <host>.py
│       ├── develop.py           pre-commit hook management
│       ├── document.py          properdocs build/view
│       ├── format_.py           ruff format + import sort
│       ├── github.py            (Only if git_hosting_service=github)
│       ├── gitlab.py            (Only if git_hosting_service=gitlab)
│       ├── lint.py              ruff/pylint/ty/complexipy/commitizen
│       ├── quality.py           pyscn
│       ├── release.py           Validate, bump, changelog, push, publish
│       ├── secure.py            pip-audit, SBOM, (optional) DT upload
│       ├── shared.py            @logged, @run, execute(), run_steps()
│       └── test.py              pytest + coverage
├── Dockerfile.deps              Multi-stage deps-cache image
├── LICENSE                      Selected at generation time
├── README.md
├── docs/                        Diátaxis-structured properdocs site
│   ├── index.md
│   ├── tutorials/
│   ├── how-to/
│   ├── reference/
│   └── explanation/
├── properdocs.yml               Docs config + mkdocstrings setup
├── pyproject.toml               Project + dependency groups + tool configs
├── src/
│   └── example_project/
│       ├── __init__.py          Re-exports + LOGGER setup
│       └── example_project.py   Main module with example hello() function
├── tests/
│   └── test_example_project.py  Smoke test for hello()
├── tox.ini                      Multi-Python test matrix
├── uv.lock                      Locked dependency graph
├── workflow.cmd                 Polyglot launcher (sh on Unix, cmd on Windows)
└── workflow.cmd.bat             Windows entrypoint
```

## File ownership

| Owner | Files |
| --- | --- |
| **You** | `src/`, `tests/`, `README.md`, `docs/` (after first edit), `.security-overrides` (curated list) |
| **The template** | `_CI/`, `pyproject.toml`'s framework sections, `Dockerfile.deps`, `workflow.cmd*`, CI workflow files |
| **Tooling** | `uv.lock` (managed by uv), `.copier-answers.yml` (managed by copier), `dist/` (build output) |

The template-owned files are the ones `copier update` will reach for. Customising them is fine but introduces merge work on every update.

## See also

- [Copier questions](copier-questions.md) — which answer creates which directories.
- [Generation internals](generation-internals.md) — what happens after the tree is laid down.
