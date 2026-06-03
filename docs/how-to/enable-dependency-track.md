# Enable Dependency Track integration

Wire a generated project to an OWASP [Dependency Track](https://dependencytrack.org/) server so every release uploads a fresh CycloneDX SBOM.

## When to use this

You already run a Dependency Track instance (self-hosted or managed) and want this project's releases to appear there automatically. If you don't have a server, see [SBOM and security model](#) (inner-project explanation) for what you're missing first.

## At generation time

When `copier copy` asks:

```
integrate_dependency_track [y]:
```

answer `y`. This adds the Dependency Track upload step to the security workflow and the `OWASP_DTRACK_SETTINGS` block to `_CI/tasks/configuration.py`.

## After generation

The generated project expects three environment variables at release time:

| Variable | Example | Where to find it |
| --- | --- | --- |
| `OWASP_DT_URL` | `https://dt.example.com` | Your Dependency Track instance |
| `OWASP_DT_API_KEY` | `odt_…` | DT → Administration → Access Management → Teams |
| `OWASP_DT_PROJECT_UUID` | UUID | DT → Projects → your project |

Set them in your CI secret store (GitHub Actions secrets or GitLab CI variables). Locally, export them in your shell before running:

```bash
./workflow.cmd secure.sbom-upload
```

## Verify it works

After running `secure.sbom-upload`, the task prints the upload response. In the DT UI, the project's "Components" tab should refresh within a few seconds.

## I picked the wrong answer at generation time

Re-run `uvx copier update --trust` and change `integrate_dependency_track` when prompted. See [Update an existing project with copier](update-existing-project-with-copier.md) for the full flow.
