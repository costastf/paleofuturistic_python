"""Invariants over the task modules themselves: the launcher, the shared helpers and their hygiene."""

import os
import re
import subprocess
import tomllib

import pytest

# conftest.py wires sys.path so _CI.tasks.* is importable; pytest loads it
# before this module, which is why no path setup is needed here.
from .support import (
    CREDENTIALED_URLS,
    OUTDATED_TREE,
    PINNED_PYPROJECT,
    REMOTE_URLS,
    REPO_ROOT,
    UNION_WORKAROUND_RULES,
    exec_from,
    failing,
    load_generated_shared,
    opener,
    strip_prose,
)


def test_ty_suppressions_stay_scoped_to_one_module(generated_project):
    """The py-serializable workaround must never become a project-wide rule change.

    Moving these rules to `[tool.ty.rules]` would silence them everywhere and look
    like a tidy-up in review, while quietly removing the checks most likely to catch a real
    call-signature bug across the whole project. `invalid-type-form` — the same union leaking
    into a *return* annotation — briefly rode along as a fifth rule in this same override; it
    is deliberately not one of `UNION_WORKAROUND_RULES`, because that rule is instead tagged
    per line in `sbom.py` (see below), so a config-level rule set that grows beyond this exact
    list means the fifth one has drifted back into the override rather than staying per line.
    """
    project, _ = generated_project
    ty_config = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))['tool']['ty']
    disabled_globally = UNION_WORKAROUND_RULES & set(ty_config.get('rules', {}))
    assert not disabled_globally, f'ty rules disabled project-wide: {sorted(disabled_globally)}'
    overrides = ty_config.get('overrides', [])
    assert overrides, 'no scoped ty override; the sbom.py workaround has gone missing'
    sbom_overrides = [override for override in overrides if 'sbom.py' in ','.join(override.get('include', []))]
    assert sbom_overrides, 'no ty override includes sbom.py; the workaround has gone missing'
    for override in overrides:
        assert override.get('include'), 'a ty override applies to every file, defeating the scoping'
    for override in sbom_overrides:
        rules = set(override.get('rules', {}))
        assert rules == UNION_WORKAROUND_RULES, (
            f'the sbom.py ty override covers {sorted(rules)}, not exactly the union-workaround '
            f'rules — invalid-type-form belongs per line in sbom.py, not in this config'
        )


def test_ty_ignores_in_sbom_are_scoped_to_one_rule(generated_project):
    """Every `# ty: ignore` in `sbom.py` names `invalid-type-form`, not a bare blanket ignore.

    A bare `# ty: ignore` on one of these lines would also silence `unknown-argument`,
    `missing-attribute`, `missing-union-attribute`, `too-many-positional-arguments` and
    `invalid-argument-type` on that exact line — the rules the config-level override exists to keep live everywhere
    outside constructor calls this module makes. Naming the rule keeps that promise per line.
    """
    project, _ = generated_project
    sbom_source = (project / '_CI' / 'tasks' / 'sbom.py').read_text(encoding='utf-8')
    ignore_lines = [line for line in sbom_source.splitlines() if '# ty: ignore' in line]
    assert ignore_lines, 'no ty: ignore tags found in sbom.py; did the workaround move elsewhere?'
    for line in ignore_lines:
        assert 'ty: ignore[invalid-type-form]' in line, f'a ty: ignore tag is not scoped to one rule: {line!r}'


def test_workflow_cmd_is_executable(generated_project):
    """The polyglot launcher has the executable bit so `./workflow.cmd …` works on Unix."""
    project, _ = generated_project
    assert os.access(project / 'workflow.cmd', os.X_OK)


def test_strip_credentials_removes_userinfo(generated_project):
    """`strip_credentials` drops userinfo and leaves credential-free URLs untouched."""
    project, _ = generated_project
    strip_credentials = load_generated_shared(project).strip_credentials
    for url, expected in CREDENTIALED_URLS:
        assert strip_credentials(url) == expected, f'{url!r} was not sanitized to {expected!r}'


@pytest.mark.parametrize(('url', 'host', 'path'), REMOTE_URLS)
def test_parse_remote_url_reads_host_and_path(generated_project, url, host, path):
    """The host comes from the remote, so a self-hosted instance is not mistaken for gitlab.com."""
    project, _ = generated_project
    assert load_generated_shared(project).parse_remote_url(url) == (host, path)


def test_parse_remote_url_strips_credentials(generated_project):
    """The token CI bakes into origin never reaches a parsed host or path."""
    project, _ = generated_project
    parse_remote_url = load_generated_shared(project).parse_remote_url
    ref = parse_remote_url('https://gitlab-ci-token:SECRETTOKEN@gitlab.example.com/group/project.git')
    assert ref == ('gitlab.example.com', 'group/project')
    assert 'SECRETTOKEN' not in ref.host + ref.path


def test_parse_remote_url_reports_failure_rather_than_guessing(generated_project):
    """An unparseable remote yields empty strings; callers must not invent a host."""
    project, _ = generated_project
    parse_remote_url = load_generated_shared(project).parse_remote_url
    for url in ('', 'not a url', '/local/path/repo'):
        assert parse_remote_url(url) == ('', ''), f'{url!r} was parsed into something'


def test_gitlab_helpers_never_hardcode_the_instance_host(generated_project):
    """No gitlab.com literal survives in the GitLab module — the host comes from `origin`.

    Hardcoding it made `origin_slug()` return '' on every self-hosted instance, which
    disabled the manual MR URL and the API call without printing anything.
    """
    project, cell = generated_project
    if cell['git_hosting_service'] != 'gitlab':
        pytest.skip('github combo')
    gitlab_py = (project / '_CI' / 'tasks' / 'gitlab.py').read_text(encoding='utf-8')
    assert 'gitlab.com' not in strip_prose(gitlab_py), 'the GitLab instance host is still hardcoded'


def test_the_launcher_stays_executable():
    """`./workflow.cmd` is committed with its executable bit, or every pipeline step 126s."""
    mode = subprocess.run(
        ['git', 'ls-files', '--stage', 'workflow.cmd'],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()[0]
    assert mode == '100755', f'workflow.cmd is committed as {mode}, not executable'


@pytest.mark.parametrize(
    ('system', 'expected'),
    [('macos', 'open site/index.html'), ('linux', 'xdg-open site/index.html'), ('windows', 'start site/index.html')],
)
def test_open_target_keeps_strict_failure_off_wsl(generated_project, system, expected):
    """macOS, Linux and Windows keep the pre-existing command and keep failing loudly."""
    project, _ = generated_project
    ran, executed = opener(project, system)
    assert executed == [expected], f'{system} should go through execute() so a failure fails the task'
    assert ran == []


def test_open_target_uses_wslview_when_still_installed(generated_project):
    """An existing `wslu` install keeps working, rather than being bypassed."""
    project, _ = generated_project
    ran, executed = opener(project, 'wsl', has_wslview=True, interop=True)
    assert ran == ['wslview "site/index.html"']
    assert executed == [], 'WSL must not use execute(): the Windows helpers exit non-zero on success'


def test_open_target_hands_a_translated_path_to_windows(generated_project):
    """Without `wslview`, the path is translated with `wslpath -w` and opened via cmd.exe.

    Both details are load-bearing: Windows cannot resolve a Linux path, and `start`
    needs its empty window-title argument or it treats the quoted path as a title and
    opens nothing.
    """
    project, _ = generated_project
    ran, executed = opener(project, 'wsl', interop=True)
    assert ran[0] == 'wslpath -w "site/index.html"'
    assert ran[1] == "cmd.exe /c start '' '\\\\wsl.localhost\\Ubuntu\\home\\me\\site\\index.html'"
    assert executed == []


def test_open_target_degrades_when_wsl_interop_is_disabled(generated_project):
    """A distro with interop off gets a message, not a traceback or a failed task."""
    project, _ = generated_project
    ran, executed = opener(project, 'wsl', interop=False)
    assert ran == [], f'unexpected run() calls: {ran}'
    assert executed == [], f'unexpected execute() calls: {executed}'


def test_no_task_still_depends_on_wslu(generated_project):
    """Nothing tells the user to install the deprecated `wslu` package, or shells out to it blindly."""
    project, _ = generated_project
    for name in ('shared.py', 'document.py', 'test.py', 'quality.py'):
        source = (project / '_CI' / 'tasks' / name).read_text(encoding='utf-8')
        assert 'install the wslu' not in source, f'{name} still recommends the deprecated wslu package'
        assert 'open_command' not in source, f'{name} still uses the removed open_command()'


def test_refresh_deps_moves_every_exact_pin_except_uv(generated_project):
    """`develop.refresh-deps` rewrites the pins `uv tree --outdated` names, and never uv's.

    The newest version comes from uv under the boundary just set, so a pin cannot move past
    it. uv's own pin is tied to the base image's digest and belongs to `develop.bump-uv`
    (ADR-0042). Extras survive, names compare the way PyPI compares them, and the build
    backend's range is not an exact pin, so it is not touched.
    """
    project, _ = generated_project
    source = (project / '_CI' / 'tasks' / 'develop.py').read_text(encoding='utf-8')
    helpers = exec_from(source, 'canonical', 'outdated_pins', 'move_pins', 'PIN', 'OUTDATED', 'HELD_BACK', re=re)
    latest = helpers['outdated_pins'](OUTDATED_TREE)
    assert latest == {'ty': '0.0.101', 'uv': '0.13.9', 'validate-pyproject': '0.28', 'pytest-env': '1.9.0'}
    content, moved = helpers['move_pins'](PINNED_PYPROJECT, latest)
    assert moved == [
        ('ty', '0.0.100', '0.0.101'),
        ('validate-pyproject', '0.27', '0.28'),
        ('pytest-env', '1.8.5', '1.9.0'),
    ]
    assert '"ty==0.0.101",' in content
    assert '"validate-pyproject[all]==0.28",' in content, 'the extras were lost'
    assert '"pytest-env==1.9.0",' in content, 'the name was not compared the way PyPI compares it'
    assert '"ruff==0.17.4",' in content, 'a current pin moved'
    assert '"uv==0.13.7",  # moves with develop.bump-uv' in content, 'the uv pin moved, leaving the image digest behind'
    assert 'requires = ["uv_build>=0.8.15,<=0.13.7"]' in content, 'the build backend range was rewritten'
    assert '# Newest version clearing the [tool.uv] exclude-newer boundary.' in content
    assert helpers['HELD_BACK'] == frozenset({'uv'})
    # The task says a newer uv exists rather than taking it; the body spells the hand-off.
    body = source.split('def refresh_deps', 1)[1].split('\n@task', 1)[0]
    assert 'develop.bump-uv' in body, 'a held-back uv is not pointed at the task that moves it'
    assert 'uv lock --upgrade' in body, 'the transitive closure is not re-resolved'
    assert 'preflight' in body, 'the task does not say what has to pass before the commit'


def test_task_output_stays_in_order_when_redirected(generated_project):
    """The streams are line-buffered, so a log read after the fact attributes output correctly.

    Python block-buffers stdout when it is not a terminal — which is every CI log and every
    `> run.log` — while a subprocess invoke spawns writes to the same descriptor immediately.
    Our own lines therefore arrived in chunks *after* the command they introduce, so the
    echoed command sat below its own output and a task's prints appeared under the previous
    task's command. `Wrote SBOM to …` reading as though `uv run coverage json` had produced it
    is what that looked like, and the SBOM tasks have no command of their own to echo, so
    nothing contradicted the impression.
    """
    project, _ = generated_project
    shared = (project / '_CI' / 'tasks' / 'shared.py').read_text(encoding='utf-8')
    assert 'line_buffering=True' in shared, 'the streams are block-buffered again when redirected'


def test_importing_a_task_module_does_not_cost_a_second(generated_project):
    """The SBOM composer is imported by the tasks that compose one, not at module scope.

    `cyclonedx.validation.json` reaches `jsonschema._format` and a lark grammar built at
    import time: 1.0s, measured, of the 1.2s `_CI/tasks/sbom.py` costs to import. `build`
    imports `secure` imports `sbom`, so every `./workflow.cmd` paid it — `format`, `lint`, the
    commit hook, `--list`. Deferring it took `--list` from 1.37s to 0.15s.
    """
    project, _ = generated_project
    tasks = project / '_CI' / 'tasks'
    secure = (tasks / 'secure.py').read_text(encoding='utf-8')
    module_scope = secure.split('\n@task', 1)[0]
    assert 'from .sbom import' not in module_scope, 'importing secure.py pays for cyclonedx again'
    # Every module, not just `secure.py`: any of them importing `.sbom` at module scope brings
    # the cost back, since `preflight` imports most of them.
    for module in sorted(tasks.glob('*.py')):
        if module.name == 'sbom.py':
            continue
        head = module.read_text(encoding='utf-8').split('\ndef ', 1)[0].split('\n@', 1)[0]
        assert 'from .sbom import' not in head, f'{module.name} imports the SBOM composer at module scope'
        assert 'import cyclonedx' not in head, f'{module.name} imports cyclonedx at module scope'
    sbom = (tasks / 'sbom.py').read_text(encoding='utf-8')
    assert 'from cyclonedx.validation' not in sbom.split('\ndef ', 1)[0], (
        'the JSON validator is imported before anything validates'
    )


def test_a_tool_that_fails_ends_the_run(generated_project):
    """`execute` raises `SystemExit` when the command it ran failed.

    Every task in the workflow runs every tool through this one function, so without the raise
    ruff, pylint, ty, the matrix and the wheel build all pass unconditionally. Two tokens —
    this and `run_scope`'s exit — make the whole gate decorative: a mutation sweep found both
    surviving, and on a rendered project the mutated gate printed
    "❌ preflight.artifacts failed" and then exited 0.

    Guarded by execution because that is what the identical mutation in
    `execute_with_retries` is guarded by; the same edit on the function every other failure
    passes through was invisible.
    """
    project, _ = generated_project
    source = (project / '_CI' / 'tasks' / 'shared.py').read_text(encoding='utf-8')
    execute = exec_from(source, 'execute', os=os, Context=object)['execute']

    with pytest.raises(SystemExit):
        execute(failing(), 'ruff check')
    execute(failing(failed=False), 'ruff check')


def test_local_task_module_ships_with_a_namespace(generated_project):
    """`_CI/tasks/local.py` ships and exposes a `local` collection ready to add tasks to."""
    project, _ = generated_project
    local = project / '_CI' / 'tasks' / 'local.py'
    assert local.is_file(), 'no project-owned task module ships'
    source = local.read_text(encoding='utf-8')
    assert "Collection('local')" in source, 'local.py defines no namespace for __init__ to pick up'


def test_local_tasks_need_no_registration(generated_project):
    """`__init__.py` discovers `local.py` itself, so adding a task never edits template files.

    Registration used to mean editing `__init__.py` and its bootstrap loop — both
    template-owned, so every local task cost a merge conflict on every update.
    """
    project, _ = generated_project
    init = (project / '_CI' / 'tasks' / '__init__.py').read_text(encoding='utf-8')
    assert 'LOCAL_MODULE' in init, 'local.py is not referenced by __init__'
    assert 'is_file()' in init, 'local.py is imported unconditionally, so its absence would break'
    assert 'local.namespace' in init, 'the local namespace is never added'
    assert 'modules.append(local)' in init, 'local tasks would not get the bootstrap pre-task'


def test_launcher_dispatch_is_intact(generated_project):
    """The launcher execs on the sh line so the cmd line is unreachable from a POSIX shell.

    Without `exec`, sh would fall through and try to run the Windows line as a command.
    """
    project, _ = generated_project
    lines = [line.strip() for line in (project / 'workflow.cmd').read_text(encoding='utf-8').splitlines()]
    posix = next(line for line in lines if line.startswith(': ;'))
    assert 'exec ' in posix, 'sh would fall through to the Windows line'
    assert posix.startswith(': ;'), 'cmd relies on this line reading as a label'
    assert '--search-root _CI' in posix
