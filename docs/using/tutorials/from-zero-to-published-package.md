# From zero to a published package

This tutorial picks up where [Generate your first project](generate-your-first-project.md) left off: a freshly generated project with a green dev cycle. We'll make a real change, cut a release, and publish to PyPI.

You'll need a [PyPI account](https://pypi.org/account/register/) and a public [git remote](https://docs.github.com/en/get-started/git-basics/about-remote-repositories#creating-remote-repositories) before the publish step.

## Step 1 — Write a feature

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
Commit:

```bash
git add -A
git commit -m "feat: greet someone with a specific word"
```

Reminders:

- All relevant checks for pre-commit run on staged files (Ruff format/check, pylint, complexipy, conventional commit messages).
- Commit messages drive the release notes, not the version bump.

## Step 2 — Integrate

For this tutorial we will assume you use GitHub as your git remote.
Create a repository on GitHub.
It must be public if you want to publish public GH pages, as we do at the end of this tutorial.
Do not add any files like README, LICENSE etc.

Run the following commands in your project directory to connect to the remote
(replace your_handle / test_260708 with your git remote handle / project name here and in the following examples):

```bash
git remote add origin git@github.com:your_handle/test_260708.git
git push -u origin main
```

This will run all the checks from preflight before actually pushing.
This might fail if you did some more exotic edits than the example above.
Don't worry.
Preflight will tell you what to fix, do that commit and then try to push again.

Go to your git remote.
A couple of pipelines will start running.
For now only Continuous Integration is the interesting one.
It runs the same preflight as before, this time where everyone can see its outcome.

## Step 3 — Cut the release

```bash
./workflow.cmd release -i minor
```

The `-i minor` is your explicit choice. Valid values: `major`, `minor`, `patch`, `alpha`, `beta`, `rc`.

This task:

1. Validates the working tree is clean and synched with origin.
2. Creates a `release/<version>` branch off `main`.
3. Bumps the version, writes the changelog, updates the version badge, commits all.
4. Pushes the branch and the new `vX.Y.Z` tag.
5. Opens a release pull request on your git host (GitHub: via API if `GITHUB_TOKEN` is set, otherwise prints a manual URL; GitLab: prints a manual URL).

Note that the security audit pipeline now does run.
That is because a commit edited `uv.lock`.
This is a desired side-effect during release.
You would not want to release a package with known vulnerabilities (that have not been suppressed in `.security-overrides`).

## Step 4 — Publish to PyPI

The `release.publish` task pushes the wheel and SBOM to PyPI. The recommended path is CI-driven [PyPI trusted publishing](https://docs.pypi.org/trusted-publishers/) — no long-lived tokens. Wire it up once for the project (see [Harden the GitHub repository](../how-to/harden-github-repository.md) for the GitHub Actions side), then:

Approve and merge the resulting PR.
The tag and bump land on `main`.

After all the pipelines ran you should see your project published on PyPI.

## Step 5 — Publish the docs

For GitHub-hosted projects, see [Publish docs to GitHub Pages](../how-to/publish-docs-to-github-pages.md) for the workflow file and Pages setup.

## You're done

A tagged release exists, a wheel is on PyPI, and your docs are live.

Where to go next:

- Run `./workflow.cmd --list` to see all available workflow commands and experiment to create your ideal dev cycle.
- Look at the (developer) docs in your templated project. It will guide you on practical things, like adding dependencies.
- [Update an existing project with copier](../how-to/update-existing-project-with-copier.md) — bring future template improvements into this project.
- [Design principles](../../maintaining/explanation/design-principles.md) — why the template made the choices it did.
- When you feel comfortable developing in a project molded by this template [activate the test coverage ratchet](../explanation/testing-strategy.md).
