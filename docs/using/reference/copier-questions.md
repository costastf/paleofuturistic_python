# Copier questions

Every question in `copier.yml`, what it does, and how it's validated. The template config file is `copier.yml` at the repo root; the tool you invoke is copier.

## User-facing questions

### `project_name`

- **Type**: string
- **Default**: `Paleofuturistic Python Project`

Human-readable name. Appears as the README title and the docs `site_name`; `pyproject.toml`'s `name` is `project_slug`.

### `project_slug`

- **Type**: string (prompted, pre-filled with a derived default you can accept or edit)
- **Default**: `project_name` lowercased, with every run of non-identifier characters replaced by a single underscore and leading/trailing underscores stripped — e.g. `Username's Toolkit` → `username_s_toolkit`.

Python package name: both the `import` name / source-tree directory (`src/<slug>/`) and the `pyproject.toml` distribution name. It must therefore be a valid Python identifier **and** a valid [PyPI project name](https://packaging.python.org/en/latest/specifications/name-normalization/): lowercase ASCII letters, digits, and underscores, starting with a letter and ending with a letter or digit. A `validator` on this question enforces exactly that — it re-prompts (or, in non-interactive runs, aborts) on an empty value, a leading digit, or leftover punctuation such as an apostrophe.

Because PyPI [normalizes names](https://packaging.python.org/en/latest/specifications/name-normalization/) — lowercasing and collapsing runs of `.`, `-`, or `_` to a single `-` — the distribution name and the import name legitimately differ: `username_s_toolkit` is published and installed as `username-s-toolkit` (`pip install username-s-toolkit`) but imported as `import username_s_toolkit`.

### `project_description`

- **Type**: string
- **Default**: `Development flow as Paleofuturistic Python`

One-line summary. Lands in `pyproject.toml`'s `description` and the README lead paragraph.

### `full_name`

- **Type**: string
- **Default**: `John Doe`

Author name. Appears in `pyproject.toml` authors metadata and the chosen `LICENSE` file.

### `email`

- **Type**: string
- **Default**: `me@here.now`

Author email. Appears in `pyproject.toml` authors metadata.

### `min_python_version`

- **Type**: choice
- **Default**: `3.11`
- **Allowed**: `"3.11"`, `"3.12"`, `"3.13"`, `"3.14"`, `"3.15"`

Lower bound. Drives `requires-python`, classifier list, tox envs, and CI matrix. See [Choose the Python version range](../how-to/choose-python-version-range.md).

### `max_python_version`

- **Type**: choice
- **Default**: `3.15`
- **Allowed**: `"3.11"`, `"3.12"`, `"3.13"`, `"3.14"`, `"3.15"`

Upper bound. Must be `>= min_python_version` and share the same major version. A validator on this question in `copier.yml` enforces both constraints at generation time and aborts with a clear error if they are violated.

### `license`

- **Type**: choice
- **Default**: `Apache-2.0`
- **Allowed**: `Apache-2.0`, `MIT`, `BSD-3-Clause`, `None`

Selects which license file is installed to `LICENSE` by `tasks_render.py`. See [License options](license-options.md).

### `git_hosting_service`

- **Type**: choice
- **Default**: `github`
- **Allowed**: `github`, `gitlab`

Determines which CI scaffolding ships and which host-specific submodule lives at `_CI/tasks/<host>.py`. The unchosen host's files are omitted at generation time via copier conditional filenames — a file or directory whose rendered name is an empty string is simply not created. See [Choose a git host](../how-to/choose-a-git-host.md).

### `repository_url`

- **Type**: string
- **Default**: empty
- **Allowed**: empty, or an `https://` URL with a path, e.g. `https://github.com/acme/widget`

The public home of the repository. It renders `[project.urls]` in `pyproject.toml`, the links PyPI shows in the project sidebar, under [well-known labels](https://packaging.python.org/en/latest/specifications/well-known-project-urls/) so each gets its own icon:

| Label | Value |
| --- | --- |
| `Homepage` | The GitHub Pages site when `git_hosting_service=github`, the repository is on github.com and `integrate_pages=true`; otherwise the repository |
| `Source` | The repository |
| `Issues` | `<repository>/issues` on GitHub, `<repository>/-/issues` on GitLab |
| `Changelog` | `docs/reference/changelog.md` on the default branch, the page `release` updates |
| `Documentation` | The GitHub Pages site, under the same conditions as `Homepage` |

A trailing `/` or `.git` is dropped, so a pasted clone URL works. Left empty, the project ships no `[project.urls]` at all rather than links that would 404 on PyPI; answer it on a later `copier update`, or add the table by hand. Self-hosted GitLab and GitHub Enterprise URLs work too; only the Pages links assume github.com.

### `integrate_pages`

- **Type**: bool
- **Default**: `true`
- **Asked when**: `git_hosting_service=github`

Controls whether documentation-publishing scaffolding (the Pages workflow file and the matching `document.deploy-github` task) ships in the generated project. The scaffolding is GitHub-specific, so GitLab projects are not asked; the answer keeps its default there and nothing reads it. See [Publish docs to GitHub Pages](../how-to/publish-docs-to-github-pages.md).

## Validation

Validation is split between copier's built-in mechanisms and the `tasks_render.py` copy-time script:

1. **Python version range** — a `validator` on the `max_python_version` question in `copier.yml` checks that `max >= min`, that both values share the same major version, and that both appear in the choices list. Any failure aborts generation immediately before any files are written.
2. **Project slug** — a `validator` on the `project_slug` question checks the value is a valid Python identifier and PyPI project name (`^[a-z]([a-z0-9_]*[a-z0-9])?$`), rejecting empty values, leading digits, and punctuation such as apostrophes. Generation aborts before any files are written on failure.
3. **Repository URL** — a `validator` on `repository_url` accepts an empty value or `^https://[^/\s]+/[^\s]+$`, so `http://`, SSH remotes and a bare host are refused before any files are written.
4. **License installation** — `tasks_render.py` installs the chosen `LICENSE` file (substituting author/year tokens) and removes the `licenses/` staging directory. It runs only on `copier copy`, not on `copier update`.

## See also

- [Generation internals](../../maintaining/reference/generation-internals.md) — what runs after these answers are collected.
- [Generated project tree](generated-project-tree.md) — what each answer ends up shaping in the output.
