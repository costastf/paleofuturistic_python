"""Invariants over the QA gate: the preflight registry, the hooks, the badges and the coverage scope."""

import ast
import os
import re
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

# conftest.py wires sys.path so _CI.tasks.* is importable; pytest loads it
# before this module, which is why no path setup is needed here.
from _CI.tasks.configuration import (
    matrix_combos,
)

from .support import (
    STAGEABLE_PATHS,
    calls_in,
    command_strings,
    commits_in,
    exec_from,
    function_named,
    git,
    hook_stages,
    invoked_task,
    per_file_step_filters,
    pre_commit_hooks,
    range_resolver,
    registry_steps,
)


def test_ratchet_defaults_to_auto_detect(generated_project):
    """`[tool.test-ratchet] mode = "auto-detect"` ships by default so the ratchet starts dormant."""
    project, _ = generated_project
    data = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    assert data['tool']['test-ratchet']['mode'] == 'auto-detect'


def test_scaffold_test_sanity_marker_present(generated_project):
    """`def test_sanity` ships in the scaffolded test file — it doubles as the ratchet dormancy marker."""
    project, _ = generated_project
    slug = project.name
    test_file = project / 'tests' / f'test_{slug}.py'
    assert 'def test_sanity' in test_file.read_text(encoding='utf-8')


def test_pyproject_validation_is_a_per_file_gate_and_part_of_lint(generated_project):
    """validate-pyproject runs from the commit hook, `preflight`, and the `lint` aggregator."""
    project, _ = generated_project
    assert registry_steps(project).get('pyproject') == 'PER_FILE', 'pyproject validation is not a per-file step'
    lint_py = (project / '_CI' / 'tasks' / 'lint.py').read_text(encoding='utf-8')
    aggregator = re.search(r'run_steps\(([^)]*)\)\(context\)', lint_py)
    assert aggregator, 'lint.py has no run_steps aggregator'
    assert 'pyproject' in aggregator.group(1).split(', '), 'the lint aggregator skips pyproject validation'
    assert "'uv run validate-pyproject" in lint_py


def test_commit_stage_is_one_invocation_of_the_per_file_steps(generated_project):
    """The commit stage runs the staged bundle in a single `./workflow.cmd` invocation.

    Each invocation costs ~1.3s of interpreter and import startup before a tool runs, so the
    six hooks this replaced spent most of a commit's budget starting up: ~8s of startup to do
    ~2s of checking. One hook pays it once, which is what keeps the stage worth leaving on.
    """
    project, _ = generated_project
    code_hooks = [
        hook for hook in pre_commit_hooks(project) if 'pre-commit' in hook_stages(hook) and invoked_task(hook)
    ]
    invoked = sorted(invoked_task(hook) for hook in code_hooks)
    assert invoked == ['preflight.staged', 'secure.validate-overrides'], (
        f'the commit stage runs {invoked}, so it no longer pays startup exactly once for the code checks'
    )
    staged = next(hook for hook in code_hooks if invoked_task(hook) == 'preflight.staged')
    # No filenames and no wrapper: the task reads the index itself, so this entry is the same
    # command a person would type. Handing over the list needed `sh -c … --paths="$*"`, since
    # Invoke reads a bare second filename as another task name.
    assert staged.get('pass_filenames') is False, 'the hook hands over a file list again'
    assert staged['entry'] == './workflow.cmd preflight.staged', (
        f'the entry is not the bare command: {staged["entry"]!r}'
    )


def test_commit_stage_filter_is_the_union_of_the_steps_it_runs(generated_project):
    """The one remaining `files:` filter wakes the hook for exactly the files some step reads.

    Collapsing six hooks into one left a single `files:` key in front of tools that do not
    agree on what they check — complexipy is `src/` only, the pyproject check reads one file,
    the rest cover `_CI/tasks/`, `src/` and `tests/`. The per-tool filters live in the registry,
    and this pattern decides only whether the hook *wakes*. Narrower than the union, and staging
    a file some step cares about leaves the hook skipped and the file unchecked; wider, and
    every commit of an unrelated file pays the startup for nothing.
    """
    project, _ = generated_project
    filters = per_file_step_filters(project)
    assert filters, 'the registry declares no per-file steps'
    staged = next(hook for hook in pre_commit_hooks(project) if invoked_task(hook) == 'preflight.staged')
    hook_filter = re.compile(staged['files'])
    for path in STAGEABLE_PATHS:
        readers = sorted(name for name, pattern in filters.items() if pattern.search(path))
        wakes = bool(hook_filter.search(path))
        assert wakes == bool(readers), (
            f'{path!r}: the hook {"wakes" if wakes else "sleeps"} but the steps that read it are {readers}'
        )
    accepted = {name for name, pattern in filters.items() if any(pattern.search(p) for p in STAGEABLE_PATHS)}
    assert accepted == set(filters), f'per-file steps no probe path exercises: {sorted(set(filters) - accepted)}'


def test_whole_program_steps_are_never_scoped_to_a_diff(generated_project):
    """ty, commitizen, pyscn, tox, build and artifacts are whole-program, so never run at commit stage.

    ty: a changed signature fails in the *callers*, which a narrowed run never looks at.
    pyscn: dead code and duplicate blocks are relationships between files.
    tox: a passing changed test says nothing about the ones it broke, on any interpreter.
    build: a wheel is built from the whole tree or not at all.

    Their cost also scales with the size of the project rather than of the change, which is
    what would have made commits slower and slower as the project grew.
    """
    project, _ = generated_project
    steps = registry_steps(project)
    for name in ('ty', 'commitizen', 'pyscn', 'tox', 'build', 'artifacts'):
        assert steps.get(name) == 'WHOLE_PROGRAM', f'{name} is declared {steps.get(name)!r}, not whole-program'
    commit_stage = {invoked_task(hook) for hook in pre_commit_hooks(project) if 'pre-commit' in hook_stages(hook)}
    assert 'preflight' not in commit_stage, 'the whole-program bundle runs on every commit'


def test_path_taking_tasks_accept_a_paths_argument(generated_project):
    """The tasks the hooks scope actually take `--paths`, and fall back to the project paths."""
    project, _ = generated_project
    lint_py = (project / '_CI' / 'tasks' / 'lint.py').read_text(encoding='utf-8')
    format_py = (project / '_CI' / 'tasks' / 'format_.py').read_text(encoding='utf-8')
    for name, source in (('lint.py', lint_py), ('format_.py', format_py)):
        # A hardcoded `@run(f'… {PATHS}')` cannot be narrowed: it is baked at import time.
        assert '@run(' not in source, f'{name} still builds its command at import time'
    for signature in ('def ruff_lint(context: Context, paths: str', 'def pylint(context: Context, paths: str'):
        assert signature in lint_py, f'missing {signature!r}'
    assert 'def format_(context: Context, paths: str' in format_py, 'the format aggregator cannot forward paths'
    assert 'paths or PATHS' in lint_py, 'lint tasks do not fall back to the project-wide paths'


def test_whole_program_gate_runs_on_pre_push_without_writing(generated_project):
    """The whole-program bundle gates pushes, not commits, and writes nothing tracked.

    It needs no flag to be safe: `preflight` verifies by default and `--write` is opt-in, which
    is the point of that inversion — the hook, the pipeline, and the command you type to
    reproduce a failure are all the same string.
    """
    project, _ = generated_project
    hooks = {hook['id']: hook for hook in pre_commit_hooks(project)}
    gate = hooks['preflight']
    assert gate['stages'] == ['pre-push'], f'preflight hook stages are {gate["stages"]}'
    assert invoked_task(gate) == 'preflight', f'preflight hook runs {gate["entry"]!r}'
    assert '--write' not in gate['entry'], f'the pre-push hook would rewrite tracked files: {gate["entry"]!r}'
    # No `files:` either. `preflight` verifies README.md and pyproject.toml, so a filter over
    # source paths would skip the gate on a push carrying only those — which is exactly what
    # the recovery loop produces: `--write`, then commit the badges. CI would still run it.
    assert 'files' not in gate, f'the pre-push gate is narrowed and can be skipped: {gate.get("files")!r}'
    assert gate.get('pass_filenames') is False, 'the whole-program gate was narrowed to the pushed files'
    installed = yaml.safe_load((project / '.pre-commit-config.yaml').read_text(encoding='utf-8'))
    assert 'pre-push' in installed['default_install_hook_types'], 'pre-push hooks would never be installed'


def test_the_coverage_floor_is_enforced_where_it_was_measured(generated_project):
    """`fail_under` is enforced once, over the combined data, and nowhere else.

    The ratchet sets the floor from coverage combined across the matrix, and no single env can
    reach a union figure — a `sys.version_info` branch has one arm unreachable per interpreter
    by construction. pytest-cov enforcing the same floor per env therefore deadlocks a project:
    the ratchet bumps to the union, every env then fails below it, and the ratchet only moves
    up. Reproduced end to end before this: 100% combined, 84.62% per env, no way out but
    editing `fail_under` by hand.

    So every per-interpreter reporter passes `--fail-under=0`, and `combine_coverage`'s
    `coverage json` over the combined data is the single enforcement point. Correctness rests on
    every present and future call site opting out, which is a rule about call sites rather than
    about configuration — hence the walk over all of them rather than a check of the two the
    deadlock happened to involve.
    """
    project, _ = generated_project
    data = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    addopts = data['tool']['pytest']['ini_options']['addopts']
    assert '--cov' in addopts
    assert '--cov-fail-under=0' in addopts, 'pytest-cov enforces a union floor per interpreter'
    assert 'fail_under' in data['tool']['coverage']['report']

    test_py = (project / '_CI' / 'tasks' / 'test.py').read_text(encoding='utf-8')
    combine = test_py.split('def combine_coverage', 1)[1].split('\n@', 1)[0]
    # Command lines, not any line mentioning the command: the comments here discuss
    # `coverage json` too, and an earlier version of this test inspected one of those and
    # passed for that reason.
    union_writes = [line for line in combine.splitlines() if 'coverage json -o' in line and '{COVERAGE_REPORT}' in line]
    enforcing = [line.strip() for line in union_writes if '--fail-under' not in line]
    assert len(enforcing) == 1, f'the floor is enforced by {len(enforcing)} commands, not one: {enforcing}'

    reads = [
        line.strip()
        for line in test_py.splitlines()
        if re.search(r'uv run coverage (report|json|html)', line) and line.strip() not in enforcing
    ]
    assert reads, 'no coverage commands left to check, so this walk has stopped walking'
    for command in reads:
        assert '--fail-under=0' in command, f'{command} is gated by a floor its data cannot clear'

    # And the floor cannot drift by the gate and the task measuring different things: both run
    # the same tox task, and the `test` aggregator the same pytest task.
    aggregator = test_py.split("@logged('test')", 1)[1]
    assert 'run_steps(pytest)' in aggregator, 'the aggregator no longer delegates to the same pytest task'
    assert 'tox' in registry_steps(project), 'the registry no longer runs the matrix'
    preflight_py = (project / '_CI' / 'tasks' / 'preflight.py').read_text(encoding='utf-8')
    imported_from_test = preflight_py.split('from .test import', 1)[1].split('\n', 1)[0]
    assert 'tox' in imported_from_test, (
        'the registry no longer runs the shared tox task, so the floor it enforces can drift'
    )


def test_the_gate_offers_no_way_to_run_less_than_ci(generated_project):
    """`preflight` takes no flag that trims what it runs, because CI runs this same command.

    A `--quick` that dropped the matrix would be a documented way to make local and CI
    disagree, and the obvious thing to reach for in a hurry. The knob that shortens the matrix
    is `env_list`, which shortens it for CI too and so cannot open a gap. The two flags it does
    take add rather than remove: `--write` updates the derived files, and `--audit-dependencies`
    runs a step no gate runs anywhere.
    """
    project, _ = generated_project
    preflight_py = (project / '_CI' / 'tasks' / 'preflight.py').read_text(encoding='utf-8')
    signature = preflight_py.split('def preflight(', 1)[1].split(')', 1)[0]
    parameters = {part.split(':')[0].strip() for part in signature.split(',')}
    assert parameters == {'context', 'write', 'audit_dependencies'}, (
        f'preflight grew a parameter that can change what it runs: {parameters}'
    )


def test_a_failing_run_writes_no_derived_values(generated_project):
    """Once a check has failed, the steps that write derived files are skipped.

    Every step otherwise runs even after one fails, so a single run reports everything that is
    wrong. That is right for reporting and wrong for writing: a badge computed from a tree
    whose checks just failed is a claim the tree does not support. Before this, `preflight`
    would print "Updated build badge to passing" on a run that went on to fail, and write a
    grade-A pyscn badge over a project whose tests were red — the aggregator it replaced
    short-circuited instead, so this restores a property the template already had.

    Skipped rather than reordered, so a late failure cannot retroactively undo an earlier
    write, and `secure.audit` being last means an advisory does not stop a badge from updating.
    """
    project, _ = generated_project
    source = (project / '_CI' / 'tasks' / 'preflight.py').read_text(encoding='utf-8')
    body = source.split('def run_scope', 1)[1]
    assert 'if failed and derived' in body, 'a failing run can still write derived values'
    # The writers have to be last for the skip to cover them; `artifacts` is the final
    # non-network step, and `build`'s badge precedes it.
    steps = list(registry_steps(project))
    assert steps[-1] == 'audit', f'audit is no longer last, so its failure would skip the writers: {steps}'
    assert steps[-2] == 'artifacts', f'artifacts is not the last checked step: {steps}'


def test_no_automated_run_edits_source(generated_project):
    """Nothing in the registry can write source — there is no step that could.

    The commit hook used to apply formatting. That made the automated entry points behave
    differently from the command a person types, and it rewrote the *worktree* while git was
    mid-commit, which suits a partially staged file badly: the formatter rewrites the whole
    file, hunks deliberately left out of the index included. Reporting and naming
    `./workflow.cmd format` costs one command and owns neither problem.

    So the property is now absolute rather than conditional, and this asserts the absence of
    the machinery rather than its correct use: no step declares a source-writing variant, and
    the concept of "fixing" is gone from the module.
    """
    project, _ = generated_project
    source = (project / '_CI' / 'tasks' / 'preflight.py').read_text(encoding='utf-8')
    assert 'fixes_source' not in source, 'a step can write source again'
    assert 'ruff_format' not in source, 'the registry reaches the formatter again'

    # Every write variant in the registry produces a derived file, which is what `--write` is
    # for; `plan_scope` marks exactly those so a failing run can skip them.
    assert 'derived = step.write is not None' in source, 'the plan no longer marks which steps produce derived files'

    # And the hook asks for no fixing, because there is nothing to ask for.
    hook = next(h for h in pre_commit_hooks(project) if invoked_task(h) == 'preflight.staged')
    assert '--fix' not in hook['entry'], f'the commit hook rewrites files again: {hook["entry"]!r}'


def test_running_the_hooks_by_hand_matches_what_git_will_do(generated_project):
    """`develop.pre-commit` runs the hooks exactly as git will, with nothing to widen.

    It passed `--all-files` unconditionally, so the command behaved differently from the hook it
    is named after. The flag then survived as an option, which was worse: the staged bundle
    passes no filenames and reads the index instead, so `pre-commit run --all-files` printed
    "Nothing staged" and exited 0 — a whole-tree check that checked nothing. `preflight` is the
    command that covers every file.
    """
    project, _ = generated_project
    develop = (project / '_CI' / 'tasks' / 'develop.py').read_text(encoding='utf-8')
    body = develop.split("@logged('develop.pre-commit')", 1)[1].split('@task', 1)[0]
    assert "'uv run pre-commit run'" in body, 'the default no longer runs the hooks on staged files'
    # Past the docstring, which explains the flag's absence.
    code = body.split('"""', 2)[2]
    assert '--all-files' not in code, 'a widening flag is back, and it still cannot widen'


def test_the_staged_bundle_defaults_to_what_is_staged(generated_project):
    """`preflight.staged` with no paths checks the index, not the whole project.

    It used to fall back to every project path, so typing the command by hand swept everything
    — the opposite of what its name promises. The hook passes no filenames either: it invokes
    the bare command, so what the hook checks and what you check are the same list, read from
    the same place.
    """
    project, _ = generated_project
    source = (project / '_CI' / 'tasks' / 'preflight.py').read_text(encoding='utf-8')
    body = source.split("@logged('preflight.staged')", 1)[1].split('@task', 1)[0]
    assert re.search(r'paths\s+or\s+staged_files\(', body), 'an explicit --paths no longer wins'
    assert 'Nothing staged' in body, 'an empty index is not reported'

    # A space in a staged path has to fail loudly: `--paths` is space-separated the whole way
    # down, so such a path would otherwise split into fragments that match no step's filter and
    # be dropped, leaving the hook to pass because it checked nothing at all.
    reader = source.split('def staged_files', 1)[1].split('\ndef ', 1)[0]
    assert 'git diff --cached --name-only' in reader, 'the staged bundle no longer reads the index'
    assert 'splitlines()' in reader, 'the index is split on whitespace, so a path with a space breaks up'
    assert 'unsupported' in reader, 'a staged path containing a space is not refused'
    assert '--diff-filter=ACMR' in reader, 'a staged deletion is handed to a tool as a path'


def test_the_gate_renders_no_report_it_does_not_read(generated_project):
    """`preflight` produces the JSON its derived values need, and no browsable report.

    The rule, applied the same way to both tools that offer one. pyscn allows a single output
    format per run, so an HTML report there costs a whole second analysis; coverage renders one
    from data it already has, for a fraction of a second. Different prices, same answer —
    nothing in a hook or a pipeline opens an HTML report, and a gate that produces artefacts
    for an absent reader is a gate doing work nobody asked for. Two tools behaving alike in the
    pipeline is worth more than the fraction of a second.

    The reports are not lost, they are moved to where someone is actually looking:
    `quality.pyscn-analyze` produces the pyscn HTML and opens it, and `test.coverage` renders
    the coverage HTML from whatever the last run measured.
    """
    project, _ = generated_project
    tasks = project / '_CI' / 'tasks'
    gate_pyscn = (tasks / 'quality.py').read_text(encoding='utf-8').split('def pyscn_json_report', 1)[1]
    gate_pyscn = gate_pyscn.split('\n@', 1)[0]
    assert 'ANALYZE_JSON' in gate_pyscn, 'the gate no longer produces the JSON the badge reads'
    assert 'ANALYZE_HTML' not in gate_pyscn, 'the gate produces a pyscn HTML report nothing reads'

    test_py = (tasks / 'test.py').read_text(encoding='utf-8')
    gate_coverage = test_py.split('def combine_coverage', 1)[1].split('\n@', 1)[0]
    assert 'coverage json' in gate_coverage, 'the gate no longer produces the JSON the badge reads'
    assert 'coverage html' not in gate_coverage, 'the gate renders a coverage HTML report nothing reads'

    on_demand = test_py.split("@logged('test.coverage')", 1)[1].split('\n@task', 1)[0]
    assert 'coverage html' in on_demand, 'nothing renders the combined coverage report any more'


def test_pyscn_never_opens_a_browser_by_itself(generated_project):
    """Every pyscn run that writes HTML passes `--no-open`.

    pyscn launches a browser as soon as it writes an HTML report — verified with a stub
    `xdg-open`, which fires once for a bare `analyze` and not at all with `--no-open`. That
    made `quality.pyscn-analyze` open the report twice, once by itself and once from its own
    deliberate `open_target`, and made `pyscn_analyze_only` — "without opening the report" —
    open one anyway. It also had a tool reaching for a browser on a CI runner, where
    `is_ci()` exists precisely to prevent that.

    Whether a report is worth opening is the task's call, not the tool's.
    """
    project, _ = generated_project
    quality_py = (project / '_CI' / 'tasks' / 'quality.py').read_text(encoding='utf-8')
    # Command strings only — prose about `pyscn analyze` is not an invocation of it.
    html_runs = [line for line in quality_py.splitlines() if 'uv run pyscn analyze' in line and '--json' not in line]
    assert html_runs, 'no pyscn invocation produces an HTML report any more'
    for line in html_runs:
        assert '--no-open' in line, f'{line.strip()!r} lets pyscn open a browser on its own'


def test_the_docs_build_is_in_the_gate_and_early_in_it(generated_project):
    """`properdocs build --strict` runs on every push, before the expensive steps.

    A broken cross-reference or a page missing from the nav fails `--strict`, and publishing
    happens on a release tag — so without this step the first run that sees a bad link is the
    release pipeline, after the tag is pushed, which is the one moment there is no cheap way
    back.

    Ordering is the other half. `run_scope` runs every step regardless of failure, so the
    registry's order is all that decides how long a verdict takes: the docs build costs 1.3s
    and the steps after it cost twelve, so a bad link is reported at 1.7s of a 13.8s run rather
    than at 6.3s. pylint moved behind it for the same reason — five of those twelve seconds are
    pylint's, and everything cheaper that can also fail should have spoken first.
    """
    project, _ = generated_project
    order = list(registry_steps(project))
    assert registry_steps(project).get('docs') == 'WHOLE_PROGRAM', 'the docs build is in no gate'
    document = (project / '_CI' / 'tasks' / 'document.py').read_text(encoding='utf-8')
    assert '--strict' in document, 'the docs build tolerates a broken link'
    for earlier, later in (('docs', 'pyscn'), ('docs', 'tox'), ('docs', 'build'), ('complexipy', 'pylint')):
        assert order.index(earlier) < order.index(later), (
            f'{earlier!r} now runs after {later!r}, so its verdict waits for a slower step'
        )


def test_a_report_a_reader_would_misread_is_cleared_first(generated_project):
    """Reports from a previous run do not survive into this one, pyscn's included.

    pyscn timestamps every report, so nothing overwrites anything and `reports/` grows for as
    long as the project runs its gate. Clearing also decides what an early failure means: with
    the directory empty the badge reports that it has no grade to read, instead of certifying
    one measured against a tree that has since changed. The per-env coverage reports go the
    same way, and for one more reason — named after an env, one from a dropped `env_list`
    entry would sit in `reports/` looking like a result from this run.
    """
    project, _ = generated_project
    quality = (project / '_CI' / 'tasks' / 'quality.py').read_text(encoding='utf-8')
    for name in ('analyze', 'pyscn_json_report'):
        body = quality.split(f'\ndef {name}(', 1)[1].split('\ndef ', 1)[0]
        assert 'clear_pyscn_reports()' in body, f'{name} can read a report from a previous run'
    # The two analysis tasks share `analyze`, so the clearing above covers both.
    for name in ('pyscn_analyze', 'pyscn_analyze_only'):
        body = quality.split(f'\ndef {name}(', 1)[1].split('\ndef ', 1)[0]
        assert 'analyze(context, write=write)' in body, f'{name} no longer runs the shared analysis'
    test_py = (project / '_CI' / 'tasks' / 'test.py').read_text(encoding='utf-8')
    erase = test_py.split('def erase_coverage_data', 1)[1].split('\ndef ', 1)[0]
    assert "Path('reports').glob('coverage.*.json')" in erase, 'a retired env keeps its report'


def test_a_derived_value_that_cannot_be_written_fails_the_write(generated_project):
    """`preflight --write` exits non-zero when a value survives the writing.

    A reason survives `--write` only when the value could not be computed at all — its report
    missing, or unreadable. "Wrote nothing, exited 0" is the shape that lets a stale badge
    reach main through the command meant to refresh it, so both modes fail on it and only the
    hint about which command to run differs.
    """
    project, _ = generated_project
    source = (project / '_CI' / 'tasks' / 'preflight.py').read_text(encoding='utf-8')
    body = source.split('def artifacts', 1)[1].split('\nSTEPS', 1)[0]
    tail = body.split('for reason in reasons:', 1)[1]
    assert 'if not write:' in tail, 'both modes print the same hint'
    fix_hint, exit_call = tail.index('FIX_COMMAND'), tail.index('raise SystemExit(1)')
    assert fix_hint < exit_call, 'the hint comes after the exit, so nobody reads it'
    assert tail.split('raise SystemExit(1)')[0].count('if ') == 1, 'the exit is conditional again'


def test_a_badge_the_reader_removed_is_reported_not_assumed(generated_project):
    """A pattern that matches nothing says so, rather than reading as up to date.

    `re.sub` cannot tell "already correct" from "not there": both leave the content
    unchanged. So deleting or renaming a badge silently retired the check that guarded it,
    and the gate went on passing with one fewer thing to verify. Removing a badge stays the
    reader's decision — this workflow does not put it back — but it is said out loud.
    """
    project, _ = generated_project
    shared = (project / '_CI' / 'tasks' / 'shared.py').read_text(encoding='utf-8')
    body = shared.split('def apply_badge', 1)[1].split('\ndef ', 1)[0]
    assert 're.search(pattern' in body, 'a missing badge is indistinguishable from a current one'
    assert body.index('re.search(pattern') < body.index('re.sub('), 'the check comes after the substitution'


def test_the_gate_verifies_the_import_order_format_writes(generated_project):
    """`_CI/` is held to the same ruff selection as `src/`, with only a small, named delta.

    `format` runs `ruff check --fix` over `src/`, `_CI/tasks/` and `tests/`, while the gate
    used to only run `ruff format --check` under `_CI/` — so import order (and everything else
    `select = ["ALL"]` catches elsewhere) drifted there unwatched, and `format` swept the
    correction into whatever commit came next, on files a `copier update` owns. `_CI/` now
    selects `ALL` too, matching the root config, so nothing `format` can fix goes unchecked by
    `lint`. The two ignore lists are otherwise required to match exactly: a rule ignored under
    `_CI/` but not the root (or vice versa) has to be a deliberate, named exception — not a
    silent drift between the two files this test is here to catch.
    """
    project, _ = generated_project
    ci_config = tomllib.loads((project / '_CI' / 'pyproject.toml').read_text(encoding='utf-8'))
    root = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    ci_lint = ci_config['tool']['ruff']['lint']
    root_lint = root['tool']['ruff']['lint']
    assert ci_lint['select'] == ['ALL'], 'the _CI/ tree is not held to the same selection as src/'
    assert root_lint['select'] == ['ALL'], 'nothing checks the import order under src/'
    known_delta = {'T201', 'N999', 'FBT001', 'FBT002', 'TC006'}
    ci_ignore = set(ci_lint['ignore'])
    root_ignore = set(root_lint['ignore'])
    assert root_ignore <= ci_ignore, 'a rule the root config ignores must also be ignored under _CI/'
    extra = ci_ignore - root_ignore
    assert extra == known_delta, f'_CI/ ignores {extra} beyond the root config; update the delta if this is deliberate'


def test_the_push_hook_names_every_check_it_runs(generated_project):
    """The `name:` a developer reads on every push lists what the registry actually runs.

    That string is the only description of the gate most people ever see, and it drifted twice
    — `commitizen` and the docs build were both added to `STEPS` while it still said "ty,
    pyscn, test matrix, wheel, derived files". Naming each step here means a new one cannot be
    added without either updating the string or deciding, explicitly, that it needs no name.
    """
    project, _ = generated_project
    # The phrase each step is called in prose. `audit` is deliberately absent: it is in the
    # registry but off by default, being an answer about the advisory database rather than
    # about this tree.
    phrases = {
        'ty': 'ty (types)',
        'commitizen': 'commit messages',
        'docs': 'docs build',
        'pyscn': 'pyscn',
        'tox': 'test matrix',
        'build': 'wheel',
        'artifacts': 'derived files',
    }
    gate = next(hook for hook in pre_commit_hooks(project) if invoked_task(hook) == 'preflight')
    whole_program = [name for name, scope in registry_steps(project).items() if scope == 'WHOLE_PROGRAM']
    unnamed = [name for name in whole_program if name != 'audit' and name not in phrases]
    assert not unnamed, f'steps with no agreed phrase for the hook name: {unnamed}'
    for name in whole_program:
        if name == 'audit':
            assert 'audit' not in gate['name'], 'the hook name promises an audit it does not run'
            continue
        assert phrases[name] in gate['name'], f'{name!r} runs on every push and the hook does not say so'


def test_the_formatting_failure_names_a_command_you_can_paste(generated_project):
    """The gate's fix hint is scoped to the files it checked, and needs no shell of its own.

    A how-to once told readers to assemble the list themselves —
    `format --paths="$(git diff --cached --name-only)"` — which broke three ways: an empty index
    reformatted the whole tree, staged Markdown hit ruff's experimental-formatter error, and a
    staged deletion hit a missing file. The step that reports the failure already holds a list
    with none of those problems, having been through `CODE_FILES` and the index reader, so it
    prints the command instead of describing it. No flag was needed for that.
    """
    project, _ = generated_project
    source = (project / '_CI' / 'tasks' / 'preflight.py').read_text(encoding='utf-8')
    body = source.split('def formatting', 1)[1].split('\ndef ', 1)[0]
    assert '--paths=' in body, 'the fix hint is not scoped to what was checked'
    assert re.search(r'if\s+paths\b', body), 'a whole-project run is told to fix a path list it never had'

    formatter = (project / '_CI' / 'tasks' / 'format_.py').read_text(encoding='utf-8')
    assert '--staged' not in formatter, 'the formatter grew a flag for what the hint already does'
    assert 'staged_files' not in formatter, 'the formatter reads the index itself again'

    how_to = (project / 'docs' / 'developer' / 'how-to' / 'skip-a-check.md').read_text(encoding='utf-8')
    commands = [
        line.strip() for index, block in enumerate(how_to.split('```')) if index % 2 for line in block.splitlines()
    ]
    assert 'git add -A' not in commands, 'the how-to sweeps the whole tree into the commit again'
    assert not any('$(' in command for command in commands), 'the how-to assembles a path list in the shell again'


def test_the_commit_message_check_sees_the_tip_in_every_checkout_shape(generated_project):
    """Whatever the clone looks like, the range covers the commit that just arrived.

    This is the test that was missing. Its string-level predecessor asserted the fallback chain
    and passed while that chain resolved to nothing in GitHub CI: `actions/checkout` fetches one
    commit and runs `checkout -B main refs/remotes/origin/main`, so the branch does track
    `origin/main` and `origin/main` is `HEAD`. The range came out empty, the step reported
    nothing to check, and the run that exists to catch what the hook cannot — a `--no-verify`
    commit, a clone with no hooks — validated no message at all. GitLab's detached checkout took
    a different branch of the same code and did fail, so one check gave two answers by host.

    Also asserted: settled history stays out of the range, which is the deadlock the scoping
    exists to avoid.
    """
    project, cell = generated_project
    # `lint.py` ships identically in every cell, so one cell is enough for a test that builds
    # repositories rather than reading files.
    if cell['label'] != matrix_combos()[0]['label']:
        return
    resolve = range_resolver(project)
    root = project.parent / 'range-shapes'
    root.mkdir(exist_ok=True)

    origin = root / 'origin.git'
    git(root, 'init', '--quiet', '--bare', str(origin))
    upstream = root / 'work'
    upstream.mkdir()
    git(upstream, 'init', '--quiet', '-b', 'main')
    git(upstream, 'commit', '--quiet', '--allow-empty', '-m', 'feat: the first one')
    git(upstream, 'commit', '--quiet', '--allow-empty', '-m', 'WIP unconventional')
    git(upstream, 'remote', 'add', 'origin', str(origin))
    git(upstream, 'push', '--quiet', 'origin', 'main')

    # What `actions/checkout@v6` does: one commit, then a local branch tracking the remote.
    github = root / 'github-runner'
    github.mkdir()
    git(github, 'init', '--quiet', '.')
    git(github, 'remote', 'add', 'origin', str(origin))
    git(
        github,
        '-c',
        'protocol.version=2',
        'fetch',
        '--quiet',
        '--no-tags',
        '--prune',
        '--depth=1',
        'origin',
        '+refs/heads/main*:refs/remotes/origin/main*',
    )
    git(github, 'checkout', '--quiet', '--force', '-B', 'main', 'refs/remotes/origin/main')
    assert git(github, 'rev-parse', '--abbrev-ref', '@{upstream}').stdout.strip() == 'origin/main', (
        'the premise of this test is gone: that checkout no longer sets branch tracking'
    )
    assert 'WIP unconventional' in commits_in(github, resolve(github)), (
        'CI validates no message at all, on the only run that can catch one the hook did not see'
    )

    # What GitLab's runner does: a detached checkout at a shallow depth.
    gitlab = root / 'gitlab-runner'
    gitlab.mkdir()
    git(gitlab, 'init', '--quiet', '.')
    git(gitlab, 'remote', 'add', 'origin', str(origin))
    git(gitlab, 'fetch', '--quiet', '--depth', '20', 'origin', 'main')
    git(gitlab, 'checkout', '--quiet', '--detach', 'FETCH_HEAD')
    assert 'WIP unconventional' in commits_in(gitlab, resolve(gitlab)), 'the detached shape checks nothing'

    # A developer with the message still unpushed.
    git(upstream, 'commit', '--quiet', '--allow-empty', '-m', 'nope: mine to fix')
    assert 'nope: mine to fix' in commits_in(upstream, resolve(upstream)), 'an unpushed message goes unchecked'

    # Once it is pushed and a good commit follows, the old one is nobody's problem.
    git(upstream, 'push', '--quiet', 'origin', 'main')
    git(upstream, 'commit', '--quiet', '--allow-empty', '-m', 'feat: moving on')
    subjects = commits_in(upstream, resolve(upstream))
    assert subjects == ['feat: moving on'], f'the range reaches back into settled history: {subjects}'

    # pre-commit hands a pre-push hook the push's own range, and that wins when it is there.
    base = git(upstream, 'rev-parse', 'HEAD~2').stdout.strip()
    os.environ['PRE_COMMIT_FROM_REF'], os.environ['PRE_COMMIT_TO_REF'] = base, 'HEAD'
    try:
        assert 'nope: mine to fix' in commits_in(upstream, resolve(upstream)), (
            'the range pre-commit supplies loses to an inference about it'
        )
    finally:
        del os.environ['PRE_COMMIT_FROM_REF'], os.environ['PRE_COMMIT_TO_REF']

    # No commits at all is the one case with nothing to say.
    empty = root / 'fresh'
    empty.mkdir()
    git(empty, 'init', '--quiet', '.')
    assert resolve(empty) is None, 'an empty repository resolves a range'


def test_the_commit_message_task_uses_the_bounded_range(generated_project):
    """`lint.commitizen` reaches `cz check` through `unpushed_range`, not with a literal range.

    `test_the_commit_message_check_sees_the_tip_in_every_checkout_shape` proves the resolver
    answers correctly in five clone shapes; it says nothing about whether the task asks it.
    Both halves are needed, and for one commit only the first existed: replacing the task body
    with `cz check --rev-range HEAD` — the unbounded form this whole scoping exists to avoid —
    left the suite green.
    """
    project, _ = generated_project
    lint = (project / '_CI' / 'tasks' / 'lint.py').read_text(encoding='utf-8')
    task = function_named(lint, 'commitizen')
    assert task, 'lint.py declares no commitizen task'
    assert 'unpushed_range' in calls_in(task), 'the task does not ask for a bounded range'
    commands = [text for text in command_strings(task) if 'cz check' in text]
    assert commands, 'the task no longer runs cz check'
    for command in commands:
        assert '--rev-range HEAD' not in command, f'{command!r} reads every reachable commit'


def test_formatting_takes_paths_and_nothing_else(generated_project):
    """`format` has no `--staged`, by signature rather than by the absence of a string.

    invoke derives a flag from the parameter name, so `'--staged' not in source` passed with
    `staged: bool = False` right there in the signature. The gate prints the scoped command;
    the formatter takes the paths.
    """
    project, _ = generated_project
    formatter = (project / '_CI' / 'tasks' / 'format_.py').read_text(encoding='utf-8')
    task = function_named(formatter, 'format_')
    assert task, 'format_.py declares no format task'
    parameters = [argument.arg for argument in task.args.args]
    assert parameters == ['context', 'paths'], f'the formatter takes more than paths: {parameters}'


def test_only_the_matrix_writes_the_unions_filename(generated_project):
    """`reports/coverage.json` is written by the combine and by nothing else.

    The badge and the ratchet read that path by name, so its name is a claim: coverage across
    every interpreter in `env_list`. Three things used to write it. Two were fixed a commit
    apart — the per-env paths in `[tool.tox]`, then `test.tox --env=py311` — and the third was
    `addopts`, whose `--cov-report=json:` tox overrides *inside* the matrix but which applies to
    every bare `pytest` outside it: measured, `test.pytest` left one interpreter's 78.571% in the
    file where the union's 92.857% had been, and `erase_coverage_data`'s glob did not match the
    plain name either, so it stayed until the next full matrix run.
    """
    project, _ = generated_project
    data = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    addopts = ' '.join(data['tool']['pytest']['ini_options']['addopts'])
    assert 'json:reports/coverage.json' not in addopts, 'a bare pytest overwrites the union report'

    test_py = (project / '_CI' / 'tasks' / 'test.py').read_text(encoding='utf-8')
    writers = [line.strip() for line in test_py.splitlines() if 'coverage json -o' in line]
    union = [line for line in writers if 'coverage json -o {COVERAGE_REPORT}' in line]
    assert len(union) == 1, f'{len(union)} commands write the union report, not one: {union}'
    combine = test_py.split('def combine_coverage', 1)[1].split('\n@', 1)[0]
    assert union[0] in combine, 'the union report is written outside the combine'

    erase = test_py.split('def erase_coverage_data', 1)[1].split('\ndef ', 1)[0]
    assert 'COVERAGE_REPORT' in erase, 'a stale union report survives the next matrix run'


def test_the_gate_exits_non_zero_when_any_step_failed(generated_project):
    """`run_scope` accumulates failures, skips the writers after one, and exits non-zero.

    The three properties are one function's behaviour and were asserted by reading it. The exit
    is the load-bearing one: `preflight` prints every failure and then, without this, reports
    success — which is worse than not running at all, because the log says both things.
    """
    project, _ = generated_project
    source = (project / '_CI' / 'tasks' / 'preflight.py').read_text(encoding='utf-8')

    ran: list[str] = []

    def step(name, *, fails=False, derived=False):
        def runner(_context):
            ran.append(name)
            if fails:
                raise SystemExit(1)

        return runner, derived

    def plan(steps):
        return lambda *_args, **_kwargs: steps

    namespace = exec_from(source, 'run_scope', Context=object, FIX_COMMAND='./workflow.cmd preflight --write')

    def run(steps):
        ran.clear()
        namespace['plan_scope'] = plan(steps)
        namespace['run_scope'](object(), 'whole-program', write=False)

    # Nothing failing: no exit, every step run.
    run([step('format'), step('artifacts', derived=True)])
    assert ran == ['format', 'artifacts']

    # One failing check: the later steps still run, and the run ends non-zero.
    with pytest.raises(SystemExit):
        run([step('format', fails=True), step('ruff'), step('ty')])
    assert ran == ['format', 'ruff', 'ty'], 'a failure stopped the run early'

    # A failure before a derived step: that step is skipped, and the exit still happens.
    with pytest.raises(SystemExit):
        run([step('format', fails=True), step('artifacts', derived=True)])
    assert ran == ['format'], 'a derived value was written after a failure'


def test_a_staged_path_that_cannot_be_forwarded_is_refused(generated_project, tmp_path, monkeypatch):
    """`staged_files` refuses a path with a space or a shell character, and drops what is gone.

    `--paths` is space-separated the whole way down, and the list is printed back as a command
    to paste — so `src/a";id;".py`, a valid filename, has to be refused rather than forwarded.
    Without the raise the hook checks a subset of what was staged and passes.
    """
    project, _ = generated_project
    source = (project / '_CI' / 'tasks' / 'preflight.py').read_text(encoding='utf-8')
    namespace = exec_from(source, 'staged_files', 'UNSAFE_IN_PATHS', Context=object, Path=Path)
    staged_files = namespace['staged_files']

    def index(*paths: str):
        class Context:
            def run(self, _command, **_kwargs: object):
                return SimpleNamespace(failed=False, stdout=''.join(f'{path}\n' for path in paths))

        return Context()

    monkeypatch.chdir(tmp_path)
    (tmp_path / 'src').mkdir()
    for name in ('kept.py', 'gone.py', 'has space.py', 'quoted";id;".py'):
        (tmp_path / 'src' / name).touch()

    assert staged_files(index('src/kept.py')) == 'src/kept.py'
    # Staged, then removed from the worktree: nothing left for a tool to read.
    assert staged_files(index('src/kept.py', 'src/missing.py')) == 'src/kept.py'
    for unforwardable in ('src/has space.py', 'src/quoted";id;".py'):
        with pytest.raises(SystemExit):
            staged_files(index('src/kept.py', unforwardable))

    class Broken:
        def run(self, _command, **_kwargs: object):
            return SimpleNamespace(failed=True, stdout='')

    assert staged_files(Broken()) == '', 'no index reads as an error rather than as no work'


def test_the_ci_badge_is_verified_only_where_the_tree_can_answer(generated_project, monkeypatch):
    """The gate asks whether the placeholder survived a remote — never which URL the badge holds.

    Three states, and only one of them is wrong. A fresh project keeps the placeholder because it
    has been pushed nowhere; a fork contributor's README names upstream while their `origin` names
    the fork, and demanding they match would have them repoint upstream's badge at their fork; the
    owner who generated, committed and pushed without running `--write` leaves `build-unknown` in
    place, and nothing used to ask — verified end to end, the badge stayed that way through both
    tutorials.

    So verifying stops at the one tree-level question: is this still the shipped placeholder while
    `origin` resolves? Executed here rather than read, because the distinction is the whole point
    and a grep cannot tell the three states apart.
    """
    project, cell = generated_project
    # `update_pipeline_badge` reads `Path('README.md')`, so the project has to be the cwd.
    monkeypatch.chdir(project)
    document = (project / '_CI' / 'tasks' / 'document.py').read_text(encoding='utf-8')
    updater = exec_from(
        document,
        'update_pipeline_badge',
        'PIPELINE_PLACEHOLDER',
        re=re,
        Path=Path,
        Context=object,
        apply_badge=lambda *_args, **_kwargs: None,
        pipeline_badge=lambda context: context.badge,
    )['update_pipeline_badge']

    placeholder = 'build' if cell['git_hosting_service'] == 'github' else 'pipeline'
    readme = project / 'README.md'
    original = readme.read_text(encoding='utf-8')
    assert f'img.shields.io/badge/{placeholder}-unknown' in original, 'the shipped README has no placeholder'

    # No remote: nothing to say. `pipeline_badge` returns '' when `origin` is unreadable.
    assert updater(SimpleNamespace(badge=''), write=False) is None, 'an unpushed project is reported stale'

    # A remote, and the placeholder still there: the owner forgot, and the gate says so.
    pushed = SimpleNamespace(badge='[![Build](https://example.invalid/b)](https://example.invalid)')
    reason = updater(pushed, write=False)
    assert reason is not None, 'a forgotten badge passes the gate'
    assert 'placeholder' in reason, f'the reason does not name the placeholder: {reason!r}'

    # A real URL, whatever it names: the fork contributor is left alone.
    try:
        readme.write_text(
            original.replace(
                f'https://img.shields.io/badge/{placeholder}-unknown-lightgrey',
                'https://github.com/upstream/project/actions/workflows/continuous-integration.yaml/badge.svg',
                1,
            ),
            encoding='utf-8',
        )
        forked = updater(
            SimpleNamespace(badge='[![Build](https://github.com/contributor/fork)](https://x)'), write=False
        )
        assert forked is None, f'a fork is asked to repoint upstream badge: {forked!r}'
    finally:
        readme.write_text(original, encoding='utf-8')


def test_matrix_envs_do_not_share_report_paths(generated_project):
    """Every tox env writes its report to its own path, and a plain run renders nothing else.

    `addopts` sends the JSON report to one fixed path, so under `run-parallel` all five envs
    wrote `reports/coverage.json` simultaneously. It stayed invisible while nothing read that
    file; the moment the coverage badge and the `fail_under` ratchet read it, they would be
    reading whichever env finished last, possibly mid-write.

    No HTML from a plain run, per env or otherwise: nothing in a hook or a pipeline opens one,
    and rendering them is most of a scaffold's test run. `test.coverage` and `test.view`
    produce them on demand.
    """
    project, _ = generated_project
    data = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    addopts = data['tool']['pytest']['ini_options']['addopts']
    commands = data['tool']['tox']['env_run_base']['commands']
    specs = [argument for command in commands for argument in command if isinstance(argument, str)]

    overrides = [spec for spec in specs if spec.startswith('--cov-report=json:')]
    assert overrides, 'no per-env override for --cov-report=json:'
    for spec in overrides:
        assert '{envname}' in spec, f'{spec!r} is fixed, so parallel envs clobber each other'

    for flag in ('--cov-report=html:', '--html='):
        rendered = [spec for spec in (*addopts, *specs) if spec.startswith(flag)]
        assert not rendered, f'a plain run renders {flag} for nobody: {rendered}'

    # `-n auto` under `run-parallel` asks for one pool per env, which measured slower on
    # sixteen cores than the same config on four.
    assert 'auto' not in addopts, 'every env spawns a pool sized for the whole machine'
    assert '-n' in addopts, 'the worker count is no longer pinned'


def test_matrix_coverage_is_combined_before_anything_reads_it(generated_project):
    """`test.tox` erases, runs the matrix, then combines into the one report the badge reads.

    Combining takes the union of the lines each interpreter executed, which is the only
    correct reading of a version matrix: version-gated code cannot be fully covered by any
    single env, so reading one env's report understates coverage on exactly the code the
    matrix exists to exercise. The erase is what stops a `.coverage.<env>` left over from an
    env since removed from `env_list` being folded into that union.
    """
    project, _ = generated_project
    test_py = (project / '_CI' / 'tasks' / 'test.py').read_text(encoding='utf-8')
    # Past the closing `"""`, so the docstring's own mention of combine_coverage — which
    # precedes every command — cannot satisfy the ordering assertions below.
    body = test_py.split('def tox_matrix', 1)[1].split('\n@', 1)[0].split('"""')[-1]
    for step in ('erase_coverage_data', 'tox run', 'combine_coverage'):
        assert step in body, f'the matrix no longer runs {step!r}'
    assert body.index('erase_coverage_data') < body.index('tox run'), 'stale coverage data is not cleared first'
    # Not `coverage erase`: it leaves `.coverage.<envname>` in place, so a retired env's data
    # would still be combined into the union that feeds the badge and the ratchet.
    erase = test_py.split('def erase_coverage_data', 1)[1].split('\ndef ', 1)[0]
    assert "Path().glob('.coverage.*')" in erase, 'the per-env data files are no longer cleared'
    assert body.index('tox run') < body.index('combine_coverage'), 'coverage is combined before the matrix runs'
    combine = test_py.split('def combine_coverage', 1)[1].split('\n@task', 1)[0]
    assert 'coverage combine' in combine, 'the per-env data is never merged'
    assert 'coverage json -o {COVERAGE_REPORT}' in combine, 'the union never reaches the report the badge reads'
    # And it gates only when the data under it is the union the floor was measured from.
    # `test.tox --env=py311` combines one env's data: enforcing there failed the command whose
    # whole purpose is looking at one interpreter, on any project with an engaged ratchet.
    assert re.search(r'combine_coverage\([^)]*scope\s*=\s*env', test_py), 'the combine no longer knows its scope'
    # The two writes, by command line rather than by prose: the comments around them discuss
    # `--fail-under=0` as well.
    writes = [line for line in combine.splitlines() if 'coverage json -o' in line]
    scoped = [line for line in writes if '{scope}' in line]
    union = [line for line in writes if '{COVERAGE_REPORT}' in line]
    assert scoped, "one interpreter's data is written to the union's name"
    assert all('--fail-under=0' in line for line in scoped), 'one interpreter is gated by a floor set from five'
    assert union, 'the union never reaches the report the badge reads'
    assert not any('--fail-under=0' in line for line in union), 'the union run does not enforce the floor either'


def test_only_what_measures_a_derived_value_may_write_it(generated_project):
    """A derived value is written by whatever produced the data behind it — and nothing else.

    Not "only `preflight` writes", which was the earlier rule and too blunt. The coverage badge
    means coverage across every interpreter in `env_list`, so `test.tox` may write it: that is
    exactly what it measured. `test` and `test.coverage` measure one interpreter, so they may
    neither write it nor comment on it — a single-interpreter number is not the badge's
    quantity, and warning about it would be a claim they cannot support. Demonstrated before
    the change: `test` wrote 85% from one interpreter and the gate then rejected it as stale
    against the union's 100%.

    `document` is the same argument for a different reason. Version, Python range and the CI
    badge's URL come from tracked files, so it can vouch for those; coverage and pyscn come
    from reports it does not produce, so it would be stamping in whatever a previous run left.

    Writing stays opt-in via `--write` wherever it is allowed, and the gate verifies all five.
    """
    project, _ = generated_project
    tasks = project / '_CI' / 'tasks'
    test_py = (tasks / 'test.py').read_text(encoding='utf-8')

    # One interpreter: no write, and no comment either.
    for task_name in ("@logged('test')", "@logged('test.coverage')"):
        body = test_py.split(task_name, 1)[1].split('\n@', 1)[0]
        assert 'update_coverage_badge' not in body, f'{task_name} writes the coverage badge again'
        assert 'ratchet_fail_under' not in body, f'{task_name} moves the ratchet again'

    # The matrix: writes under --write, reports otherwise, refuses a narrowed run.
    tox_task = test_py.split("@logged('test.tox')", 1)[1].split('\n@', 1)[0]
    assert 'note(update_coverage_badge(write=write))' in tox_task, 'the matrix no longer owns the badge'
    assert 'note(ratchet_fail_under(write=write))' in tox_task, 'the matrix no longer owns the ratchet'
    assert 'if env and write:' in tox_task, 'a narrowed matrix can still write the badge'

    # The registry runs the non-writing entry point, so a hook and a pipeline write nothing.
    preflight = (tasks / 'preflight.py').read_text(encoding='utf-8')
    assert 'check=tox_matrix' in preflight, 'the gate runs the writing task instead of the matrix'

    # pyscn measured the grade, so it may write the badge — but only when asked.
    quality = (tasks / 'quality.py').read_text(encoding='utf-8')
    for task_name in ('def pyscn_analyze(', 'def pyscn_analyze_only(', 'def pyscn('):
        signature = quality.split(task_name, 1)[1].split(')', 1)[0]
        assert 'write: bool = False' in signature, f'{task_name} writes the pyscn badge unasked'

    # And `document` writes no badge at all: building docs is not changing the README.
    document = (tasks / 'document.py').read_text(encoding='utf-8')
    aggregator = document.split("@logged('document')", 1)[1]
    for absent in ('update_coverage_badge', 'update_pyscn_badge', 'update_package_version_badge'):
        assert absent not in aggregator, f'document writes {absent} unasked'

    # Which leaves no task writing a tracked file unasked: every write is behind `--write` or
    # inside a command named for the mutation it performs.
    release = (tasks / 'release.py').read_text(encoding='utf-8')
    bump = release.split("@logged('release.bump')", 1)[1].split('\n@', 1)[0]
    assert 'update_package_version_badge(version=' in bump, (
        'release.bump lands a README that contradicts the version it released'
    )


def test_the_ci_badge_is_the_hosts_own(generated_project):
    """The CI badge points at the host's status endpoint, and no task records a build status.

    It used to be written locally by `build`, recording whether *that* run passed — which told
    a reader nothing, could claim "passing" on a run that then failed, and on GitLab was never
    written at all: `build.py` matched only the `Build` badge that GitHub projects render, so
    every GitLab project shipped a `pipeline-unknown` badge nothing could update.

    The host renders the current status on every page load, so only the URL is derived, from
    `origin`, and it stops changing once written. A project with no readable `origin` keeps its
    placeholder rather than being reported stale — not pushed anywhere is not the same as wrong.
    """
    project, cell = generated_project
    tasks = project / '_CI' / 'tasks'
    # Asserted against code, not prose: the docstring explains the absence, so matching the
    # word "README" would fail on the explanation itself.
    build_py = (tasks / 'build.py').read_text(encoding='utf-8')
    assert "Path('README.md')" not in build_py, 'build writes the README again'
    assert 'apply_badge' not in build_py, 'build writes a badge again'

    host_module = (tasks / f'{cell["git_hosting_service"]}.py').read_text(encoding='utf-8')
    assert 'def pipeline_badge' in host_module, 'the host module builds no CI badge'
    expected = (
        'actions/workflows' if cell['git_hosting_service'] == 'github' else 'badges/{DEFAULT_BRANCH}/pipeline.svg'
    )
    assert expected in host_module, f'the CI badge does not point at the host: {expected!r} missing'

    document = (tasks / 'document.py').read_text(encoding='utf-8')
    assert 'def update_pipeline_badge' in document, 'nothing points the CI badge anywhere'
    updater = document.split('def update_pipeline_badge', 1)[1].split('\ndef ', 1)[0]
    unknown_remote = updater.split('pipeline_badge(context)', 1)[1].split('return apply_badge', 1)[0]
    assert 'return None' in unknown_remote, 'a project without a remote is reported stale, not left alone'


def test_readme_has_exactly_one_writer(generated_project):
    """Every write to README.md goes through `apply_badge`, so check mode cannot drift.

    A `preflight` that verifies is only trustworthy if it compares against the same substitution the
    writer applies. A second module that rewrote a badge its own way would be invisible to the
    check — the badge would be updated by one code path and verified by another, which is the
    failure this whole shape exists to prevent.
    """
    project, _ = generated_project
    tasks = project / '_CI' / 'tasks'
    for module in sorted(tasks.glob('*.py')):
        source = module.read_text(encoding='utf-8')
        if 'README.md' not in source or module.name == 'shared.py':
            continue
        assert 'write_text' not in source, f'{module.name} writes README.md without going through apply_badge'


def test_derived_values_are_computed_in_both_modes_by_one_function(generated_project):
    """Each derived value has a single updater that takes `write`, rather than a paired checker.

    The generator and the gate being one function is what makes a verifying `preflight` mean
    anything. Splitting them — a writer here, a verifier there — is exactly how a check ends up
    passing on a value the writer would have changed.
    """
    project, _ = generated_project
    tasks = project / '_CI' / 'tasks'
    updaters = {
        'quality.py': ['update_pyscn_badge'],
        'test.py': ['update_coverage_badge', 'ratchet_fail_under'],
        'document.py': ['update_package_version_badge', 'update_python_badge', 'update_pipeline_badge'],
    }
    for filename, names in updaters.items():
        tree = ast.parse((tasks / filename).read_text(encoding='utf-8'))
        functions = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        for name in names:
            assert name in functions, f'{filename} no longer defines {name}'
            kwonly = [argument.arg for argument in functions[name].args.kwonlyargs]
            assert 'write' in kwonly, f'{name} takes no keyword-only `write`, so it cannot verify without writing'
