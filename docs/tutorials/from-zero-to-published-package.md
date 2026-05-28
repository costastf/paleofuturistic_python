# From zero to a published package

This tutorial picks up where [Generate your first project](generate-your-first-project.md) left you: a freshly-generated project with a green dev cycle. We'll make a real change, cut a release, and publish to PyPI.

You'll need a [PyPI account](https://pypi.org/account/register/) before the publish step.

## Step 1 — Write a feature

Open `src/<your_project_slug>/<your_project_slug>.py` and replace the body of `hello()` with something more interesting:

```python
def hello(someone: str = 'you') -> str:
    """Greet `someone` and announce the project."""
    return f'Hello {someone} from <your_project_slug>!'
```

Update the smoke test under `tests/` to match. Run the dev cycle once to confirm it's still green:

```bash
./workflow.cmd format && ./workflow.cmd lint && ./workflow.cmd test
```

## Step 2 — Commit using Conventional Commits

Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/) — the lint step rejects anything that doesn't parse. Start each message with a type prefix:

```bash
git add -A
git commit -m "feat: greet someone by name"
```

The prefix does **not** drive the version bump — you'll choose that explicitly in the next step. What it does drive is the **release notes**: commitizen reads the commit history when generating the changelog and groups your commits by prefix (`feat:` under "Features", `fix:` under "Bug Fixes", etc.).

## Step 3 — Cut the release

```bash
./workflow.cmd release -i minor
```

The `-i minor` is your explicit choice. Valid values: `major`, `minor`, `patch`, `alpha`, `beta`, `rc`.

This task:

1. Validates the working tree is clean and synced with origin.
2. Creates a `release/<version>` branch off `main`.
3. Bumps the version, writes the changelog, commits both.
4. Pushes the branch and the new `vX.Y.Z` tag.
5. Opens a release pull request on your git host (GitHub: via API if `GITHUB_TOKEN` is set, otherwise prints a manual URL; GitLab: prints a manual URL).

Approve and merge the resulting PR. The tag and bump land on `main`.

## Step 4 — Publish to PyPI

The `release.publish` task pushes the wheel and SBOM to PyPI. The recommended path is CI-driven [PyPI trusted publishing](https://docs.pypi.org/trusted-publishers/) — no long-lived tokens. Wire it up once for the project (see [Harden the GitHub repository](../how-to/harden-github-repository.md) for the GitHub Actions side), then:

```bash
./workflow.cmd release.publish
```

In a CI pipeline triggered by your release tag, this fires automatically.

## Step 5 — Publish the docs

For GitHub-hosted projects, see [Publish docs to GitHub Pages](../how-to/publish-docs-to-github-pages.md) for the workflow file and Pages setup.

## You're done

A tagged release exists, a wheel is on PyPI, and your docs are live.

Where to go next:

- [Update an existing project with cruft](../how-to/update-existing-project-with-cruft.md) — bring future template improvements into this project.
- [Design principles](../explanation/design-principles.md) — why the template made the choices it did.
