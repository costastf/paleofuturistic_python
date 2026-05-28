# History and lineage

This template is a detached fork of [Straight to the Money 💰](https://github.com/Carlovo/straight_to_the_money). Both share the same north-star — "the Python development workflow your past self had always hoped for is finally here" — but the forks diverged on what "enterprise-ready" means in practice.

## What we inherited

From Straight to the Money:

- uv-first toolchain, ruff for formatting and linting.
- A practical walkthrough as the primary documentation surface (now split across [Tutorials](../tutorials/generate-your-first-project.md) and [How-to](../how-to/update-existing-project-with-cruft.md)).
- Cookiecutter + cruft as the delivery mechanism.
- A bias toward making the happy path short.

## What we changed

Paleofuturistic Python added the infrastructure that turns a starter into an enterprise scaffold:

- **Vendored CI tooling.** `_CI/lib/vendor/` ships Invoke and its deps; `./workflow.cmd` works on a fresh clone.
- **Multiple linters and analyzers.** ruff alone wasn't enough — pylint, ty, complexipy, and pyscn cover what ruff doesn't.
- **Security pipeline.** pip-audit, CycloneDX SBOM generation, optional Dependency Track upload.
- **Multi-host CI support.** Both GitHub Actions and GitLab CI scaffolding, gated on the `git_hosting_service` answer.
- **Conventional Commits + commitizen** for automated release notes, replacing Release Please. The version bump stays explicit; only the changelog is derived from commit messages.
- **pytest + tox + xdist** for the test layer, replacing the original `python -m unittest`.
- **Diátaxis-structured docs** (the structure you're reading right now), replacing the single-page walkthrough.

## What we kept identical

- **The license menu.** Apache-2.0 default, MIT/BSD-3/None as alternatives.
- **The python-version range model.** Min/max prompts, validated to share a major.
- **Headers prepended to every source file.** Dunder metadata + license boilerplate.

## What the name means

"Paleofuturistic" — past-meets-future. The template's job is to take the practices that should have been default in 2015 (uv-equivalents, opinionated formatting, supply-chain attestations) and ship them as the boring default for 2025+. The contradiction in the name is the point.

## Ownership

The template is maintained at [github.com/schubergphilis/paleofuturistic_python](https://github.com/schubergphilis/paleofuturistic_python). Issues and pull requests welcome.

## See also

- [Design principles](design-principles.md) — what we kept opinionated on purpose.
- [Why a cruft template?](why-a-cookiecutter.md) — why this delivery format.
