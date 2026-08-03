"""Tasks owned by this project, not by the template.

The template creates this file once and never touches it again — it is listed in the
template's ``_skip_if_exists``, so ``copier update`` will neither overwrite it nor raise a
conflict on it. Every other module in ``_CI/tasks/`` belongs to the template and *will* be
updated, so a task added there collides on every update. Add yours here instead.

Anything registered on ``namespace`` below shows up as ``./workflow.cmd local.<task>``, and
inherits the same bootstrap pre-task as the built-in namespaces.

A task looks like this::

    from typing import cast

    from invoke import Context, Task, task

    from .shared import execute, logged

    @task
    @logged('local.benchmark')
    def benchmark(context: Context) -> None:
        \"\"\"Run the project's benchmark suite.\"\"\"
        execute(context, 'uv run pytest benchmarks/ --benchmark-only')

    namespace.add_task(cast(Task, benchmark))

``@logged`` prints the pass/fail banner, and ``execute`` raises ``SystemExit(1)`` on a
non-zero exit so the task fails properly. See the *Add a workflow task* how-to for the
longer version, including how to give a namespace its own default task.
"""

from invoke import Collection

namespace = Collection('local')
