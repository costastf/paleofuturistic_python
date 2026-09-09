# From zero to a published package

This tutorial picks up where [Generate your first project](generate-your-first-project.md) left off: a freshly generated project with a green dev cycle. We'll make a real change, cut a release, and publish to PyPI.

You'll need a [PyPI account](https://pypi.org/account/register/) and a public [git remote](https://docs.github.com/en/get-started/git-basics/about-remote-repositories#creating-remote-repositories) before the publish step.

## Step 1 — Connect to GitHub

For this tutorial we will assume you use GitHub as your git remote.
Create a repository on GitHub.
It must be public if you want to publish public GH pages, as we do at the end of this tutorial.
Do not add any files like README, LICENSE etc.

Run te following commands in your project directory to connect to the remote:

```bash
git remote add origin git@github.com:your_handle/test_260708.git
git branch -M main
git push -u origin main
```

## Step 2 — Write a feature

Open `src/<your_project_slug>/<your_project_slug>.py` and replace the body of `hello()` with something more interesting, for example:

```python
def hello(greeting: str = 'Hello', someone: str = 'you') -> str:
    """Greet someone.

    Args:
        greeting: The greeting message.
        someone: The name of the person to greet.

    Returns:
        A greeting message.
    """
    return f'{greeting} {someone} from test_260708!'
```

Update the smoke test under `tests/` to match if needed.
Run the dev cycle once to confirm it's still green:

```bash
./workflow.cmd preflight
```

Commit:

```bash
git add -A
git commit -m "feat: greet someone with a specific word"
git push
```

(Reminder: conventional commit messages are required, the messages drive the release notes, not the version bump.)

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

## Step 4 — Publish to PyPI

The `release.publish` task pushes the wheel and SBOM to PyPI. The recommended path is CI-driven [PyPI trusted publishing](https://docs.pypi.org/trusted-publishers/) — no long-lived tokens. Wire it up once for the project (see [Harden the GitHub repository](../how-to/harden-github-repository.md) for the GitHub Actions side), then:

Approve and merge the resulting PR.
The tag and bump land on `main`.

## Step 5 — Publish the docs

For GitHub-hosted projects, see [Publish docs to GitHub Pages](../how-to/publish-docs-to-github-pages.md) for the workflow file and Pages setup.

## You're done

A tagged release exists, a wheel is on PyPI, and your docs are live.

Where to go next:

- [Update an existing project with copier](../how-to/update-existing-project-with-copier.md) — bring future template improvements into this project.
- [Design principles](../../maintaining/explanation/design-principles.md) — why the template made the choices it did.
- Run `./workflow.cmd --list` to see all available workflow commands and experiment to create your ideal dev cycle.
