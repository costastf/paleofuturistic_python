# Fencing options

Every way a generated project can sit behind an organisation's Artifactory, what each case
needs set, and what the organisation provides for it. The project's files are the same in
every case: one pipeline, one Dockerfile, one set of tasks, serving a project in the open with
every variable unset and a project behind a fence with a handful of variables its organisation
sets once. The generated project ships the same material rendered for its host as *Work behind
a fenced index*; this page covers both hosts and every case side by side.

## The cases

| Case | Packages | Interpreters | Base image | Deps image | Job images and uv | Publishing |
| --- | --- | --- | --- | --- | --- | --- |
| **1. In the open** | PyPI | GitHub's releases | `ghcr.io` | GitLab's registry, or `ghcr.io` | Docker Hub, gcr.io; Astral's mirror | PyPI, Trusted Publishing |
| **2. Fenced index, runners with public egress** | Artifactory | Artifactory | `ghcr.io`, or Artifactory | GitLab's registry, or `ghcr.io` | Docker Hub, gcr.io; Astral's mirror | Artifactory |
| **3. Fenced index, runners inside the fence** | Artifactory | Artifactory | Artifactory | GitLab's registry, or Artifactory | Artifactory | Artifactory |
| **4. A developer machine behind the fence** | Artifactory | Artifactory | Artifactory, or `ghcr.io` if reachable | local build | not used | not from a laptop |
| **5. Generating a project behind the fence** | Artifactory | Artifactory | not used | not used | not used | not used |

Case 1 needs nothing. Cases 2 and 3 differ only in what the runner itself can reach: with
public egress the base image may stay on `ghcr.io`, the deps image stays where the host keeps
it, and the GitLab job images and GitHub's uv download need no change; inside the fence
everything comes from Artifactory. On GitLab the deps image always lives in the project's own
registry, which is inside the fence with the instance; on GitHub it moves from `ghcr.io` to a
docker repository in Artifactory. A fenced index with an open base image is a supported mix:
the credentials are sent only to a registry on the index host, so `ghcr.io` never sees them.
Case 4 is case 2 with a personal token in place of the job's. Case 5 is `uv lock` and two
tool fetches with the same variables as case 4.

## What to set, per case

Each variable is set once at the organisation level and inherited by every project: a group on
GitLab, an organisation or repository on GitHub. GitHub injects nothing on its own, so every
workflow names the variables it hands down in its `env:` from `vars`; a variable the workflows
do not name never reaches a job. An unset variable arrives empty, which uv and the tasks read
as unset.

| Variable | Cases | GitLab | GitHub | Shell | What it does |
| --- | --- | --- | --- | --- | --- |
| `UV_DEFAULT_INDEX` | 2, 3, 4, 5 | group variable | organisation or repository variable | yes | uv resolves and installs from this simple API instead of PyPI; the lock generation wrote already names it. |
| `UV_PYTHON_INSTALL_MIRROR` | 2, 3, 4, 5 | group variable | organisation or repository variable | yes | Where uv fetches the interpreters the tox matrix needs, a generic remote in front of GitHub's `python-build-standalone` releases. |
| `PIP_INDEX_URL` | 2, 3 | group variable | not needed | no | The GitLab plan job installs uv with pip before the launcher exists; same value as the index. Nothing on GitHub installs with pip. |
| `JFROG_URL`, `JFROG_PROJECT`, `JFROG_AUDIENCE` | 2, 3 | group variables | organisation or repository variables | no | Each job mints an ID token for the audience and exchanges it at `JFROG_URL` for a token scoped to the project, as user `<project>-ci`. No stored secret anywhere. |
| `JFROG_PROVIDER` | 2, 3 | group variable, optional | organisation or repository variable, optional | no | The identity provider name Artifactory verifies the token against; `gitlab` or `github` unless set. |
| `INDEX_USERNAME`, `INDEX_PASSWORD` | 4; 2 or 3 without OIDC | group variables, masked | repository secrets | yes | A token the index accepts, for a project that would rather not map an OIDC identity, or a developer's own. Set, they win over the exchange everywhere, and the same pair logs the engine in to the base image's registry. |
| `UV_PUBLISH_URL` | 2, 3 | group variable scoped to the `pypi` environment | secret on the `pypi` environment | no | `release.publish` uploads here with credentials and without attestations; with OIDC the job fills the username and password itself. |
| `UV_PUBLISH_USERNAME`, `UV_PUBLISH_PASSWORD` | 2 or 3 without OIDC | scoped to `pypi`, masked | secrets on `pypi` | no | The upload credentials when they are not minted. Set, they are left alone. |
| `base-image` in `pyproject.toml` | 3; 2 optionally | the project's file | the project's file | n/a | Edited to the name the docker remote serves `ghcr.io/astral-sh/uv` under, digest kept. The build logs in to that registry with the index identity when it is the index host or one of its subdomains. |
| `PYTHON_IMAGE`, `KANIKO_IMAGE` | 3 | group variables | n/a | no | The images the two deps jobs run in before the deps image exists, overridden with the names Docker Hub's and gcr.io's docker remotes serve them under. |
| `DOCKER_AUTH_CONFIG` | 3 | group variable, masked | n/a | no | Read by the GitLab runner to pull a job's own image. Kaniko does not read it; the base image is pulled with the index identity instead. |
| `DEPS_IMAGE_REGISTRY` | 3 | n/a | organisation or repository variable | no | `host/repository` of a docker repository in Artifactory the deps image goes to instead of `ghcr.io`, pushed with the index identity and pulled anonymously by the jobs that run in it. |
| `UV_MANIFEST_FILE` | 3 | n/a | organisation or repository variable | no | The URL of a uv version manifest the organisation hosts, in the `astral-sh/versions` format, for the build job, the one GitHub job outside the deps image. |
| `inventories` in `properdocs.yml` | 3 | the project's file | the project's file | n/a | The two object inventories `document.build` fetches from `docs.python.org` and `typing-extensions.readthedocs.io`; dropped or pointed at hosted copies inside the fence. |

Two GitLab variables are not about the fence but every GitLab project needs them: the deploy
token in `DEPS_IMAGE_USERNAME` and `DEPS_IMAGE_PASSWORD`, scoped to the `deps` environment,
which pushes the deps image to the project's own registry in every case.

## What setting or leaving each variable does, per target

The four targets are the GitLab pipeline, the GitHub workflows, a developer's machine and
generation. Every row says what happens when the variable is unset and what changes when it
is set, including the half-set states that fail in a way the log does not explain.

### `UV_DEFAULT_INDEX`

| Target | Unset | Set |
| --- | --- | --- |
| GitLab | Every job resolves from PyPI. The plan job hands the kaniko job no credentials even when the `JFROG_*` variables are set, and `index.login` says there is no fenced index: the index is what the credentials are for. | Every uv call in every job resolves from the index. `index.login` writes a netrc for its host, the builder stage gets it as `INDEX_URL`, and the base image's registry is matched against its host. |
| GitHub | The same: PyPI everywhere, no credentials minted, `index.login` a no-op. | The same as GitLab; the build job's `INDEX_URL` is this value. |
| Your machine | PyPI, for `uv sync`, `uv lock` and every task. | Every uv command uses the index; `uv auth login` pairs with its host. |
| Generation | The lock is resolved against PyPI and records `pypi.org` and `files.pythonhosted.org` for every package. | The lock records the index and its file URLs. A project generated in the open and moved behind the fence, or the reverse, has a lock the other side cannot install from: `uv sync --frozen` in the deps image fetches the recorded URLs. Relock with `uv lock` under the new variable, or `develop.refresh-deps` to move the pins too. |

### `UV_PYTHON_INSTALL_MIRROR`

| Target | Unset | Set |
| --- | --- | --- |
| GitLab, GitHub | The tox matrix fetches each interpreter the deps image lacks from GitHub's releases. Behind a fence that fetch fails, and `preflight` with it, for every environment whose interpreter is missing. | uv fetches them from the mirror. Nothing else changes; in the open the variable is harmless. |
| Your machine | GitHub's releases, for `test.tox` and for the floor interpreter the first sync needs. | The mirror, for both. |
| Generation | `uv lock` fetches the floor interpreter from GitHub if the machine lacks it. | From the mirror. |

### `PIP_INDEX_URL`

| Target | Unset | Set |
| --- | --- | --- |
| GitLab | The plan job installs uv with pip from PyPI. With runner egress that works behind a fence too; without it the plan job fails before the launcher exists, and nothing after it runs. | pip installs uv from the index, with the netrc `index.login` does not write yet: the plan job has no launcher before this line, so the index must allow this one anonymous read or the group sets pip's own credentials. |
| GitHub, your machine, generation | Not read: nothing installs with pip. | Harmless. |

### `JFROG_URL`, `JFROG_PROJECT`, `JFROG_AUDIENCE`

| Target | Unset | Set |
| --- | --- | --- |
| GitLab | Every job mints an ID token for the placeholder audience `not-configured` and nothing consumes it. With the index set and these unset, every fetch is anonymous and fails on the first package the remote refuses. | Each job exchanges its token at `JFROG_URL` for a token scoped to the project as `<project>-ci`, and logs in. `JFROG_AUDIENCE` unset while the other two are set leaves the placeholder audience in the token, which Artifactory rejects: `index.login` fails the job with the exchange's answer. `JFROG_URL` or `JFROG_PROJECT` alone mints nothing and logs in nowhere. |
| GitHub | No token is minted; the same anonymous failure behind a fence. | The job asks the Actions endpoint for a token for the audience and exchanges it. An unset `JFROG_AUDIENCE` means no token is requested, no login, and the anonymous failure. A pull request from a fork gets no token and no variables, so it fails on its first fetch whatever is set. |
| Your machine | Not read. The exchange needs a job's ID token, which a shell does not have. | Not read; set `INDEX_USERNAME` and `INDEX_PASSWORD` instead. |
| Generation | Not read. | Not read; the same pair applies. |

### `JFROG_PROVIDER`

| Target | Unset | Set |
| --- | --- | --- |
| GitLab, GitHub | The exchange names `gitlab` or `github` as the identity provider, which is what Artifactory most likely called it. A provider named otherwise rejects the exchange and `index.login` fails the job with that answer. | The exchange names this provider instead. |
| Your machine, generation | Not read. | Not read. |

### `INDEX_USERNAME`, `INDEX_PASSWORD`

| Target | Unset | Set |
| --- | --- | --- |
| GitLab | The credentials come from the exchange, or from nowhere. | Used as given everywhere, no exchange runs, and the same pair pulls the base image from a registry on the index host. Group variables are readable by every job unless marked protected, which keeps a fork's pipeline from them. |
| GitHub | The same. | Repository secrets, handed to the build job, which wins over the exchange there; `index.login` in the other jobs still exchanges unless the secrets are named in their `env:` too. A fork's pull request never sees them. |
| Your machine | `container.build` builds the base image anonymously and the builder stage syncs with whatever `uv auth login` stored, which the build does not see: behind a fence the sync fails on the first package. | The build names them, supplies them through the environment, logs the engine in to the base image's registry when it is on the index host, and the builder stage syncs with them. Set them for the one command. |
| Generation | `uv lock` uses what `uv auth login` stored for the index host. | Not read by generation; `uv auth login` is the way. |

### `UV_PUBLISH_URL`, with `UV_PUBLISH_USERNAME` and `UV_PUBLISH_PASSWORD`

| Target | Unset | Set |
| --- | --- | --- |
| GitLab, GitHub | `release.publish` publishes to PyPI through Trusted Publishing with the job's ID token, attestations included; PyPI must know the project's publisher or the upload is refused. | Uploads go to this URL with credentials and no attestations. With only the URL set, `index.login`'s credentials fill the username and password; with no exchange configured either, uv is refused at the upload. With the username and password set, they are left alone and no exchange is needed for the upload. |
| Your machine | `release.publish` by hand needs a PyPI token or fails; the pipeline is the intended publisher. | Uploads to the URL with the pair you set; the OIDC fill does not apply. |
| Generation | Not read. | Not read. |

### `base-image` in `pyproject.toml`

| Target | Left at `ghcr.io` | Pointed at the docker remote |
| --- | --- | --- |
| GitLab | kaniko pulls from `ghcr.io` anonymously. With runner egress that works behind a fence; without it the build job fails at the pull. | The plan job writes `BASE_IMAGE_REGISTRY` into its dotenv when the remote is on the index host, and kaniko pulls from it with the `INDEX_*` pair the same dotenv carries. With no credentials configured the pull is anonymous and fails if the remote requires a login. The deps tag changes, so the next run builds a new image. |
| GitHub | The engine pulls from `ghcr.io`, reachable from hosted runners. | The engine logs in to the remote with the index identity first, under the same host rule, then builds. |
| Your machine | `container.build` pulls from `ghcr.io`. | Logs in with `INDEX_USERNAME` and `INDEX_PASSWORD` when set, then builds; anonymous otherwise. |
| Generation | The render hook reads the digest from `ghcr.io` to stamp a fresh pin and falls back to the committed pin when it cannot. | The name is a project edit after generation; the hook stamps `ghcr.io` names only. |

### `PYTHON_IMAGE`, `KANIKO_IMAGE`

| Target | Unset | Set |
| --- | --- | --- |
| GitLab | The two deps jobs run in `python:3-slim` from Docker Hub and the kaniko executor from gcr.io. A runner without egress to both fails at the image pull before any script runs. | The runner pulls the named images with `DOCKER_AUTH_CONFIG`. The SBOM records the file's defaults, not the group's override. |
| GitHub, your machine, generation | Not read. | Not read. |

### `DOCKER_AUTH_CONFIG`

| Target | Unset | Set |
| --- | --- | --- |
| GitLab | The runner pulls every job image anonymously, which the public registries allow. With the two images overridden and this unset, the runner pulls from Artifactory anonymously and fails if it requires a login. | The runner logs in to the registries named in it before pulling a job's image. Kaniko and the tasks never read it; a value here does nothing for the base image or the index. |
| GitHub, your machine, generation | Not read. | Not read. |

### `DEPS_IMAGE_REGISTRY`

| Target | Unset | Set |
| --- | --- | --- |
| GitHub | The build job pushes the deps image to `ghcr.io` with the workflow token, and every job that runs in it pulls with the same token. A runner that cannot reach `ghcr.io` fails at the push, and the jobs after it at the pull. | The build job pushes under `host/repository` by repository name, logged in with the index identity when the host is the index host or a subdomain; on any other host the push goes anonymously and says so. Every `container:` block's credentials become empty, the runner skips the login, and the pull is anonymous: a repository that refuses anonymous reads fails every job after the build. `container.audit` reads the image back anonymously too. The image's tag and digest handling are unchanged. |
| GitLab, your machine, generation | Not read: GitLab's deps image lives in the project's own registry in every case, and a laptop build is local. | Not read. |

### `UV_MANIFEST_FILE`

| Target | Unset | Set |
| --- | --- | --- |
| GitHub | `setup-uv` in the build job resolves the pinned uv through Astral's manifest and downloads it from `releases.astral.sh`, falling back to GitHub's releases. A runner that reaches neither fails at that step, before the build. | The action reads the manifest at this URL, in the `astral-sh/versions` format, and downloads from the URLs it lists, which the organisation points at copies on its generic remote. The pinned version must be in it. Empty reads as unset. |
| GitLab, your machine, generation | Not read: the GitLab plan job installs uv with pip from the index. | Not read. |

### `inventories` in `properdocs.yml`

| Target | Kept | Dropped or rehosted |
| --- | --- | --- |
| GitLab, GitHub | `document.build` fetches the two inventories. With runner egress it works; inside the fence the fetch fails and `preflight` fails with it, because the build is part of the gate. | The build fetches nothing, or fetches the hosted copies; cross-references to the standard library and typing-extensions resolve only with the copies. |
| Your machine | The same, on `document.build` and `preflight`. | The same. |
| Generation | Not read. | Not read. |

## Minted or stored credentials

The template takes either, and one rule orders them. With the four `JFROG_*` variables set and
nothing else, every job that fetches mints its credentials from the ID token its host gives it,
and nothing is stored anywhere: GitLab mints the token through the pipeline's `default:` block,
GitHub through the Actions endpoint a job with `id-token: write` is handed. With
`INDEX_USERNAME` and `INDEX_PASSWORD` set, they are used as given and no exchange runs, which
is how a developer's own token and a project that keeps a stored secret both work. Set both and
the stored pair wins.

Wherever the credentials come from, they reach the same places: a netrc for the index host
that uv, pip and tox-uv read for the rest of the job; the builder stage of `Dockerfile.deps`
and no other stage, which `container.audit` checks by reading the image back; the base image's
registry when it is on the index host; and `UV_PUBLISH_USERNAME` and `UV_PUBLISH_PASSWORD`
beside `UV_PUBLISH_URL` when only the URL is set.

## What the organisation provides

Once per organisation, for every project under the fence. The project names what it maps to;
the repository names are the organisation's.

1. **An OIDC integration** for the host, named as `JFROG_PROVIDER` says, with the audience in
   `JFROG_AUDIENCE`.
2. **An identity mapping** from the claims of a project's ID token to the `<project>-ci` user of
   the project `JFROG_PROJECT` names, with a token lifetime that outlasts a job.
3. **A pypi remote** in front of PyPI, which `<project>-ci` reads; its simple API is
   `UV_DEFAULT_INDEX`, and on GitLab `PIP_INDEX_URL`.
4. **A docker remote** in front of `ghcr.io`, which `<project>-ci` reads, served under the index
   host by path, port or subdomain; `base-image` is edited to the name it serves the image under.
5. **A generic remote** in front of `github.com/astral-sh/python-build-standalone/releases/download`,
   which `<project>-ci` reads; its URL is `UV_PYTHON_INSTALL_MIRROR`.
6. **A local pypi repository** the project publishes to, which `<project>-ci` deploys to; its
   upload URL is `UV_PUBLISH_URL`.
7. **Only for GitLab runners inside the fence**, docker remotes in front of Docker Hub and
   gcr.io, named in `PYTHON_IMAGE` and `KANIKO_IMAGE`, with credentials for the runner in
   `DOCKER_AUTH_CONFIG`.
8. **Only for GitHub runners inside the fence**, a docker repository the deps image goes to,
   named in `DEPS_IMAGE_REGISTRY`, which `<project>-ci` deploys to and anyone inside the
   network reads without a login; and a uv version manifest hosted at `UV_MANIFEST_FILE`,
   in the `astral-sh/versions` format, pointing at copies of the uv releases on the generic
   remote.

## What no case covers

- **The advisory database.** `secure.audit` asks `pypi.org` or `osv.dev` about each package and
  pip-audit can ask nothing else. Artifactory does not proxy it. The audit needs egress to one
  of the two, or runs where it has it.
- **The docs inventories**, above: dropped or rehosted, never proxied.
- **The render hook's uv lookup.** Generation asks `pypi.org` for the newest uv to pin and falls
  back to the committed pin, saying so, when it cannot.
- **GitHub's own endpoints.** Every workflow fetches its actions from `github.com`, and a
  job that mints an ID token asks `actions.githubusercontent.com`. A self-hosted runner
  reaches both by definition, since it reaches the host it works for; they are allowances
  the organisation already has, not template variables.
- **A docker registry on a host unrelated to the index.** The index identity goes to the index
  host and its subdomains only. Artifactory does not serve docker elsewhere; a project with such
  a registry logs in by hand before it builds.

## Where the pieces are

- [Work behind a fence](../tutorials/work-behind-a-fence.md), the tutorial: the same material
  as a walk from a fenced laptop to a green pipeline and a first release.
- The generated project's *Work behind a fenced index*, under its how-to pages, rendered for
  its host with the same variables and the same list.
- [Network egress](network-egress.md), for which service every command and pipeline job
  reaches in each case.
- [ADR-0063](../../maintaining/decisions/0063-a-fenced-index-is-a-set-of-group-variables.md),
  [ADR-0064](../../maintaining/decisions/0064-every-job-that-fetches-logs-in-to-the-index.md),
  [ADR-0065](../../maintaining/decisions/0065-the-deps-build-pulls-a-fenced-base-image-with-the-index-identity.md)
  and [ADR-0066](../../maintaining/decisions/0066-github-pushes-the-deps-image-where-a-variable-says-and-pulls-it-anonymously.md),
  for why the fence is variables, why every fetching job logs in, why the base image gets the
  same identity, and where GitHub's deps image goes behind a full fence.
