# Copier questions

Every question in `copier.yml`, what it does, and how it's validated. The template config file is `copier.yml` at the repo root; the tool you invoke is copier.

## User-facing questions

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

- **Type**: choice
- **Default**: `3.13`
- **Allowed**: `"3.13"`, `"3.14"`

Lower bound. Drives `requires-python`, classifier list, tox envs, and CI matrix. See [Choose the Python version range](../how-to/choose-python-version-range.md).

### `max_python_version`

- **Type**: choice
- **Default**: `3.14`
- **Allowed**: `"3.13"`, `"3.14"`

Upper bound. Must be `>= min_python_version` and share the same major version. A validator on this question in `copier.yml` enforces both constraints at generation time and aborts with a clear error if they are violated.

### `license`

- **Type**: choice
- **Default**: `Apache-2.0`
- **Allowed**: `Apache-2.0`, `MIT`, `BSD-3-Clause`, `None`

Selects which license file is installed to `LICENSE` and which header is prepended to source files by `tasks_render.py`. See [License options](license-options.md).

### `git_hosting_service`

- **Type**: choice
- **Default**: `github`
- **Allowed**: `github`, `gitlab`

Determines which CI scaffolding ships and which host-specific submodule lives at `_CI/tasks/<host>.py`. The unchosen host's files are omitted at generation time via copier conditional filenames — a file or directory whose rendered name is empty string is simply not created. See [Choose a git host](../how-to/choose-a-git-host.md).

### `integrate_dependency_track`

- **Type**: bool
- **Default**: `true`

When `true`, the release pipeline uploads the generated CycloneDX SBOM to an OWASP Dependency Track server (expects `OWASP_DT_*` environment variables at runtime). See [Enable Dependency Track integration](../how-to/enable-dependency-track.md).

### `integrate_pages`

- **Type**: bool
- **Default**: `true`

Controls whether documentation-publishing scaffolding (the Pages workflow file and the matching `document.deploy-github` task) ships in the generated project. The actual scaffolding is host-specific: today only `git_hosting_service=github` has shipping Pages scaffolding — picking `gitlab` with `integrate_pages=true` is a silent no-op until GitLab Pages support lands. See [Publish docs to GitHub Pages](../how-to/publish-docs-to-github-pages.md).

## Validation

Validation is split between copier's built-in mechanisms and the `tasks_render.py` copy-time script:

1. **Python version range** — a `validator` on the `max_python_version` question in `copier.yml` checks that `max >= min`, that both values share the same major version, and that both appear in the choices list. Any failure aborts generation immediately before any files are written.
2. **License installation** — `tasks_render.py` installs the chosen license file (substituting author/year tokens) and removes the `licenses/` staging directory. It runs only on `copier copy`, not on `copier update`.

## See also

- [Generation internals](generation-internals.md) — what runs after these answers are collected.
- [Generated project tree](generated-project-tree.md) — what each answer ends up shaping in the output.
