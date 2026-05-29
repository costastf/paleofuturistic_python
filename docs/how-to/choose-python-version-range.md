# Choose the Python version range

The questionnaire asks for `min_python_version` and `max_python_version`. They drive everything Python-version-related in the generated project.

## What they control

- **`requires-python`** in `pyproject.toml` is set to `>=<min>,<<next-major>`.
- **`tool.tox` envs** are generated for each minor version from `<min>` to `<max>` inclusive.
- **CI matrix** in `.github/workflows/` or `.gitlab-ci.yml` runs lint/test/build across the same range.
- **PyPI classifiers** (`Programming Language :: Python :: 3.X`) match the range.

## Constraints enforced at generation time

A `validator` on the `max_python_version` question in `copier.yml` checks:

1. Both values are in the choices list (currently `["3.13", "3.14"]`).
2. `max_python_version >= min_python_version`.
3. Both share the same major version — `3.x` to `4.x` ranges are not supported.

A violation aborts generation immediately with a clear error message. No partial output is left on disk.

## Widening the range later

To support additional minor versions after generation:

1. Update `pyproject.toml`'s `requires-python` and the classifier list.
2. Add a new `tox` env in `pyproject.toml`'s `[tool.tox]` section.
3. Add the new version to the CI matrix (the host-specific workflow file).
4. Run `./workflow.cmd test` against each version to catch incompatibilities.

For a cleaner re-derivation, `uvx copier update --trust` after the template's choices list expands will regenerate all four locations in lockstep — see [Update an existing project with copier](update-existing-project-with-copier.md).

## Picking a sensible minimum

The template's floor is 3.11+ for a reason: it relies on `tomllib`, `ExceptionGroup`, and PEP 604 type unions. Older floors would require shims; the template doesn't ship them.

If you need to support 3.10 or earlier for downstream consumers, generate at the template's minimum and patch the generated `pyproject.toml` manually — you're then off the template's update path for that file.

## See also

- [Design principles](../explanation/design-principles.md) — the reasoning behind the floor (see "What we deliberately do not do").
- [Copier questions](../reference/copier-questions.md#min_python_version) — the exact question definitions.
