"""Invariants over the GitHub workflows, the GitLab pipeline and the deps image they build."""

import inspect
import re
from pathlib import Path

import pytest
import yaml

# conftest.py wires sys.path so _CI.tasks.* is importable; pytest loads it
# before this module, which is why no path setup is needed here.
from .support import (
    ACTION_USE,
    RELEASE_DETECTION,
    REPO_ROOT,
    TEMPLATE_WORKFLOWS,
    action_pins,
    exec_from,
    fork_pair,
    github_workflows,
    load_generated_shared,
    pre_commit_hooks,
    run_commands,
    workflow_run_scripts,
)


def test_host_scaffolding_present(generated_project):
    """`.github/workflows/` ships only for github; `.gitlab-ci.yml` ships only for gitlab."""
    project, cell = generated_project
    if cell['git_hosting_service'] == 'github':
        assert (project / '.github' / 'workflows').is_dir()
        assert not (project / '.gitlab-ci.yml').exists()
    else:
        assert not (project / '.github').exists()
        assert (project / '.gitlab-ci.yml').exists()


def test_host_submodule_present(generated_project):
    """`_CI/tasks/<host>.py` is present for the chosen host and absent for the other."""
    project, cell = generated_project
    chosen_name = cell['git_hosting_service']
    other_name = 'gitlab' if chosen_name == 'github' else 'github'
    assert (project / '_CI' / 'tasks' / f'{chosen_name}.py').exists()
    assert not (project / '_CI' / 'tasks' / f'{other_name}.py').exists()


def test_pages_workflow_matches_choice(generated_project):
    """`pages.yaml` ships iff integrate_pages=true AND the host is github."""
    project, cell = generated_project
    expected = cell['integrate_pages'] and cell['git_hosting_service'] == 'github'
    assert (project / '.github' / 'workflows' / 'pages.yaml').exists() == expected


def test_pages_deploys_on_release_through_the_same_detection_as_publish(generated_project):
    """Pages deploys when a push to main carried a release, decided by `release.detect`.

    Not on a tag trigger: `release` creates no tag, the publish job does, on main. The pages
    workflow asks `release.detect` the same question `publish.yaml` asks `release.ship`, with
    the same arguments, so the package and its documentation cannot disagree about what counts
    as released. `workflow_dispatch` stays, because a project that has not released yet would
    otherwise never publish docs at all.
    """
    project, cell = generated_project
    # Pages ships for GitHub only, as `test_pages_workflow_matches_choice` asserts.
    if not cell['integrate_pages'] or cell['git_hosting_service'] != 'github':
        return
    workflows = project / '.github' / 'workflows'
    assert not (workflows / 'detect-release-tag.yaml').exists(), 'the shell tag walk is back'

    pages = yaml.safe_load((workflows / 'pages.yaml').read_text(encoding='utf-8'))
    triggers = pages.get('on') or pages[True]
    assert 'tags' not in (triggers.get('push') or {}), 'a tag trigger fires before the release merges'
    assert 'workflow_dispatch' in triggers, 'a project that has not released yet could never publish docs'

    detect = pages['jobs']['detect']
    commands = [step.get('run') for step in detect['steps'] if step.get('run')]
    assert commands == [RELEASE_DETECTION.format(task='release.detect')], f'the detect job runs {commands}'
    assert detect['outputs'] == {'tag': '${{ steps.find.outputs.tag }}', 'sha': '${{ steps.find.outputs.sha }}'}
    guard = pages['jobs']['deploy']['if']
    assert "needs.detect.outputs.tag != ''" in guard, f'pages deploys without a release: {guard!r}'
    assert 'workflow_dispatch' in guard, f'a manual run could never deploy: {guard!r}'

    publish = yaml.safe_load((workflows / 'publish.yaml').read_text(encoding='utf-8'))
    ship = [step for step in publish['jobs']['publish']['steps'] if step.get('id') == 'ship']
    assert ship, 'the publish job has no ship step'
    assert ship[0]['run'] == RELEASE_DETECTION.format(task='release.ship'), 'publish detects differently'


def test_release_detection_pins_the_commit_it_found(generated_project):
    """Pages checks out the commit `release.detect` reported, never a tag name.

    A tag is a mutable pointer, so a move between detection and checkout would publish a
    different tree than was detected. The detected commit is the new tip of main, which is
    what the publish job builds too.
    """
    project, cell = generated_project
    if cell['git_hosting_service'] != 'github' or not cell['integrate_pages']:
        return
    body = (project / '.github' / 'workflows' / 'pages.yaml').read_text(encoding='utf-8')
    assert 'ref: ${{ needs.detect.outputs.tag }}' not in body, 'pages checks out a mutable tag name'
    assert 'ref: ${{ needs.detect.outputs.sha }}' in body, 'pages does not check out the detected commit'


def test_pages_task_definition_matches_choice(generated_project):
    """`deploy_github` is defined iff integrate_pages=true AND the host is github."""
    project, cell = generated_project
    expected = cell['integrate_pages'] and cell['git_hosting_service'] == 'github'
    document_py = (project / '_CI' / 'tasks' / 'document.py').read_text(encoding='utf-8')
    assert ('def deploy_github' in document_py) == expected


def test_deps_image_tag_covers_every_content_input(generated_project):
    """The deps-image tag hashes the lockfile, the Dockerfile and the base image, not just the lock.

    Keying on `uv.lock` alone let a `Dockerfile.deps` edit or a base-image bump reuse a
    stale image, because the tag never changed.
    """
    project, _ = generated_project
    container_py = (project / '_CI' / 'tasks' / 'container.py').read_text(encoding='utf-8')
    assert 'def deps_image_tag' in container_py
    tag_source = container_py.split('def deps_image_tag', 1)[1].split('\n@task', 1)[0]
    for required in ('UV_LOCK', 'DOCKERFILE_DEPS', 'info.base-image'):
        assert required in tag_source, f'deps_image_tag() does not hash {required}'
    # Per-input digests are fixed-width, which is what stops ("AB","C") colliding
    # with ("A","BC") and what makes the algorithm reproducible in shell.
    assert 'hexdigest()' in tag_source, 'deps_image_tag() does not fold per-input digests'


def test_gitlab_deps_tag_reaches_kaniko_from_the_launcher(generated_project):
    """GitLab's kaniko job pushes to an address `container.tag` computed, and computes nothing.

    kaniko has no Python, so the job used to repeat `deps_image_tag()` in shell, pinned to
    the Python one by this test's predecessor. Now a job before it runs the launcher and hands
    the tag and the base image on as a dotenv artifact (ADR-0043); the only shell left in the
    kaniko job is the push.
    """
    project, cell = generated_project
    if cell['git_hosting_service'] != 'gitlab':
        pytest.skip('GitLab-only pipeline')
    pipeline = (project / '.gitlab-ci.yml').read_text(encoding='utf-8')
    config = yaml.safe_load(pipeline)
    plan = config['plan-deps-image']
    assert any('./workflow.cmd container.tag --output .deps-tag.env' in line for line in plan['script']), (
        f'the plan job does not run the launcher: {plan["script"]}'
    )
    assert plan['artifacts']['reports']['dotenv'] == '.deps-tag.env', 'the tag is not handed on as a dotenv artifact'
    assert plan['variables'].get('UV_NO_SYNC') == '1', 'the plan job installs every group to hash a file'
    deps = config['build-deps-image']
    assert {'job': 'plan-deps-image', 'artifacts': True} in deps['needs'], 'kaniko does not wait for the tag'
    deps_job = pipeline.split('build-deps-image:', 1)[1].split('\npreflight:', 1)[0]
    for forbidden in ('sha256sum', 'sed ', 'cut -c'):
        assert forbidden not in deps_job, f'the kaniko job still computes something with {forbidden!r}'
    assert '${CI_REGISTRY_IMAGE}:deps-${DEPS_TAG}' in deps_job, 'the kaniko job does not push to the computed tag'
    assert '--build-arg=BASE_IMAGE="$BASE_IMAGE"' in deps_job, (
        'the kaniko job does not build on the handed-on base image'
    )
    assert '--digest-file' in deps_job, 'GitLab deps job does not capture the pushed digest'
    assert 'DEPS_IMAGE=${CI_REGISTRY_IMAGE}@${DIGEST}' in deps_job, 'DEPS_IMAGE is not digest-pinned'


def test_container_tag_writes_the_dotenv_the_kaniko_job_reads(generated_project):
    """`container.tag --output` writes exactly the two keys the kaniko job substitutes."""
    project, _ = generated_project
    source = (project / '_CI' / 'tasks' / 'container.py').read_text(encoding='utf-8')
    printed = []
    helpers = exec_from(
        source,
        'tag',
        Path=Path,
        Context=object,
        task=lambda fn: fn,
        logged=lambda _name: lambda fn: fn,
        deps_image_tag=lambda: 'cafe' * 8,
        read_info=lambda _key: 'ghcr.io/astral-sh/uv:0.13.7-python3.11-trixie-slim@sha256:abc',
        print=printed.append,
    )
    helpers['tag'](None)
    assert printed == ['cafe' * 8], 'without --output the task prints something other than the bare tag'
    output = project / 'reports' / 'deps-tag.env'
    output.parent.mkdir(exist_ok=True)
    helpers['tag'](None, output=str(output))
    assert output.read_text(encoding='utf-8') == (
        f'DEPS_TAG={"cafe" * 8}\nBASE_IMAGE=ghcr.io/astral-sh/uv:0.13.7-python3.11-trixie-slim@sha256:abc\n'
    )


def test_deps_image_reference_is_digest_pinned(generated_project):
    """`container.publish` hands downstream jobs a digest, so a repointed tag can't swap the image."""
    project, cell = generated_project
    host = cell['git_hosting_service']
    host_py = (project / '_CI' / 'tasks' / f'{host}.py').read_text(encoding='utf-8')
    # Both hosts build with a daemon-based engine by hand, so both resolve the repo digest of
    # the local image. GitLab's pipeline job is the exception, and has its own test above.
    assert 'image_digest_reference' in host_py
    shared = load_generated_shared(project)
    resolver = inspect.getsource(shared.image_digest_reference)
    assert 'RepoDigests' in resolver
    # Parsed as JSON rather than via a Go --format template, which docker and
    # podman expose differently and which needs brace quoting in a shell command.
    assert 'json.loads' in resolver


def test_security_audit_is_automated_without_failing_unrelated_changes(generated_project):
    """The audit runs automatically, but never on a push that cannot have caused it.

    Two failure modes, and the fix for one is the cause of the other. Reachable only as a
    local command, the `.security-overrides` expiry mechanism gates nothing and a dependency
    with a known CVE ships green. Wired to every push, it fails pull requests for advisories
    published overnight that the author did not introduce and cannot fix in their branch —
    and a pipeline that goes red for reasons outside the author's control is one people learn
    to ignore.

    So it is automated on the axis it actually varies along: time (a schedule) and the
    dependency surface (the files that can introduce a vulnerable package). Publishing is
    gated separately by `release.dist`.
    """
    project, cell = generated_project
    # The lockfile alone. The project runs `--frozen` throughout, so a `pyproject.toml` edit
    # that changes what is installed changes `uv.lock` with it, while the edits that do not —
    # a ratchet bump, a `cz bump` — used to fire a full audit of an untouched dependency set.
    dependency_surface = {'uv.lock'}
    if cell['git_hosting_service'] == 'github':
        pipeline = (project / '.github' / 'workflows' / 'continuous-integration.yaml').read_text(encoding='utf-8')
        assert 'secure.audit' not in pipeline, 'the per-push pipeline audits every change'
        audit_workflow = yaml.safe_load(
            (project / '.github' / 'workflows' / 'security-audit.yaml').read_text(encoding='utf-8')
        )
        # yaml parses a bare `on:` key as the boolean True, hence the lookup.
        triggers = audit_workflow.get('on') or audit_workflow[True]
        paths = set(triggers['push']['paths'])
        assert dependency_surface <= paths, f'the audit is not triggered by {dependency_surface - paths}'
        assert 'pyproject.toml' not in paths, 'a version bump fires a full dependency audit'
    else:
        jobs = yaml.safe_load((project / '.gitlab-ci.yml').read_text(encoding='utf-8'))
        rules = jobs['secure']['rules']
        assert any('schedule' in str(rule.get('if', '')) for rule in rules), 'no scheduled audit'
        changes = {path for rule in rules for path in rule.get('changes') or []}
        assert dependency_surface <= changes, f'the audit is not triggered by {dependency_surface - changes}'
        assert 'pyproject.toml' not in changes, 'a version bump fires a full dependency audit'


def test_fork_pull_requests_run_the_same_gate_on_the_runners_image(generated_project):
    """A pull request from a fork runs `preflight` with the same command, on a plain runner.

    `push` covers the repository's own branches; a fork's pushes land elsewhere. `pull_request`
    covers those, but its read-only token cannot push the deps image, so the image build is
    skipped on that event and a second job installs the dependencies with uv instead. Pull
    requests from the repository's own branches run nothing on the new trigger.
    """
    project, cell = generated_project
    if cell['git_hosting_service'] != 'github':
        pytest.skip('GitHub-only workflows')
    workflow = yaml.safe_load(
        (project / '.github' / 'workflows' / 'continuous-integration.yaml').read_text(encoding='utf-8')
    )
    triggers = workflow.get('on') or workflow[True]
    assert 'pull_request' in triggers, 'a pull request from a fork runs nothing'
    assert 'push' in triggers, "the repository's own branches lost their run"
    assert "github.event_name == 'push'" in workflow['jobs']['build-deps-image']['if'], (
        'the image build runs on a pull request event, whose token cannot push it'
    )
    container, fork = fork_pair(workflow, 'preflight', 'preflight-from-fork')
    gate = next(hook for hook in pre_commit_hooks(project) if hook['id'] == 'preflight')['entry']
    assert gate in run_commands(container)
    assert gate in run_commands(fork), f'the fork job runs {run_commands(fork)}, not the gate'


def test_fork_pull_requests_touching_the_dependency_surface_are_audited(generated_project):
    """The audit's `pull_request` trigger watches the same files as its `push` trigger."""
    project, cell = generated_project
    if cell['git_hosting_service'] != 'github':
        pytest.skip('GitHub-only workflows')
    workflow = yaml.safe_load((project / '.github' / 'workflows' / 'security-audit.yaml').read_text(encoding='utf-8'))
    triggers = workflow.get('on') or workflow[True]
    assert triggers['pull_request']['paths'] == triggers['push']['paths'], 'the two path filters drifted apart'
    assert "github.event_name != 'pull_request'" in workflow['jobs']['build-deps-image']['if']
    container, fork = fork_pair(workflow, 'secure', 'secure-from-fork')
    assert run_commands(container) == ['./workflow.cmd secure.audit']
    assert './workflow.cmd secure.audit' in run_commands(fork)


def test_scheduled_security_audit_ships_for_github(generated_project):
    """GitHub projects get a scheduled audit, so expiries come due without a push."""
    project, cell = generated_project
    workflow = project / '.github' / 'workflows' / 'security-audit.yaml'
    if cell['git_hosting_service'] != 'github':
        assert not workflow.exists()
        return
    content = workflow.read_text(encoding='utf-8')
    assert 'schedule:' in content, 'the audit is not scheduled'
    assert 'cron:' in content, 'the schedule has no cron expression'
    assert 'workflow_dispatch:' in content, 'no way to trigger the audit on demand'
    assert 'secure.audit' in content
    config = yaml.safe_load(content)
    # Least privilege: the audit only reads the repo; only the image build may publish.
    assert config['permissions'] == {'contents': 'read'}
    assert config['jobs']['secure']['permissions'] == {'contents': 'read', 'packages': 'read'}


def test_this_repo_runs_tasks_only_through_the_launcher():
    """No pipeline step assembles its own invoke call; every task goes through `./workflow.cmd`.

    A hand-built `uvx --from invoke --with … invoke --search-root _CI` runs a *different*
    invoke from the one developers use: unpinned, and without the vendored copy's
    search-root patch, which is the only reason such a step needs `PYTHONPATH`. Its `--with`
    list is maintained by hand too, and once left `main` red because `configuration.py`
    imports yaml and the list had no pyyaml.
    """
    for path in sorted((REPO_ROOT / '.github' / 'workflows').glob('*.yaml')):
        workflow = yaml.safe_load(path.read_text(encoding='utf-8'))
        for label, script in workflow_run_scripts(workflow):
            assert '--from invoke' not in script, f'{path.name}:{label} installs invoke itself'
            assert '--search-root' not in script, f'{path.name}:{label} calls invoke directly'


def test_no_workflow_writes_the_token_into_a_git_remote(generated_project):
    """No workflow embeds the token in a remote URL.

    `origin` carrying `x-access-token:<token>` is what leaked a credential into the
    published SBOM; checkout now authenticates with a non-persisted header instead.
    """
    project, cell = generated_project
    if cell['git_hosting_service'] != 'github':
        pytest.skip('GitHub-only workflows')
    for name, _ in github_workflows(project):
        raw = (project / '.github' / 'workflows' / name).read_text(encoding='utf-8')
        code = '\n'.join(line for line in raw.splitlines() if not line.strip().startswith('#'))
        assert 'x-access-token' not in code, f'{name} still builds a credentialed remote URL'


def test_checkouts_do_not_persist_credentials(generated_project):
    """Every `actions/checkout` that precedes an SBOM-capable task refuses to persist auth.

    The Pages *deploy job* is the deliberate exception: `properdocs gh-deploy` pushes to the
    `gh-pages` branch and needs the credential to survive the checkout. Only that job — the
    exemption used to be written per file, which silently covered every other job in
    `pages.yaml` too, including ones added later.
    """
    project, cell = generated_project
    if cell['git_hosting_service'] != 'github':
        pytest.skip('GitHub-only workflows')
    exempt = ('pages.yaml', 'deploy')
    for name, config in github_workflows(project):
        for job_name, job in config['jobs'].items():
            for step in job.get('steps') or []:
                if not str(step.get('uses', '')).startswith('actions/checkout@'):
                    continue
                persists = (step.get('with') or {}).get('persist-credentials')
                if (name, job_name) == exempt:
                    assert persists is True, f'{name}:{job_name} cannot push gh-pages without the credential'
                    continue
                assert persists is False, f'{name}:{job_name} checkout persists credentials'


def test_every_github_job_declares_least_privilege_permissions(generated_project):
    """No job silently inherits the repository's default token scopes."""
    project, cell = generated_project
    if cell['git_hosting_service'] != 'github':
        pytest.skip('GitHub-only workflows')
    for name, config in github_workflows(project):
        for job_name, job in config['jobs'].items():
            declared = job.get('permissions') or config.get('permissions')
            assert declared, f'{name}:{job_name} inherits default token permissions'
            # Only the image build (pushes to ghcr) and the docs deploy (pushes gh-pages)
            # may mutate anything, and the publish job may write `contents` alone: that is
            # the scope the Releases API checks when `release.tag` creates the tag, and the
            # job's checkout persists no credential, so the scope reaches git only through
            # that one API call. Two write scopes are exempt everywhere because neither
            # grants access to repository contents: `id-token` mints an OIDC token for PyPI
            # Trusted Publishing, and `attestations` records a signed build-provenance
            # statement. Both produce a signature; neither can change what is in the repo.
            signing_scopes = ('id-token', 'attestations')
            allowed_writes = {'build-deps-image': None, 'deploy': None, 'publish': {'contents'}}
            if job_name in allowed_writes and allowed_writes[job_name] is None:
                continue
            writes = [
                scope
                for scope, level in declared.items()
                if level == 'write'
                and scope not in signing_scopes
                and scope not in (allowed_writes.get(job_name) or ())
            ]
            assert not writes, f'{name}:{job_name} asks for write scopes {writes}'


def test_gitlab_publish_mints_both_tokens_and_ships(generated_project):
    """The GitLab publish job requests the two OIDC audiences and hands the push to `release.ship`.

    uv reads `PYPI_ID_TOKEN` (audience `pypi`) for Trusted Publishing and `pypi-attestations`
    reads `SIGSTORE_ID_TOKEN` (audience `sigstore`) to sign. The names are derived from the
    audiences by the tools, so a renamed variable is a silent fallback to no token at all.
    The job's one command is the task: the pipeline file carries no logic of its own.
    """
    project, cell = generated_project
    if cell['git_hosting_service'] != 'gitlab':
        pytest.skip('GitLab-only pipeline')
    job = yaml.safe_load((project / '.gitlab-ci.yml').read_text(encoding='utf-8'))['publish']
    assert job['id_tokens'] == {'PYPI_ID_TOKEN': {'aud': 'pypi'}, 'SIGSTORE_ID_TOKEN': {'aud': 'sigstore'}}
    assert job['script'] == ['./workflow.cmd release.ship --before "$CI_COMMIT_BEFORE_SHA" --after "$CI_COMMIT_SHA"'], (
        f'the publish job runs {job["script"]}'
    )


def test_gitlab_publishes_only_once_the_tag_reaches_the_default_branch(generated_project):
    """The GitLab publish job runs on default-branch pushes, never on the tag push itself.

    `release` creates no tag, so a `CI_COMMIT_TAG` rule would never fire; and a tag pushed by
    hand from a branch would publish a version nobody has reviewed. The job runs on every push
    to the default branch with full history, and `release.ship` looks for a version bump among
    the pushed commits, then creates the tag there. GitHub's `publish.yaml` runs the same task.
    """
    project, cell = generated_project
    if cell['git_hosting_service'] != 'gitlab':
        pytest.skip('GitLab-only pipeline')
    job = yaml.safe_load((project / '.gitlab-ci.yml').read_text(encoding='utf-8'))['publish']
    rules = [rule.get('if', '') for rule in job['rules']]
    assert not any('CI_COMMIT_TAG' in rule for rule in rules), f'the publish job triggers on tags: {rules}'
    assert rules == ['$CI_PIPELINE_SOURCE == "push" && $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'], rules
    assert job['variables']['GIT_DEPTH'] == 0, 'the tag walk needs the full history'


def test_generated_actions_are_pinned_to_a_sha_with_a_version_comment(generated_project):
    """Every third-party action is pinned to a full commit SHA, annotated with its tag.

    A tag is a moving target: `@v6` silently becomes whatever the owner pushes next, inside a
    job holding the publish credentials. The trailing `# vX.Y.Z` is what makes a 40-character
    hex string reviewable, so it is required too.
    """
    project, cell = generated_project
    if cell['git_hosting_service'] != 'github':
        pytest.skip('GitHub-only workflows')
    for action, refs in action_pins(project / '.github' / 'workflows').items():
        for ref, places in refs.items():
            assert re.fullmatch(r'[0-9a-f]{40}', ref), f'{action} pinned to {ref!r} at {places[0]}, not a SHA'
    for path in sorted((project / '.github' / 'workflows').glob('*')):
        for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
            match = ACTION_USE.match(line)
            if match:
                assert match.group('comment'), f'{path.name}:{lineno} pins {match.group("action")} with no # vX.Y.Z'


def test_action_pins_never_drift_apart():
    """One action, one SHA — across this repository and the template it ships.

    `actions/checkout` alone appears in every workflow. Bumping the copies you happen to grep for
    and missing the rest is the failure this catches: the result still runs, so nothing else
    reports it, and the workflows quietly disagree about which version they trust. It also
    catches the parent moving ahead of the template, which would leave generated projects on
    an older action indefinitely.
    """
    combined = {}
    for directory in (REPO_ROOT / '.github' / 'workflows', TEMPLATE_WORKFLOWS):
        for action, refs in action_pins(directory).items():
            for ref, places in refs.items():
                combined.setdefault(action, {}).setdefault(ref, []).extend(places)
    assert combined, 'no pinned actions found; the workflow paths are wrong'
    for action, refs in combined.items():
        assert len(refs) == 1, f'{action} is pinned to {len(refs)} different SHAs: ' + '; '.join(
            f'{ref} at {", ".join(places)}' for ref, places in sorted(refs.items())
        )


def test_publish_job_may_write_attestations(generated_project):
    """Without `attestations: write` the attest step 403s at the end of a release."""
    project, cell = generated_project
    if cell['git_hosting_service'] != 'github':
        pytest.skip('GitHub-only workflow')
    config = yaml.safe_load((project / '.github' / 'workflows' / 'publish.yaml').read_text(encoding='utf-8'))
    permissions = config['jobs']['publish']['permissions']
    assert permissions.get('attestations') == 'write', 'publish job cannot record an attestation'
    assert permissions.get('id-token') == 'write', 'attestation signing also needs the OIDC token'


def test_deps_image_runs_as_non_root(generated_project):
    """`Dockerfile.deps` drops root and makes the venv path writable to that user."""
    project, _ = generated_project
    dockerfile = (project / 'Dockerfile.deps').read_text(encoding='utf-8')
    assert 'USER 1001' in dockerfile, 'deps image still runs as root'
    assert 'chown -R 1001:1001 /app' in dockerfile, 'uv run could not write to UV_PROJECT_ENVIRONMENT'
    assert '--create-home' in dockerfile, 'uv needs a writable HOME for its cache'
    # The uid is part of the tag inputs, so changing it cannot serve a stale image.
    container_py = (project / '_CI' / 'tasks' / 'container.py').read_text(encoding='utf-8')
    assert 'DOCKERFILE_DEPS' in container_py


def test_gitlab_credentials_are_environment_scoped(generated_project):
    """The GitLab deps job declares an environment so its registry token can be scoped."""
    project, cell = generated_project
    if cell['git_hosting_service'] != 'gitlab':
        pytest.skip('GitLab-only pipeline')
    config = yaml.safe_load((project / '.gitlab-ci.yml').read_text(encoding='utf-8'))
    assert config['build-deps-image'].get('environment'), 'deps job has no environment to scope variables to'
    assert config['publish'].get('environment') == 'pypi'


def test_no_ci_job_reruns_what_the_gate_already_covers(generated_project):
    """CI has one job for the checks, and it is the gate.

    Separate lint, test and build jobs re-ran, in a different shape, work `preflight`
    already covers — which is how a green push comes to meet a red pipeline: two lists of
    checks, one of them out of step. The cost of folding them in is the wall-clock their
    parallelism bought, not diagnosis; `run_steps` still reports every failure in one pass.
    """
    project, cell = generated_project
    duplicated = ('./workflow.cmd lint', './workflow.cmd test', './workflow.cmd build')
    if cell['git_hosting_service'] == 'github':
        pipeline = (project / '.github' / 'workflows' / 'continuous-integration.yaml').read_text(encoding='utf-8')
        jobs = set(yaml.safe_load(pipeline)['jobs'])
        # Two gate jobs, one per event shape (ADR-0041); both run the same command, which
        # `test_fork_pull_requests_run_the_same_gate_on_the_runners_image` asserts.
        assert jobs == {'build-deps-image', 'preflight', 'preflight-from-fork'}, f'the pipeline runs {jobs}'
    else:
        pipeline = (project / '.gitlab-ci.yml').read_text(encoding='utf-8')
        jobs = {name for name in yaml.safe_load(pipeline) if not name.startswith(('stages', 'variables'))}
        assert jobs == {'plan-deps-image', 'build-deps-image', 'preflight', 'secure', 'publish'}, (
            f'the pipeline runs {jobs}'
        )
    # The task name, not the whole line: `startswith` also forbade a future
    # `test.list-combos`, exact-match let `./workflow.cmd test --args=…` through, and
    # `lstrip('- ')` strips any run of those two characters rather than one list marker.
    forbidden = {command.split()[-1] for command in duplicated}
    for line in pipeline.splitlines():
        if './workflow.cmd' not in line:
            continue
        # After the comment is stripped, a line that only mentioned the launcher in prose has
        # nothing left to check.
        command = re.sub(r'^\s*-\s*', '', line.split('#', 1)[0]).strip()
        if './workflow.cmd' not in command:
            continue
        invoked = command.split('./workflow.cmd', 1)[1].split()
        task = invoked[0] if invoked else ''
        assert task not in forbidden, f'{command!r} re-runs what preflight covers'


def test_ci_runs_the_same_gate_as_the_pre_push_hook(generated_project):
    """CI's preflight job runs the identical command the pre-push hook does.

    This is the property that stops local and remote from disagreeing: a badge that is stale in
    the pipeline would have failed the push, so the pipeline is a backstop rather than the
    place you first hear about it. CI cannot commit a refresh either way — the checkout is
    credential-less and the token is read-only — so failing with the fix command is all it can
    usefully do.
    """
    project, cell = generated_project
    gate = next(hook for hook in pre_commit_hooks(project) if hook['id'] == 'preflight')
    command = gate['entry']
    if cell['git_hosting_service'] == 'github':
        workflow = yaml.safe_load(
            (project / '.github' / 'workflows' / 'continuous-integration.yaml').read_text(encoding='utf-8')
        )
        job = workflow['jobs']['preflight']
        commands = [step.get('run') for step in job['steps']]
        assert job['permissions']['contents'] == 'read', 'the preflight job can write to the repository'
    else:
        pipeline = yaml.safe_load((project / '.gitlab-ci.yml').read_text(encoding='utf-8'))
        commands = pipeline['preflight']['script']
    assert command in commands, f'no CI job runs {command!r}; it runs {commands}'
