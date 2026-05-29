# Publish docs to GitHub Pages

For GitHub-hosted projects, the template ships `.github/workflows/pages.yaml` by default. It runs `./workflow.cmd document.deploy-github` on every push to `main`, which delegates to `properdocs gh-deploy` (no GitHub Pages deploy actions involved — see [Design principles](../explanation/design-principles.md#pipelines-run-template-commands-only) for the reasoning). The only manual step is enabling Pages on the GitHub side.

The Pages scaffolding is **opt-in/opt-out at generation time** via the `integrate_pages` questionnaire answer (default `true`). Answering `false` removes both the workflow file and the matching `document.deploy-github` task from the generated project — see [Cookiecutter variables](../reference/cookiecutter-variables.md#integrate_pages).

## Step 1 — Push the template

Generate the project with `git_hosting_service=github`, push to GitHub. The first push to `main` triggers the Pages workflow. The workflow creates the `gh-pages` branch on its first successful run.

## Step 2 — Enable Pages on the repo

On GitHub:

1. **Settings → Pages**.
2. **Source**: **Deploy from a branch**.
3. **Branch**: `gh-pages` / `/ (root)`.

The branch only appears after the first workflow run completes — wait for the Actions tab to show a green Pages run, then configure.

That's it. Subsequent pushes to `main` redeploy automatically. The site lives at `https://<owner>.github.io/<repo>/`.

## Why `gh-pages` branch instead of the Actions-source flow?

Two related design principles drive this choice:

- **Pipelines run template commands only.** The workflow's only substantive step is `./workflow.cmd document.deploy-github`. Every behaviour change happens in `_CI/tasks/document.py`, not in the YAML.
- **Track every dependency in the SBOM.** `properdocs gh-deploy` is a Python command resolved from the locked `document` dependency group. `actions/upload-pages-artifact` and `actions/deploy-pages` would bring transitive dependencies that don't appear in `uv.lock` or the CycloneDX SBOM. Avoiding them keeps the supply-chain story honest.

See [Design principles](../explanation/design-principles.md#pipelines-run-template-commands-only).

## About the Node.js deprecation warning

After every push to `main` you may see a deprecation warning on the **`pages build and deployment`** workflow run — *not* on our `Pages` workflow. The warning reads:

> Node.js 20 actions are deprecated. The following actions are running on Node.js 20 and may not work as expected: actions/checkout@v4, actions/upload-artifact@v4.

That run is a GitHub-managed pipeline (`dynamic/pages/pages-build-deployment`) that the platform auto-triggers whenever the `gh-pages` branch updates. It is not defined in `.github/workflows/` and we cannot edit it. The deprecated `actions/checkout@v4` and `actions/upload-artifact@v4` references live inside that internal pipeline, not in our own workflow files — every action we *do* control is already pinned to its latest immutable release.

The warning is expected and intentionally not addressed. Silencing it would require switching to the `actions/upload-pages-artifact` + `actions/deploy-pages` flow, which would violate both design principles above. We accept the warning as the cost of keeping deploy logic in `_CI/tasks/document.py` and outside the SBOM-tracked dependency surface. GitHub will update their internal pipeline on their own timeline.

## Concurrency

The workflow uses `concurrency: { group: pages, cancel-in-progress: false }`. If you push twice in quick succession, the second deploy waits for the first to finish rather than racing it. Cancelling mid-deploy would leave the `gh-pages` branch in an indeterminate state.

## Custom domain

After the first deploy:

1. Add a `CNAME` file containing your domain to the `docs/` directory.
2. Configure DNS — ALIAS/ANAME for an apex domain, CNAME for a subdomain — pointing at `<owner>.github.io`.
3. **Settings → Pages → Custom domain** to set it on the GitHub side.

The next push to `main` redeploys with the custom domain.

## GitLab Pages instead

For GitLab-hosted projects, the equivalent is a `pages:` job in `.gitlab-ci.yml` that publishes the `site/` directory. The template doesn't ship one yet — it's the logical follow-up to this workflow.

## See also

- [The shipped workflow](https://github.com/schubergphilis/paleofuturistic_python/blob/main/%7B%7B%20cookiecutter.project_slug%20%7D%7D/.github/workflows/pages.yaml) — the actual YAML, kept short on purpose.
- [Design principles](../explanation/design-principles.md) — the two rules behind the workflow's shape.
