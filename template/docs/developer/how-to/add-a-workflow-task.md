# Add a workflow task

The `./workflow.cmd <namespace>.<task>` interface is backed by Invoke.

## Put your tasks in `_CI/tasks/local.py`

**`_CI/tasks/local.py` is yours. Every other module under `_CI/tasks/` belongs to the template.**

That distinction matters on `copier update`: the template replaces the modules it owns, so a task added to `lint.py` — or a registration added to `__init__.py` — collides on every single update, forever. `local.py` is listed in the template's `_skip_if_exists`, so it is created once and then never overwritten or merged. Your tasks stay put and updates stay clean.

It ships with an empty namespace, ready to fill in:

```python
from typing import cast

from invoke import Collection, Context, Task, task

from .shared import execute, logged

namespace = Collection('local')


@task
@logged('local.benchmark')
def benchmark(context: Context) -> None:
    """Run the project's benchmark suite."""
    execute(context, 'uv run pytest benchmarks/ --benchmark-only')


namespace.add_task(cast(Task, benchmark))
```

That's the whole job — `./workflow.cmd local.benchmark` works immediately. There is no registration step: `_CI/tasks/__init__.py` picks `local.py` up if it is present, and wires the same bootstrap pre-task the built-in namespaces get, so a first invocation still bootstraps the environment.

The `@logged` decorator emits the pass/fail status line. The `execute` helper raises `SystemExit(1)` on non-zero exit; nested stdout is indented under the parent banner (the `IndentingStream` wiring in `_CI/tasks/shared.py`).

### Giving the namespace a default task

So `./workflow.cmd local` runs something on its own:

```python
namespace.add_task(cast(Task, benchmark), default=True, name='all')
```

### If you outgrow one file

Add more modules next to it and import them from `local.py`, which keeps everything hanging off the one file the template will not touch:

```python
# _CI/tasks/local.py
from .local_deploy import deploy

namespace.add_task(cast(Task, deploy))
```

Only `local.py` itself is protected from updates, but since the template never ships a
`local_deploy.py` there is nothing for it to collide with.

## Changing a task the template owns

Sometimes you genuinely need different behaviour from a built-in task rather than a new one. Wrap it from `local.py` instead of editing it in place:

```python
from .lint import ruff_lint


@task
@logged('local.lint-strict')
def lint_strict(context: Context) -> None:
    """Lint the extra paths this project cares about."""
    ruff_lint(context, paths='src/ tests/ scripts/')
```

If that isn't enough and you must edit a template-owned module, expect to resolve that hunk on every update — and consider whether the change belongs upstream in the template instead.

## Calling from another task

Modules compose via direct function calls — they don't reach into each other's Invoke internals:

```python
from .build import build as build_task

@task
def my_thing(context):
    build_task(context)   # plain call
    ...
```

## Conventions

- Your tasks live in `local.py`; the rest of `_CI/tasks/` is the template's.
- One module per concern. Lint covers all linters; security covers all security tools. Don't sprawl.
- Side effects via `execute(context, '...')` so failures abort the run cleanly.
- Don't catch `SystemExit` — let the `run_steps()` runner accumulate failures.
- Don't use leading underscores on module-level function names; the project's pylint config disallows it.

## See also

- [Generated project tree](../reference/ci-framework.md) — the full `_CI/` directory layout and shared utilities.
- [The _CI tasks architecture](../explanation/the-ci-tasks-architecture.md) — design rationale for the `@logged` + `IndentingStream` plumbing.
