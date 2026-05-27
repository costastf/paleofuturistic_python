# Publish docs to GitHub Pages

For GitHub-hosted projects, you can serve the generated properdocs site as a GitHub Pages site.

## Step 1 — Enable Pages

In your repo on GitHub:

1. **Settings → Pages**.
2. **Source**: GitHub Actions.

Don't pick "Deploy from a branch" — the template's workflow will push the built site itself.

## Step 2 — The deploy workflow

The template ships `.github/workflows/` with a publish workflow that runs `properdocs build` and publishes the result to Pages on every tag push. If you don't see a `pages.yaml` or equivalent there yet, add one along these lines (adjust if the template gains its own):

```yaml
name: Pages
on:
  push:
    tags: ['v*']
permissions:
  contents: read
  pages: write
  id-token: write
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deploy.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v7
      - run: ./workflow.cmd document
      - uses: actions/upload-pages-artifact@v3
        with: { path: site }
      - id: deploy
        uses: actions/deploy-pages@v4
```

## Step 3 — `use_directory_urls`

The template's `properdocs.yml` sets `use_directory_urls: false`. This produces `tutorials/foo.html` rather than `tutorials/foo/index.html`. Pages serves both fine; pick whichever you prefer (the template default is more portable to file://-served previews).

## Step 4 — Verify

Push a tag and watch the Pages workflow in the Actions tab. The deploy URL appears in the job summary — your docs will be at `https://<user-or-org>.github.io/<repo>/`.

## Custom domain

After the first successful deploy:

1. Add a `CNAME` file with your domain to the `docs/` directory.
2. Configure DNS (ALIAS/ANAME for apex, CNAME for subdomain) to point at `<user-or-org>.github.io`.
3. **Settings → Pages → Custom domain** to set it on the GitHub side.

## GitLab Pages instead

For GitLab-hosted projects, the equivalent is a Pages job in `.gitlab-ci.yml` that publishes the `site/` directory. The template doesn't ship one yet; it's a reasonable contribution to make.
