# ADR-0015: `local.py` is the project's module

- **Status**: accepted
- **Date**: 2026-08-03
- **Record written**: 2026-11-11 (backfilled)

## Context

Copier ownership is per file (ADR-0001). Every module under `_CI/tasks/` is template-owned and
replaced on `copier update`, so a task a project added to `lint.py`, or a registration it added
to `__init__.py`, collided on every update, forever. Projects needed somewhere to put their own
tasks that the template would never reach for.

## Decision

The template seeds `_CI/tasks/local.py` once, with an empty `local` namespace and a worked
example in its docstring, and lists it in `_skip_if_exists` so that `copier update` neither
overwrites it nor raises a conflict on it. `__init__.py` imports it when the file exists, adds
its namespace, and gives it the same bootstrap pre-task the built-in namespaces get, so there is
no registration step. A missing file is skipped as a deliberate deletion; an error inside it
propagates, because silently dropping someone's tasks is worse than a traceback.

## Consequences

- Project tasks survive every update; `./workflow.cmd local.<task>` works as soon as the task is
  written.
- Changing a template task is done by wrapping it from `local.py`, not by editing it in place.
- Only `local.py` itself is protected. Extra modules imported from it are unprotected but never
  collide, since the template ships no file of those names.

## References

- Commit `8d7ec2c`, "give projects a task module the template never overwrites".
- *Add a workflow task* in the generated-project developer docs,
  [Extend the template workflow tasks](../how-to/extend-the-template-tasks.md).
