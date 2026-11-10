# Packaging conformance

A generated project's metadata and distributions are checked against the
[PyPA packaging specifications](https://packaging.python.org/en/latest/specifications/) on every
push, not first discovered by PyPI during a release. This page explains which tools do the
checking, why those three, where each one runs, and what none of them can catch. The
spec-by-spec list is [Packaging specifications](../reference/packaging-specifications.md).

## Why check at all

`uv build` is permissive: it will build a wheel from a `pyproject.toml` that PyPI then refuses, or
worse, accepts and renders wrong. A README with broken markup shows as raw text on the project
page. A misspelt classifier is rejected at upload. A stray file at the wheel's top level installs
into every user's `site-packages`. Each of these is found today either at release time, when a
tag is already pushed and there is no cheap way back, or by a user. Checking the files the way an
index and an installer read them moves all of it to the push that introduced it.

## Three tools, three different files

Each tool reads a different artifact, so none of them overlaps with another.

| Tool | Reads | Catches | Runs in |
| --- | --- | --- | --- |
| [validate-pyproject](https://validate-pyproject.readthedocs.io/) | `pyproject.toml` | Fields the [pyproject.toml spec](https://packaging.python.org/en/latest/specifications/pyproject-toml/) does not define or types it does not allow, invalid PEP 508 requirements and PEP 440 versions, unknown trove classifiers, malformed SPDX expressions, `include-group` references to groups that do not exist, and `[tool.*]` tables it has schemas for. | `lint.pyproject`: the commit hook when `pyproject.toml` is staged, the `lint` aggregator, and `preflight`. |
| [twine check --strict](https://twine.readthedocs.io/en/stable/#twine-check) | The built wheel and sdist | Metadata PyPI's upload endpoint would reject, and a long description that does not render, which `--strict` turns from a warning into a failure. | `build.package`: inside `build`, `release.dist` and `preflight`. |
| [check-wheel-contents](https://github.com/jwodder/check-wheel-contents) | The built wheel | Bytecode, duplicate files, modules outside the package, an empty package, and files at the top level of `site-packages`. | `build.package`. |

validate-pyproject is a per-file step because whether `pyproject.toml` conforms is a question
about that file alone. The other two need a built wheel, and a wheel is built from the whole
tree, so they run on push with the rest of `build`.

## What they cannot catch

- **Whether the metadata is true.** A wrong description, a stale classifier, a URL pointing at
  the wrong repository: all valid, all published.
- **A `License ::` classifier beside a `license` expression.** The licence-expression spec says
  tools should refuse the combination, but `uv_build` builds it and none of the three flags it.
  Generated projects ship without one; adding one is a mistake no gate catches.
- **Whether PyPI already has this version.** Only the upload finds out. `uv publish --check-url`
  can skip files that already exist when re-running a partial upload.

## Why the version is not `dynamic`

`[project] dynamic` lets the build backend compute a field, typically the version from a git tag.
Generated projects do not use it: `./workflow.cmd release` has commitizen write the new version
into `pyproject.toml` and tag the commit, so the version in the file is the released one and
every field is static. Static metadata is what validate-pyproject, twine and anything else that
reads `pyproject.toml` without running a build can see.

## Where provenance fits

Conformance says the files are well-formed. It says nothing about who built them.
That is the job of the PEP 740 attestations signed at publish time; see
[SBOM and security model](sbom-and-security-model.md#layer-3-build-provenance).

## See also

- [Packaging specifications](../reference/packaging-specifications.md) — every spec, and how a generated project meets it.
- [How uv is used](how-uv-is-used.md) — the build backend and the lockfile.
