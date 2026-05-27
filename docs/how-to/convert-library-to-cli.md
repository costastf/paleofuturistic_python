# Convert the library into a CLI

The template generates a library by default. Adding a command-line entry point is a small additive change.

## Step 1 — Add a `__main__`

Create `src/<your_project_slug>/__main__.py`:

```python
"""Command-line entry point."""

from <your_project_slug> import hello


def main() -> None:
    """Print a greeting."""
    print(hello())


if __name__ == '__main__':
    main()
```

This makes `python -m <your_project_slug>` work.

## Step 2 — Register a console script

In `pyproject.toml`:

```toml
[project.scripts]
<your-project-slug> = "<your_project_slug>.__main__:main"
```

The key on the left is the executable name installed on `PATH`. Hyphens are fine; the import target on the right must use underscores.

## Step 3 — Verify

```bash
uv sync
uv run <your-project-slug>          # via console script
uv run python -m <your_project_slug> # via __main__
```

Both should print `Hello you from <your_project_slug>!`.

## Step 4 — Run it as a uvx-installable tool

After publishing the package:

```bash
uvx <your-project-slug>
```

uv fetches the wheel from PyPI, installs it into an ephemeral environment, and runs the console script.

## Picking an argument-parsing framework

The example above is enough for trivial CLIs. For anything real:

- **Stdlib `argparse`** — zero dependencies, ubiquitous, verbose.
- **[Typer](https://typer.tiangolo.com/)** — type hints become CLI flags; great DX.
- **[Click](https://click.palletsprojects.com/)** — Typer's underlying library; more control, more boilerplate.

Add your choice as a runtime dependency:

```bash
uv add typer
```

## When a script makes more sense

For one-off automations, [uv inline-dependency scripts](https://docs.astral.sh/uv/guides/scripts/#declaring-script-dependencies) skip the package layer entirely. Use the template for things you intend to version, distribute, and document.
