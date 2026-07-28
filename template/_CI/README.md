# _CI — Workflow Tooling

A portable, vendored CI/CD framework built on [Invoke](https://www.pyinvoke.org/).
All dependencies ship in `lib/vendor/`, so `./workflow.cmd` works immediately after clone — no global installs required. Everything under `lib/vendor/` is vendored; don't hand-edit it.

All commands are invoked via `./workflow.cmd <namespace>.<task>`. Running a namespace without a task name executes its default.

The full documentation lives in the project docs (`./workflow.cmd document`), under the **Developer** section:

- [Invoke task catalog](../docs/developer/reference/invoke-tasks.md) — every task and its flags.
- [CI framework internals](../docs/developer/reference/ci-framework.md) — shared utilities, constants, bootstrap framework, directory layout.
- [The _CI tasks architecture](../docs/developer/explanation/the-ci-tasks-architecture.md) — the design rationale.
