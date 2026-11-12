# Extend the template workflow tasks

Change or add a `./workflow.cmd` task that generated projects ship with. This is the *maintainer* angle: you edit the template sources here so every future (and `copier update`-d) project gets the change. Project owners extending their own copy follow the *Add a workflow task* guide that ships inside every generated project's docs (Developer → How-to).

## Where the code lives

- `template/_CI/tasks/<module>.py` or `.py.jinja` — the task modules copied into generated projects. A file needs the `.jinja` suffix only if its content depends on copier answers.
- `_CI/tasks/` — this repo's *own* task modules (`configuration.py`, `document.py`, `lint.py`, `maintain.py`, `test.py`). They are a separate, smaller set: the template repo is not a generated project.

## Steps

1. **Edit the template module.** Follow the same conventions the generated framework documents for its own users: tasks wear `@task` + `@logged('<namespace>.<name>')`, side effects go through `execute(context, '...')`, registration happens in the module's `namespace = Collection(...)` block and, for new modules, in the `modules` list of `template/_CI/tasks/__init__.py`, whose loop wires bootstrap as a pre-task.

2. **Gate on knobs with jinja where needed.** Wrap host- or feature-specific code in the corresponding copier answer, following the existing patterns:

   ```text
   {%- if integrate_pages and git_hosting_service == 'github' %}
   ...task definition...
   {%- endif %}
   ```

   For entire host-specific modules, prefer copier's conditional filenames (see [Generation internals](../reference/generation-internals.md)) so the unchosen path never ships.

3. **Mirror in this repo's `_CI/` if applicable.** If the task is also useful for developing the template itself (as `document.py` is), port it — the two trees don't share code.

4. **Update the shipped task catalog.** `template/docs/developer/reference/invoke-tasks.md.jinja` lists every task a generated project exposes; add your task with the same knob-gating as the code.

5. **Add an invariant.** A conditional task should have a matching assertion under `tests/invariants/`, in the module for the subject it reads (see the existing `test_pages_task_definition_matches_choice` for the pattern: assert the `def` is present iff the knob is on).

6. **Verify:**

   ```bash
   ./workflow.cmd test.invariants
   ./workflow.cmd test
   ```

7. **Record the decision, if there was one.** A change that settles a question a future maintainer could reopen — why this tool, why this tier, why not the obvious alternative — gets a [decision record](../decisions/index.md). The docstring keeps one sentence stating the rule and names the record; the reasoning lives there.

## See also

- [The CI tasks architecture](../explanation/the-ci-tasks-architecture.md) — why the framework is shaped the way it is.
- [Test the template](test-the-template.md) — the full test pyramid.
