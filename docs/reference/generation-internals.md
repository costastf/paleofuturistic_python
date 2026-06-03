# Generation internals

What happens between answering the questionnaire and receiving a finished project directory. The work that was previously a single `hooks/post_gen_project.py` script is now split three ways across copier's own mechanisms and a dedicated copy-time script.

## 1. Python-version validation (copier validator)

A `validator` expression on the `max_python_version` question in `copier.yml` runs before any files are written. It checks:

- `max_python_version >= min_python_version`
- Both values share the same major version (no cross-major ranges).
- Both values appear in the choices list (currently `["3.13", "3.14"]`).

Any failure aborts generation immediately with a clear error message. Because this runs before file output begins, there is no partial directory left on disk to clean up.

## 2. Conditional filenames (copier rendering)

Copier skips any file or directory whose rendered name is an empty string. The template uses this mechanism to omit unchosen scaffolding at generation time — no post-generation deletion step needed.

Examples currently used:

| Template path | Condition | Effect |
| --- | --- | --- |
| `template/{% if git_hosting_service == 'github' %}.github{% endif %}/` | `git_hosting_service != 'github'` → name is `''` | Entire `.github/` tree absent for GitLab projects |
| `template/{% if git_hosting_service == 'gitlab' %}.gitlab-ci.yml{% endif %}` | `git_hosting_service != 'gitlab'` → name is `''` | `.gitlab-ci.yml` absent for GitHub projects |
| `template/_CI/tasks/{% if git_hosting_service == 'github' %}github.py{% endif %}.jinja` | `git_hosting_service != 'github'` → name is `''` | `_CI/tasks/github.py` absent for GitLab projects |
| `template/_CI/tasks/{% if git_hosting_service == 'gitlab' %}gitlab.py{% endif %}.jinja` | `git_hosting_service != 'gitlab'` → name is `''` | `_CI/tasks/gitlab.py` absent for GitHub projects |
| `template/{% if git_hosting_service == 'github' %}.github{% endif %}/workflows/{% if integrate_pages %}pages.yaml{% endif %}` | either condition false → name is `''` | Pages workflow absent when not GitHub or pages disabled |

The `from .{{ git_hosting_service }} import …` line in `_CI/tasks/container.py` and `_CI/tasks/release.py` is Jinja-substituted at copy time to name the surviving module — exactly one code path remains, no runtime branching.

## 3. Copy-time script (`tasks_render.py`)

`tasks_render.py` at the repo root is run via copier's `_tasks` configuration. It is **gated to the copy operation only** — `copier update` does not re-run it, so re-generation side-effects (like stamping the copyright year) don't fire on every update.

It performs three actions, in order:

### Install the chosen license

- Copies `licenses/<chosen-license>` to `LICENSE` in the project root (skipped if answer was `None`).
- Reads `licenses/<chosen-license>.header`, interpolates `{year}` (current calendar year) and `{author}` (`full_name` answer), and stores the result for the next step.
- Deletes the `licenses/` directory entirely.

### Prepend headers to source `.py` files

For each `.py` under `src/` and `tests/`:

- Prepends the SPDX license header (year + author interpolated).
- Adds `"""<project_slug>."""` as the module docstring.
- Adds the dunder-metadata block (`__author__`, `__copyright__`, etc.).
- For the main module file (`src/<slug>/<slug>.py`) only: also prepends `import logging` and the `LOGGER` setup.

For `license=None`, source files receive the `__license__ = 'None'` dunder but no copyright header line.

### Make `workflow.cmd` executable

Sets the executable bit on `workflow.cmd`. On Windows the `.cmd` extension is sufficient; on Unix this step is what lets `./workflow.cmd …` work.

## Rendering model

Copier renders only files whose names end in `.jinja` (the suffix is stripped from the output filename). Every other file — vendored `_CI/lib/**`, binaries, static configs — is copied verbatim. Jinja delimiters are unchanged (`{{ }}` / `{% %}`); `{% raw %}` blocks protect GitHub Actions `${{ }}` expressions in rendered workflow files.

## See also

- [Copier questions](copier-questions.md) — what feeds into generation.
- [Choose a git host](../how-to/choose-a-git-host.md) — the prompt that drives the conditional filename logic.
