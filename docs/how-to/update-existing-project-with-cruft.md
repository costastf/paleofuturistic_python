# Update an existing project with cruft

When this template ships a new version, you can pull the changes into an existing generated project without re-generating from scratch. [cruft](https://cruft.github.io/cruft/) tracks the template revision your project was generated from and produces a reviewable diff against the latest.

## The basic update

From the root of your generated project:

```bash
uvx cruft update --checkout latest
```

cruft:

1. Re-renders the template at the new revision using your stored answers (`.cruft.json`).
2. Diffs the result against your current files.
3. Applies the diff, prompting for conflicts.

Review the changes with `git diff`, run the dev cycle (`./workflow.cmd format && lint && test && build`), and commit when happy.

## When prompts have changed

If the new template version added or renamed a questionnaire variable (for example `git_hosting_service` was added recently), cruft will prompt for any missing answers. Provide them — your `.cruft.json` is updated in place.

## Resolving conflicts

cruft uses `.rej` files for hunks it couldn't apply cleanly. The most common cause is that you customised a file the template also changed. Resolve them by hand, delete the `.rej`, and re-run `./workflow.cmd test`.

## Skip a file entirely

If you've deliberately diverged from the template for a specific file, list it in `.cruft.json` under `skip`:

```json
{
  "skip": [
    "src/your_package/your_package.py",
    "README.md"
  ]
}
```

Cruft will leave those files alone on every future update.

## When the upstream is unreachable

`cruft update` needs network access to fetch the template. In an air-gapped environment, clone the template repo separately and point `cruft` at the local path:

```bash
uvx cruft update --checkout latest --variables-to-update-file /tmp/answers.json /path/to/local/clone
```

## See also

- [Cruft documentation](https://cruft.github.io/cruft/#updating-a-project) — the full update workflow.
- [Cruft questionnaire variables](../reference/cookiecutter-variables.md) — what each answer in `.cruft.json` controls.
