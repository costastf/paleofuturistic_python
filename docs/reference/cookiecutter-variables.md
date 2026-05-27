# Cruft questionnaire variables

Every variable in `cookiecutter.json`, what it does, and how it's validated. The filename is `cookiecutter.json` because cruft uses cookiecutter under the hood; the tool you invoke is cruft.

## User-facing variables

### `project_name`

- **Type**: string
- **Default**: `Paleofuturistic Python Project`

Human-readable name. Appears in `pyproject.toml`'s `name` field, the README title, the docs `site_name`, and source-file headers.

### `project_slug`

- **Type**: derived
- **Default**: `project_name` lowercased with spaces and hyphens replaced by underscores.

Python package name and source-tree directory name. Must be a valid Python identifier — the lowercase/replace transformation guarantees that for typical inputs.

### `project_description`

- **Type**: string
- **Default**: `Development flow as Paleofuturistic Python`

One-line summary. Lands in `pyproject.toml`'s `description` and the README lead paragraph.

### `full_name`

- **Type**: string
- **Default**: `John Doe`

Author name. Appears in `pyproject.toml` authors metadata, the chosen `LICENSE` file, and the `__author__` header of every source `.py`.

### `email`

- **Type**: string
- **Default**: `me@here.now`

Author email. Same locations as `full_name`.

### `min_python_version`

- **Type**: choice from `_known_python_versions`
- **Default**: `3.13`

Lower bound. Drives `requires-python`, classifier list, tox envs, and CI matrix. See [Choose the Python version range](../how-to/choose-python-version-range.md).

### `max_python_version`

- **Type**: choice from `_known_python_versions`
- **Default**: `3.14`

Upper bound. Must be `>= min_python_version` and share the same major version.

### `license`

- **Type**: choice
- **Default**: `Apache-2.0`
- **Allowed**: `Apache-2.0`, `MIT`, `BSD-3-Clause`, `None`

Selects which license file is copied to `LICENSE` and which header is prepended to source files. See [License options](license-options.md).

### `git_hosting_service`

- **Type**: choice
- **Default**: `github`
- **Allowed**: `github`, `gitlab`

Determines which CI scaffolding ships and which host-specific submodule lives at `_CI/tasks/<host>.py`. The unchosen host's artifacts are deleted at generation time. See [Choose a git host](../how-to/choose-a-git-host.md).

### `integrate_dependency_track`

- **Type**: bool
- **Default**: `true`

When `true`, the release pipeline uploads the generated CycloneDX SBOM to an OWASP Dependency Track server (expects `OWASP_DT_*` environment variables at runtime). See [Enable Dependency Track integration](../how-to/enable-dependency-track.md).

## Private variables

Keys starting with `_` aren't prompted for. They configure the template engine itself.

### `_known_python_versions`

The list of valid choices for `min_python_version` and `max_python_version`. Update this list when the template gains support for a new minor version.

### `_copy_without_render`

Glob list of paths copied verbatim (no Jinja expansion). Currently scoped to the vendored `_CI/lib/` directory.

## Validation

`hooks/post_gen_project.py` enforces, in order:

1. Both Python versions are dotted integers parseable by `version_tuple()`.
2. `max_python_version >= min_python_version`.
3. Both Python values appear in `_known_python_versions`.
4. Both share the same major version (no cross-major ranges).
5. The selected license file exists in `licenses/`.

Any failure aborts generation; cruft does not roll back partial output, so check the partial directory for context before retrying.

## See also

- [The post-generation hook](post-gen-hook.md) — what runs after these answers are collected.
- [Generated project tree](generated-project-tree.md) — what each answer ends up shaping in the output.
