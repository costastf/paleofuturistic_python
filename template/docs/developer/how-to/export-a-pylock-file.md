# Export a pylock file

For handing this project's exact dependency set to something that does not read `uv.lock`:
another installer, a security scanner, a platform team's build system. `pylock.toml` is the
standard lock format ([PEP 751](https://packaging.python.org/en/latest/specifications/pylock-toml/)),
so any tool that implements the spec can install or audit from it.

## Export it

```bash
./workflow.cmd develop.pylock
```

This runs `uv export --frozen --format pylock.toml --all-groups` and writes
`reports/pylock.toml`: every package in `uv.lock`, every dependency group included, with its
version, index, artifact URLs and hashes. `--frozen` means it exports the lock as committed and
fails rather than re-resolving if `pyproject.toml` has moved ahead of it.

To export a narrower set, call uv directly, e.g. runtime dependencies only:

```bash
uv export --frozen --format pylock.toml --no-dev --output-file reports/pylock.runtime.toml
```

## Use it

Hand over the file, or install from it with any installer that implements PEP 751. uv's pip
interface does, into any environment:

```bash
uv pip install --python /path/to/venv -r reports/pylock.toml
```

## Why it is not committed

`uv.lock` is the lock this project works from: uv resolves into it, every task syncs from it,
and the SBOM is composed from it. A committed `pylock.toml` would be a second copy of the same
pins, correct only until the next `uv add`. So the export lands under `reports/`, which is
gitignored, and you generate it when someone needs it.

If a consumer needs it on every release, generate it in the pipeline and attach it to the
release; do not commit it.

## Source of truth

- [pylock.toml specification](https://packaging.python.org/en/latest/specifications/pylock-toml/)
- [uv: exporting a lockfile](https://docs.astral.sh/uv/concepts/projects/export/)
