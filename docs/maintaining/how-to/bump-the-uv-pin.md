# Bump the uv pin

The uv version the template ships reaches **ten** values, which is why this is a command rather
than an editing chore:

| Value | File |
|---|---|
| `[tool.uv] required-version` | `template/pyproject.toml.jinja` |
| `uv==` in the `test` group | `template/pyproject.toml.jinja` |
| `uv_build` upper bound | `template/pyproject.toml.jinja` |
| `base-image` tag | `template/pyproject.toml.jinja` |
| one image digest per supported Python (5) | `template/pyproject.toml.jinja` |
| `[tool.uv] required-version` | `pyproject.toml` (this repo) |

```bash
./workflow.cmd maintain.bump-uv
```

It resolves the newest release that has been public for at least 7 days, checks that `uv-build`
published the same version, re-fetches a digest for **every** Python version in `copier.yml`'s
choices, and writes all ten together. Nothing is written unless every substitution succeeds, so
a failure leaves the tree clean rather than half-bumped.

To take a specific version, ignoring the cool-down:

```bash
./workflow.cmd maintain.bump-uv --version=0.12.1
```

## Why the digests matter more than they look

`base-image` carries a tag *and* a digest, and such a reference resolves to the **digest**. Bump
the tag by hand and forget the digests, and every generated project keeps building the previous
image while its `pyproject.toml` claims otherwise — green, wrong, and invisible. That is the
whole reason the version and the digests are never written separately.

## After bumping

```bash
./workflow.cmd test.matrix
```

**This is the only thing that proves the bump works.** The command verifies that the version and
its images exist; it cannot tell you whether generated projects still lint, test and build on the
new uv. Only generating them and running their QA does that.

Then commit all ten values in one commit. A partial bump is the confusing state the command
exists to prevent, and splitting it across commits recreates it.

## What this does *not* do

- **It does not run on a schedule.** No bot, no automatic pull requests. Bumping is deliberate.
- **It does not touch existing projects.** Their pin was resolved when they were generated and is
  theirs to move, with `./workflow.cmd develop.bump-uv` inside the project.
- **It is not what makes new projects current.** Generation already resolves the newest eligible
  release, so a project created long after the last bump is fresh regardless. This keeps the
  committed pin — the offline fallback, and the uv this repo's own CI installs — from drifting far
  behind.

## Crossing a minor version

uv is pre-1.0, so `0.11.x → 0.12.0` is allowed to break behaviour. The command takes the newest
eligible version either way but says loudly when it crosses a boundary. Read uv's changelog
before merging one, and treat a green matrix as necessary rather than sufficient.

## See also

- [How uv is used](../../using/explanation/how-uv-is-used.md) — why the pin is exact, and how
  generation resolves it.
- [Test the template](test-the-template.md) — what `test.matrix` actually runs.
