# Packaging specifications

What a project generated from this template does about each specification on the
[PyPA specifications index](https://packaging.python.org/en/latest/specifications/), for anyone
deciding whether the template fits. Every generated project ships its own copy of this table,
written for that project's settings, under *Developer → Reference → Packaging specifications*.

"Gate" means a check that fails `./workflow.cmd preflight`, and so the pre-push hook and the
pipeline. The template's own test suite (`tests/test_packaging_specs.py`) builds a generated
project and checks its sdist and wheel against these specs on every template change.

## Summary

| Spec | Generated project | Where it is enforced | Knob dependence |
| --- | --- | --- | --- |
| [Names and normalization](https://packaging.python.org/en/latest/specifications/name-normalization/) | `project_slug` is a valid import name and project name | `project_slug` validator at generation | — |
| [Core metadata](https://packaging.python.org/en/latest/specifications/core-metadata/) | Metadata 2.4 from `[project]`, README as `text/markdown` | Gate: `twine check --strict` | — |
| [Version specifiers](https://packaging.python.org/en/latest/specifications/version-specifiers/) | PEP 440; commitizen `version_scheme = "pep440"` | Gate: validate-pyproject | — |
| [Dependency specifiers](https://packaging.python.org/en/latest/specifications/dependency-specifiers/) | PEP 508 everywhere | Gate: validate-pyproject | — |
| [pyproject.toml](https://packaging.python.org/en/latest/specifications/pyproject-toml/) | All metadata and tool config in one file, static (no `dynamic`) | Gate: validate-pyproject, per commit and per push | — |
| [Dependency groups](https://packaging.python.org/en/latest/specifications/dependency-groups/) | All tooling in groups; `dev` includes the rest | Gate: validate-pyproject (includes resolve) | — |
| [Inline script metadata](https://packaging.python.org/en/latest/specifications/inline-script-metadata/) | How-to for standalone scripts | — | — |
| [Well-known project URLs](https://packaging.python.org/en/latest/specifications/well-known-project-urls/) | `[project.urls]` with well-known labels | Template tests | `repository_url`; `Documentation` needs GitHub + Pages |
| [glob patterns](https://packaging.python.org/en/latest/specifications/glob-patterns/) | `license-files = ["LICENSE"]` | `uv build` fails on an unmatched pattern | absent when `license=None` |
| [License expression](https://packaging.python.org/en/latest/specifications/license-expression/) | SPDX `license`, no `License ::` classifier | Gate: validate-pyproject (syntax) | absent when `license=None` |
| [Source distribution format](https://packaging.python.org/en/latest/specifications/source-distribution-format/) | `uv build` sdist | Gate: `twine check --strict` | — |
| [Binary distribution format](https://packaging.python.org/en/latest/specifications/binary-distribution-format/) | `py3-none-any` wheel with `py.typed` | Gate: `check-wheel-contents`, `twine check --strict` | — |
| [Platform compatibility tags](https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/) | Pure Python | `uv_build` | — |
| [Entry points](https://packaging.python.org/en/latest/specifications/entry-points/) | None by default; how-to for scripts and plugins | Gate: validate-pyproject, once added | — |
| [Index hosted attestations](https://packaging.python.org/en/latest/specifications/index-hosted-attestations/) | PEP 740 attestation per file, uploaded via Trusted Publishing | `release.attest` in the publish job | both hosts; GitLab needs gitlab.com |
| [Simple repository API](https://packaging.python.org/en/latest/specifications/simple-repository-api/) | uv as client; how-to for private indexes | — | — |
| [.pypirc](https://packaging.python.org/en/latest/specifications/pypirc/) | Not used; gitignored | `.gitignore` | — |
| [File yanking](https://packaging.python.org/en/latest/specifications/file-yanking/) | How-to | PyPI | — |
| [Project status markers](https://packaging.python.org/en/latest/specifications/project-status-markers/) | How-to | PyPI | — |
| [Recording installed projects](https://packaging.python.org/en/latest/specifications/recording-installed-packages/) | Installer-side; uv | Template tests install the wheel and check `RECORD`, `INSTALLER` | — |
| [Direct URL data structure](https://packaging.python.org/en/latest/specifications/direct-url-data-structure/) | Installer-side; uv | Template tests check `direct_url.json` | — |
| [Virtual environments](https://packaging.python.org/en/latest/specifications/virtual-environments/) | uv-managed `.venv` | — | — |
| [Externally managed environments](https://packaging.python.org/en/latest/specifications/externally-managed-environments/) | Never installs into a system interpreter | — | — |
| [build-details.json](https://packaging.python.org/en/latest/specifications/build-details/) | Interpreter-side; nothing to do | — | — |
| [pylock.toml](https://packaging.python.org/en/latest/specifications/pylock-toml/) | `develop.pylock` exports `reports/pylock.toml` | — | — |
| [PyPA schemas](https://packaging.python.org/en/latest/specifications/schemas/) | Used through validate-pyproject | Gate: validate-pyproject | — |

## Known gap

A `License ::` classifier added next to the `license` expression passes every gate: the spec says
tools should refuse it, and `uv_build` does not. Generated projects ship without one.

## See also

- [Packaging conformance](../explanation/packaging-conformance.md) — why these three tools, and where each runs.
- [SBOM and security model](../explanation/sbom-and-security-model.md#layer-3-build-provenance) — the attestations.
- [Copier questions](copier-questions.md#repository_url) — `repository_url`.
