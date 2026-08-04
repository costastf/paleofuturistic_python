<!-- canonical: synced from docs/maintaining/explanation/the-ci-tasks-architecture.md in the paleofuturistic_python template repo. Edit there first. -->
# The _CI tasks architecture

The `_CI/` directory is this project's portable CI/CD framework — vendored [Invoke](https://www.pyinvoke.org/) plus a set of opinionated task modules. This page covers the design.

## Why Invoke, not make / just / nox

| Tool | Pro | Con (for this scaffold) |
| --- | --- | --- |
| `make` | Universal | Whitespace-sensitive, shell-quoted args, awkward Python integration |
| `just` | Modern, fast | Extra binary to install; not Python-native |
| `nox` | Python-native, env-isolating | Template integration is messy; nox needs to BE installed before it can install anything |
| **Invoke** | Python-native, no extra install (vendored), composable | Less well-known than Make |

The deciding factor was vendoring: a fresh clone runs `./workflow.cmd …` immediately, no `pip install invoke` step. Invoke + its deps live committed under `_CI/lib/vendor/`.

## The polyglot launcher

`workflow.cmd` is a single script that both sh and Windows cmd read as valid — three lines,
each doing different work depending on who is reading:

```sh
#!/bin/sh
: ; exec uv run python _CI/lib/vendor/bin/invoke --search-root _CI "$@"
@uv run python _CI\lib\vendor\bin\invoke --search-root _CI %*
```

The trick is line 2, and it hinges on `:` meaning two different things:

- **sh** treats `:` as the do-nothing builtin, runs the rest of the line, and `exec` replaces
  the shell process — so line 3 is never reached. The Windows line is dead code to sh.
- **cmd** treats a line starting with `:` as a *label*, so it skips line 2 entirely and falls
  through to line 3, which carries the backslash paths and `%*` that cmd needs.

Both routes end up running the same vendored Invoke, with `--search-root _CI` pointing it at
the task package. uv creates and syncs the virtualenv on the way through; the vendored Invoke
means there is nothing to install first. No global installs, and no second copy of the
launcher to keep in step.

## Module structure

```
_CI/tasks/
├── __init__.py          # Namespace aggregation + bootstrap pre-task wiring
├── bootstrap.py         # First-run setup framework
├── configuration.py     # Shared constants (paths, env vars, registry settings)
├── shared.py            # @logged, @run, execute, run_steps, IndentingStream
├── github.py / gitlab.py  # Host-specific helpers (only one is present)
├── local.py             # Yours. Never overwritten by `copier update`
└── <feature>.py         # build, container, develop, document, format_, lint,
                         #   quality, release, secure, test
```

Everything there except `local.py` is template-owned and replaced on update, which is why
project-specific tasks belong in `local.py` — `__init__.py` picks it up automatically.

Each feature module:

- Imports `Collection`, `task` from invoke.
- Defines its tasks with `@task` (and optionally `@logged`).
- Builds its `namespace = Collection('<name>')` at module bottom.
- `add_task(...)` registers each task; one is `default=True` for the bare-namespace shortcut.

`__init__.py` aggregates all module namespaces into one `namespace` that Invoke discovers.

## `@logged` and indented output

The `@logged` decorator wraps a task to print a clean status line:

```
    ✅ lint.ruff passed 👍
```

For tasks that call other tasks (a "workflow task" like `release` that calls `validate`, `bump`, `changelog`, `push`), nested output is indented under the parent banner via the `IndentingStream` class in `shared.py`. The indent is applied at the stdout/stderr layer, so even commands invoked through `context.run()` get their output indented.

This single design choice does a lot of heavy lifting — terminal output for `./workflow.cmd release` is hierarchical and scannable instead of a flat dump.

## Bootstrap as a pre-task

Every top-level task has `bootstrap_task` inserted as its first `pre`. This means the first run of *any* workflow command triggers the bootstrap; subsequent runs see the sentinel file (`_CI/.bootstrapped`) and skip.

Wired in `__init__.py`:

```python
bootstrap_task = bootstrap.bootstrap
for module in (build, container, develop, ...):
    for task in module.namespace.tasks.values():
        task.pre.insert(0, bootstrap_task)
```

This is why a fresh clone "just works" — `./workflow.cmd test` on day one is bootstrap-then-test; on day two it's just test.

## `run_steps`: fail-last, no short-circuiting

A workflow task that runs N steps (e.g. `lint` runs ruff + pylint + ty + complexipy + commitizen) doesn't short-circuit on the first failure. The `run_steps()` helper in `shared.py` runs every step, accumulates failures, and raises `SystemExit(1)` at the end with all the failures reported.

This makes CI runs informative — you see every issue per run instead of fixing one at a time.

## Host-specific code isolation

Whichever host was chosen at generation time — GitHub or GitLab — determines whether `_CI/tasks/github.py` or `_CI/tasks/gitlab.py` shipped in this project. Both expose the same contract:

- `registry_settings() -> RegistrySettings`
- `publish_deps_image(context, tag) -> str`
- `create_release_pr(context, branch, version) -> str`
- `pr_create_url(context, branch) -> str`

`container.py` and `release.py` import whichever module survived generation via a relative import that was rendered concrete at copy time. Because the unchosen module is omitted entirely at generation time via a copier conditional filename, this project has exactly one code path and no runtime branching between hosts.

## See also

- [Add a workflow task](../how-to/add-a-workflow-task.md) — practical recipe for extending the framework.
- [CI framework internals](../reference/ci-framework.md) — shared utilities, constants, and the directory layout.
