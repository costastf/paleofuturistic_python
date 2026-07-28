# Run tests for one Python version

`./workflow.cmd test` runs pytest against the active uv venv, which uses one Python version (the
`requires-python` floor by default). To exercise the full version range, pin to a specific minor, or
run a targeted subset, stay on the `./workflow.cmd` tasks below.

## All versions

```bash
./workflow.cmd test.tox
```

Runs every env declared in `pyproject.toml`'s `[tool.tox]` section, in parallel. The envs are
`py<major><minor>` (no dot) — one per version in your `min_python_version`..`max_python_version` range.

## A single Python version

```bash
./workflow.cmd test.tox --env=py310
```

Pass any single env name (`py310`, `py311`, …). Omit `--env` to run the whole matrix.

## A targeted subset (current venv)

Forward extra arguments to pytest with `--args`:

```bash
./workflow.cmd test.pytest --args="tests/test_specific_file.py"
./workflow.cmd test.pytest --args="-k sanity"
./workflow.cmd test.pytest --args="-m 'not slow'"
```

This uses whichever Python version uv resolved for the project, slicing by file, name, or marker.

> **Advanced — below the `./workflow.cmd` abstraction.** For tight interactive loops (e.g. `-x --pdb`,
> plugin flags) you can call the tools directly: `uv run pytest -k sanity`, `uv run tox -e py310`. This
> bypasses the task runner — you take responsibility for the environment and flags you pass. If you find
> yourself doing it often, model it as a task instead: see
> [Add a workflow task](add-a-workflow-task.md).

## In CI

The shipped CI matrix runs each Python version in parallel. To restrict locally what CI runs, edit the
`matrix` block in `.github/workflows/continuous-integration.yaml` or the `parallel:` block in
`.gitlab-ci.yml`.

## When you need a version uv hasn't fetched yet

```bash
uv python install 3.10
```

uv fetches and pins it; tox picks it up automatically on the next run.

## See also

- [Reference: invoke task catalog](../reference/invoke-tasks.md) — every `./workflow.cmd` task and its arguments.
- [Reference: configuration files](../reference/configuration-files.md) — where pytest, tox, and coverage settings live.
