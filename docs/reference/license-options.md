# License options

The questionnaire's `license` answer picks one of four entries. Each maps to a file shipped to `LICENSE`. No license header or metadata is added to individual source files.

| Choice | SPDX ID | Notes |
| --- | --- | --- |
| `Apache-2.0` | `Apache-2.0` | Default. Permissive, includes explicit patent grant. |
| `MIT` | `MIT` | Permissive, minimal. |
| `BSD-3-Clause` | `BSD-3-Clause` | Permissive, includes attribution clause. |
| `None` | — | No `LICENSE` file. Useful for proprietary code or when you'll add a license later. |

## What `tasks_render.py` does with each

For non-`None` choices, `tasks_render.py` at copy time:

1. Copies `licenses/<choice>` to `LICENSE` in the project root, interpolating `{year}` (current calendar year) and `{author}` from `full_name`.

Then it deletes the `licenses/` directory regardless of choice. For `None`, only the directory cleanup runs — no `LICENSE` file is written.

## Picking later

`License: None` at generation time, then deciding later:

1. Add a `LICENSE` file at the project root.
2. Set `pyproject.toml`'s `license = "<SPDX-ID>"` (or `license-file = "LICENSE"`).

## PyPI classifiers

If you want PyPI to display a license badge, add the matching classifier to `pyproject.toml`'s `[project] classifiers` list. Recognized strings are listed at [pypi.org/classifiers/](https://pypi.org/classifiers/) — look under `License :: OSI Approved`.

The template doesn't auto-add classifiers because they're orthogonal to the license metadata field and not all licenses have a classifier.
