# Work behind a fence

This tutorial takes a project from generation to a green pipeline and a first release when
your packages come from, and go to, your organisation's Artifactory instead of PyPI. It
follows the same path as [Generate your first project](generate-your-first-project.md) and
[From zero to a published package](from-zero-to-published-package.md), with the fence added
at each step where it matters. Nothing in the generated project differs: the fence is a set
of variables your organisation sets once, and every project under it inherits.

You need four names from your platform team before you start. [Fencing
options](../reference/fencing-options.md) lists what they set up on their side; this is what
you take from it:

| What | Looks like | Goes into |
| --- | --- | --- |
| The index's simple API | `https://pkgs.example.com/artifactory/api/pypi/pypi-remote/simple` | `UV_DEFAULT_INDEX` |
| The interpreter mirror | `https://pkgs.example.com/artifactory/python-build-standalone` | `UV_PYTHON_INSTALL_MIRROR` |
| The Artifactory instance, your project's key and the token audience | `https://pkgs.example.com`, `widgets`, `https://pkgs.example.com` | `JFROG_URL`, `JFROG_PROJECT`, `JFROG_AUDIENCE` |
| The docker remote in front of ghcr.io | `pkgs.example.com/ghcr-remote` | `base-image` in `pyproject.toml` |

A fifth, the upload URL of the repository you publish to, comes in at step 7.

## Step 1 — Point your machine at the index

Put the two uv variables in your shell profile, then log uv in to the index host with your
own Artifactory identity token:

```bash
export UV_DEFAULT_INDEX=https://pkgs.example.com/artifactory/api/pypi/pypi-remote/simple
export UV_PYTHON_INSTALL_MIRROR=https://pkgs.example.com/artifactory/python-build-standalone
uv auth login pkgs.example.com
```

uv stores the token for every request to that host, so nothing else on your machine needs it.
From here on every `uv` command, and every `./workflow.cmd` task, resolves from the index and
fetches interpreters from the mirror.

## Step 2 — Generate the project

The same command as in the open:

```bash
uvx copier copy gh:schubergphilis/paleofuturistic_python my-widget
```

Generation runs `uv lock` with your variables, so the lock is resolved against the index from
the first commit. Check it:

```bash
grep -m1 'registry =' my-widget/uv.lock
```

It names your index, not `pypi.org`. A lock names where every package came from, so a lock
made on one side of the fence cannot be installed on the other; if you ever move a project
across, relock it with `uv lock` under the new variable.

Two fetches during generation go elsewhere and fall back when they cannot: the render hook
asks `pypi.org` for the newest uv to pin and `ghcr.io` for the base image's digest, and says
so when it uses the committed pin instead. Both are fine.

## Step 3 — Run the gate

```bash
cd my-widget
./workflow.cmd preflight
```

The first task syncs the environment from the lock, through the index. If your machine has no
egress at all, one task fails: `document.build` fetches two object inventories from
`docs.python.org` and `typing-extensions.readthedocs.io` for cross-references. Drop the two
`inventories` entries in `properdocs.yml`, or point them at copies your organisation hosts,
and run the gate again. `secure.audit` has the same limit later: it asks `pypi.org` about
each package and nothing proxies that, so the audit runs where it has that egress.

## Step 4 — Move the base image inside

The deps image builds on `ghcr.io/astral-sh/uv`, pinned by digest in `pyproject.toml`. Edit
the name to the docker remote and keep the digest:

```toml
[tool.docker-versions]
base-image = "pkgs.example.com/ghcr-remote/astral-sh/uv:0.13.7-python3.11-trixie-slim@sha256:…"
```

The digest identifies the same bytes wherever they are served from, so the image you build on
does not change, only where it comes from. Build it once by hand to see the fence work. The
build needs the index credentials for its builder stage and for the pull, so set them for the
one command, from the token you logged in with:

```bash
INDEX_USERNAME=you INDEX_PASSWORD=$(cat ~/.my-artifactory-token) ./workflow.cmd container.build
./workflow.cmd container.audit
```

The build prints `Logged in to pkgs.example.com as you.` and then the build command with
`"$INDEX_PASSWORD"` in it, never the value. The audit reads the image back and reports no
credential trace: the stage that saw the token is not the stage that was kept.

Commit the change. The deps tag is computed from the lock, the Dockerfile and the base image
name, so the next pipeline run builds a new image.

## Step 5 — Set the variables on the host, once

This is your platform team's step, or yours if you own the group or organisation. Every
project under it inherits, so it is done once, not per project.

On **GitLab**, as group CI/CD variables:

| Variable | Value |
| --- | --- |
| `UV_DEFAULT_INDEX`, `PIP_INDEX_URL` | the index's simple API |
| `UV_PYTHON_INSTALL_MIRROR` | the interpreter mirror |
| `JFROG_URL`, `JFROG_PROJECT`, `JFROG_AUDIENCE` | the instance, the project key, the audience |
| `UV_PUBLISH_URL` | the upload URL, scoped to the `pypi` environment |

On **GitHub**, as organisation variables, with `UV_PUBLISH_URL` as a secret on the `pypi`
environment instead:

| Variable | Value |
| --- | --- |
| `UV_DEFAULT_INDEX` | the index's simple API |
| `UV_PYTHON_INSTALL_MIRROR` | the interpreter mirror |
| `JFROG_URL`, `JFROG_PROJECT`, `JFROG_AUDIENCE` | the instance, the project key, the audience |

Each project still needs what it needs in the open: on GitLab the deploy token for the deps
image in `DEPS_IMAGE_USERNAME` and `DEPS_IMAGE_PASSWORD`, scoped to the `deps` environment.
No fence credential is stored anywhere: every job mints its own from the ID token its host
gives it, as the user `<project>-ci` your platform team mapped.

If the runners themselves sit inside the fence, with no egress to Docker Hub, gcr.io or
`ghcr.io`, a few more variables point the job images and, on GitHub, the deps image and uv at
Artifactory too. [Fencing options](../reference/fencing-options.md) has them under case 3.

## Step 6 — Push and read the pipeline

```bash
git push -u origin main
```

Every job that fetches logs in first and says so. On GitLab the plan job prints
`Index credentials minted for widgets-ci at https://pkgs.example.com from the job ID token.`
and hands them to the kaniko job; `preflight`, `secure` and `publish` each print
`Logged in to pkgs.example.com as widgets-ci; credentials in /root/.netrc for this job.`
before anything else. On GitHub the same lines appear, with the token minted from the Actions
endpoint. The first job inside the image runs `container.audit` and reports no credential
trace.

When a job fails instead, the first line of the failure names the half-set state, and the
reference lists what each one means: `No fenced index configured; nothing to log in to.` means
`UV_DEFAULT_INDEX` did not reach the job; a 401 on the first package means the index is set
and nothing minted credentials, which is the audience or the project key missing; a failed
exchange prints Artifactory's answer, which names a provider or audience it does not know.

## Step 7 — Release into Artifactory

Make a change, cut the release and merge it, exactly as in [From zero to a published
package](from-zero-to-published-package.md):

```bash
./workflow.cmd release
```

The publish job logs in, fills the upload credentials from the same token beside the
`UV_PUBLISH_URL` the group or environment set, and uploads to your repository. Attestations
are skipped: Sigstore is outside the fence, and a credentialed upload carries none. The
release tag and its entry are created on the host as before.

## Where to go next

- [Fencing options](../reference/fencing-options.md) — every case, every variable, what
  setting or leaving each one does on each target, and what the organisation provides.
- [Network egress](../reference/network-egress.md) — which service every command and job
  reaches, in the open and behind the fence.
- The generated project's own *Work behind a fenced index*, rendered for its host, which
  every teammate finds under the project's how-to pages.
