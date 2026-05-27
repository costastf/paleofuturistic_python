# The post-generation hook

`hooks/post_gen_project.py` runs once in the freshly-generated project's directory immediately after cookiecutter writes the templated files. It applies validations and edits that aren't expressible through Jinja alone.

## Sequence of actions

The hook executes in the order below. Any step that raises aborts the hook (and therefore the generation).

### 1. Validate Python version range

- Parse `min_python_version` and `max_python_version` into integer tuples.
- Fail if either is unparseable.
- Fail if `max < min`.
- Fail if either value isn't in `_known_python_versions`.
- Fail if they don't share the same major version.

### 2. Install the chosen license

- Copy `licenses/<chosen-license>` to `LICENSE` (unless the answer was `None`).
- Read `licenses/<chosen-license>.header` (if present) and format it with the current year + author.
- Delete the `licenses/` directory entirely.

### 3. Delete the unchosen git-host's artifacts

This is the host-isolation logic added with the `git_hosting_service` questionnaire variable:

| Chosen | Deleted |
| --- | --- |
| `github` | `.gitlab-ci.yml`, `_CI/tasks/gitlab.py` |
| `gitlab` | `.github/` (entire directory), `_CI/tasks/github.py` |

After this step the project contains only the chosen host's CI config and submodule. The `from .{{ cookiecutter.git_hosting_service }} import …` line in `_CI/tasks/container.py` and `_CI/tasks/release.py` was already Jinja-substituted at copy time to name the surviving module.

### 4. Prepend headers to source `.py` files

For each `.py` file under `src/` and `tests/`:

- Strip any pre-existing module docstring.
- Prepend the license header (year + author interpolated).
- Add `"""<project_slug>."""` as the module docstring.
- Add the dunder-metadata block (`__author__`, `__copyright__`, etc.).
- For the main module file (`src/<slug>/<slug>.py`) only: also prepend `import logging` and the `LOGGER` setup.

### 5. Make `workflow.cmd` executable

`chmod +x workflow.cmd` (and the equivalent on Windows). On Windows the `.cmd` extension is sufficient; on Unix this step is what lets `./workflow.cmd …` work.

## Why a hook instead of Jinja

Three things make a post-gen hook strictly necessary:

- **Whole-file deletion.** Jinja can produce an empty file, but it can't delete one. The host-artifact removal needs filesystem operations.
- **Path-aware logic.** Prepending headers to every `.py` under `src/` and `tests/` requires walking the tree; Jinja doesn't iterate filesystems.
- **Conditional `chmod`.** File permissions aren't part of the Jinja-rendered content.

## If validation fails

The hook prints a clear error and exits with status 1. **The partial output directory remains on disk** — cookiecutter doesn't roll back. Inspect or delete it before retrying.

## See also

- [Cruft questionnaire variables](cookiecutter-variables.md) — what feeds into the hook.
- [Choose a git host](../how-to/choose-a-git-host.md) — the prompt that drives step 3.
