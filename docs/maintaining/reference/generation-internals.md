# Generation internals

What happens between answering the questionnaire and receiving a finished project directory. The work that was previously a single `hooks/post_gen_project.py` script is now split three ways across copier's own mechanisms and a dedicated copy-time script.

## Stage 1. Answer validation (copier validators)

`validator` expressions in `copier.yml` run before any files are written. `project_slug` must be a valid Python identifier and PyPI name (lowercase letters, digits and inner underscores, starting with a letter); `repository_url` must be empty or an https URL with a path. The `max_python_version` validator checks:

- `max_python_version >= min_python_version`
- Both values share the same major version (no cross-major ranges).
- Both values appear in the choices list (currently `["3.11", "3.12", "3.13", "3.14", "3.15"]`).

Any failure aborts generation immediately with a clear error message. Because this runs before file output begins, there is no partial directory left on disk to clean up.

## Stage 2. Conditional filenames (copier rendering)

Copier skips any file or directory whose rendered name is an empty string. The template uses this mechanism to omit unchosen scaffolding at generation time — no post-generation deletion step needed.

Examples currently used:

| Template path | Condition | Effect |
| --- | --- | --- |
| `template/{% if git_hosting_service == 'github' %}.github{% endif %}/` | `git_hosting_service != 'github'` → name is `''` | Entire `.github/` tree absent for GitLab projects |
| `template/{% if git_hosting_service == 'gitlab' %}.gitlab-ci.yml{% endif %}` | `git_hosting_service != 'gitlab'` → name is `''` | `.gitlab-ci.yml` absent for GitHub projects |
| `template/_CI/tasks/{% if git_hosting_service == 'github' %}github.py{% endif %}.jinja` | `git_hosting_service != 'github'` → name is `''` | `_CI/tasks/github.py` absent for GitLab projects |
| `template/_CI/tasks/{% if git_hosting_service == 'gitlab' %}gitlab.py{% endif %}` | `git_hosting_service != 'gitlab'` → name is `''` | `_CI/tasks/gitlab.py` absent for GitHub projects |
| `template/{% if git_hosting_service == 'github' %}.github{% endif %}/workflows/{% if integrate_pages %}pages.yaml{% endif %}` | either condition false → name is `''` | Pages workflow absent when not GitHub or pages disabled |

The `from .{{ git_hosting_service }} import …` line in `_CI/tasks/container.py`, `release.py`, `document.py` and `sbom.py` is Jinja-substituted at copy time to name the surviving module — exactly one code path remains, no runtime branching.

## Stage 3. Copy-time script (`tasks_render.py`)

`tasks_render.py` at the repo root is run via copier's `_tasks` configuration. It is **gated to the copy operation only** — `copier update` does not re-run it, so re-generation side-effects (like stamping the copyright year) don't fire on every update.

It performs four actions, in order:

### Install the chosen license

- Copies `licenses/<chosen-license>` to `LICENSE` in the project root, interpolating `{year}` (current calendar year) and `{author}` (`full_name` answer). Skipped if the answer was `None`.
- Deletes the `licenses/` directory entirely.

No license header or dunder metadata is added to individual source files. The main module (`src/<slug>/<slug>.py`) ships its `import logging` + `LOGGER` setup directly from the template, so it needs no copy-time injection.

### Stamp the quarantine date

Sets `[tool.uv] exclude-newer` in the generated `pyproject.toml` to the generation date, so the new project's resolutions are frozen at the day it was made rather than inheriting the template's own boundary.

### Stamp the uv pin

Resolves the newest uv release that has cleared its cool-down and writes it to every pin in `pyproject.toml`, digest included. `TEMPLATE_UV_VERSION` forces a version (the matrix sets it to the template's own pin so generation is deterministic), and an unreachable PyPI falls back to that pin too.

### Make `workflow.cmd` executable

Sets the executable bit on `workflow.cmd`. On Windows the `.cmd` extension is sufficient; on Unix this step is what lets `./workflow.cmd …` work.

## Rendering model

Copier renders only files whose names end in `.jinja` (the suffix is stripped from the output filename). Every other file — vendored `_CI/lib/**`, binaries, static configs — is copied verbatim. Jinja delimiters are unchanged (`{{ }}` / `{% %}`); `{% raw %}` blocks protect GitHub Actions `${{ }}` expressions in rendered workflow files.

## See also

- [Copier questions](../../using/reference/copier-questions.md) — what feeds into generation.
- [Choose a git host](../../using/how-to/choose-a-git-host.md) — the prompt that drives the conditional filename logic.
