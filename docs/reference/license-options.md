# License options

The questionnaire's `license` answer picks one of four entries. Each maps to a file shipped to `LICENSE` and (for the three non-`None` choices) a `<license>.header` template that gets prepended to every source `.py`.

| Choice | SPDX ID | Header in source files? | Notes |
| --- | --- | --- | --- |
| `Apache-2.0` | `Apache-2.0` | Yes | Default. Permissive, includes explicit patent grant. |
| `MIT` | `MIT` | Yes | Permissive, minimal. |
| `BSD-3-Clause` | `BSD-3-Clause` | Yes | Permissive, includes attribution clause. |
| `None` | — | No | No `LICENSE` file, no header in source files. Useful for proprietary code or when you'll add a license later. |

## What the post-gen hook does with each

For non-`None` choices, `hooks/post_gen_project.py` performs three actions:

1. Copies `licenses/<choice>` to `LICENSE` in the project root.
2. Reads `licenses/<choice>.header`, interpolates `{year}` and `{author}` from the current date and `cookiecutter.full_name`, and stores the result.
3. Prepends the interpolated header (plus dunder metadata) to every `.py` under `src/` and `tests/`.

Then it deletes the `licenses/` directory regardless of choice.

For `None`, only the directory cleanup runs — source files get the `__license__ = 'None'` dunder but no copyright header line.

## Picking later

`License: None` at generation time, then deciding later:

1. Add a `LICENSE` file at the project root.
2. Set `pyproject.toml`'s `license = "<SPDX-ID>"` (or `license-file = "LICENSE"`).
3. Optionally prepend a header block to source files by hand.

This works but `cruft update` won't manage the headers for you — you're outside the template's automation for that file.

## PyPI classifiers

If you want PyPI to display a license badge, add the matching classifier to `pyproject.toml`'s `[project] classifiers` list. Recognized strings are listed at [pypi.org/classifiers/](https://pypi.org/classifiers/) — look under `License :: OSI Approved`.

The template doesn't auto-add classifiers because they're orthogonal to the license metadata field and not all licenses have a classifier.
