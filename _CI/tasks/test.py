"""Template QA task definitions."""

import concurrent.futures
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from invoke import task

from _CI import (PROJECT_ROOT_DIRECTORY,
                 emojize_message,
                 make_file_executable)
from _CI.tasks.configuration import (IGNORE_PATTERNS,
                                     PROJECT_SLUG,
                                     TEMPLATE_SECURITY_OVERRIDE_ENV,
                                     base_context,
                                     combo_context,
                                     combo_label,
                                     generation_env,
                                     qa_cells,
                                     qa_sequence,
                                     read_template_overrides)

REPORTS_DIR = PROJECT_ROOT_DIRECTORY / 'reports' / 'matrix'
MATURE_ORIGIN = 'git@github.com:acme/widget.git'
# What a matured cell puts in place of the scaffolding. Two facts make it a project on day
# two rather than day one:
#
# `test_sanity` is gone, which is what takes the coverage ratchet out of auto-detect dormancy,
# and `hello` is imported without being called, so the floor the ratchet records lands strictly
# between 0 and 100 — the only range in which a writer and a checker can disagree.
#
# The gated module covers a different line on each interpreter, so the union the ratchet
# measures is higher than any single cell of the matrix produces. That is the shape that
# catches a coverage floor enforced per interpreter instead of against the union: the floor is
# satisfiable only by the combined run, so every env fails on a bar its own numbers cannot
# clear. The boundary is one minor above the oldest supported interpreter, so at least one env
# falls on each side of it.
MATURE_TEST_MODULE = '''"""Smoke tests for {slug}."""

from {slug} import hello
from {slug}.generation import label


def test_hello_is_available() -> None:
    """The package exports a greeter, which this leaves uncalled."""
    assert callable(hello)


def test_generation_is_named() -> None:
    """The interpreter generation is one of the two this package knows."""
    assert label() in {{'recent', 'legacy'}}
'''
MATURE_GATED_MODULE = '''"""Interpreter-dependent helper for {slug}."""

import sys


def label() -> str:
    """Name the interpreter generation this is running on."""
    if sys.version_info >= {boundary}:
        return 'recent'
    return 'legacy'
'''


def run_command(cmd, cwd=None, env=None, log_file=None):
    """Run a shell command. Return True on exit 0. Stream to log_file if given, else stdout.

    `VIRTUAL_ENV` is stripped from the inherited environment so each combo's
    generated project sees a clean slate and uv resolves the project-local
    `.venv` without warning about a mismatched parent-shell export.
    """
    inherited = {key: value for key, value in os.environ.items() if key != 'VIRTUAL_ENV'}
    proc_env = {**inherited, **(env or {})}
    cwd_str = str(cwd) if cwd else None
    if log_file is not None:
        with log_file.open('a', encoding='utf-8') as handle:
            handle.write(f'\n$ {cmd}\n')
            handle.flush()
            result = subprocess.run(cmd, shell=True, cwd=cwd_str, env=proc_env,
                                    stdout=handle, stderr=subprocess.STDOUT)
    else:
        print(f'\n$ {cmd}')
        result = subprocess.run(cmd, shell=True, cwd=cwd_str, env=proc_env)
    return result.returncode == 0


def prepare_snapshot(tmpdir):
    """Copy the template into a plain temp dir so copier sees all current files.

    Copier copies happily from a non-git local directory, so no git snapshot is needed.
    """
    template_repo = tmpdir / 'template'
    shutil.copytree(str(PROJECT_ROOT_DIRECTORY), str(template_repo), ignore=IGNORE_PATTERNS)
    return template_repo


def report_failure(message, log_file):
    """Record a QA failure in the cell's log, or on stdout when running a single combo."""
    if log_file is not None:
        with log_file.open('a', encoding='utf-8') as handle:
            handle.write(f'\n{message}\n')
    else:
        print(emojize_message(message, success=False))


def untracked_after_qa(project_dir):
    """Return paths the QA run left untracked, which should be none.

    The template promises that running its workflow does not litter: everything the tasks write
    — `reports/`, `.coverage*`, `.tox/`, `dist/`, the SBOM, the caches — is matched by the
    `.gitignore` it ships. A tool added later, or a trimmed ignore rule, would otherwise show up
    first as a confusing `git status` after someone's push, or as build output swept into a
    commit by `git add -A`.

    Only *untracked* files count: `QA_STEPS` runs `preflight --write`, so modified tracked files
    are expected.

    It lives in the template's own tests rather than shipping into generated projects, because
    the assertion is only sound on a freshly generated, fully committed tree, which is what this
    runner has. In a real project a developer's work-in-progress is indistinguishable from
    workflow output, so a shipped check would fail half the time and police the owner besides.
    """
    result = subprocess.run(
        ['git', 'status', '--porcelain', '--untracked-files=all'],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return [f'git status failed: {result.stderr.strip()}']
    return [line[3:] for line in result.stdout.splitlines() if line.startswith('??')]


def run_combo(template_repo, output_root, extra_context, label, log_file=None, mature=False):
    """Generate the template with extra_context and run the QA steps. Return True on success.

    `mature` makes the cell look like a project on day two — see `qa_cells` — and carries the
    dependency audit with it, which one cell runs rather than all of them; see `AUDIT_STEP`.
    There is no separate switch for that: a caller who could pass `audit` separately from
    `mature` could also pass it for every cell, or for none, and neither is visible from the
    matrix summary.
    """
    combo_root = output_root / label
    combo_root.mkdir(parents=True, exist_ok=True)

    data_file = combo_root / 'data.json'
    data_file.write_text(json.dumps(extra_context or {}), encoding='utf-8')
    project_dir = combo_root / 'generated' / PROJECT_SLUG
    copier_cmd = (
        f'uvx copier copy --defaults --trust '
        f'--data-file {data_file} {template_repo} {project_dir}'
    )
    # Pin what generation stamps, so the generated `required-version` matches the uv this run
    # is using — otherwise every `uv sync` below fails on a version mismatch.
    if not run_command(copier_cmd, env=generation_env(), log_file=log_file):
        return False

    make_file_executable(project_dir / 'workflow.cmd')

    if mature:
        oldest = (extra_context or {}).get('min_python_version') or base_context()['min_python_version']
        major, minor = (int(part) for part in oldest.split('.'))
        test_module = project_dir / 'tests' / f'test_{PROJECT_SLUG}.py'
        test_module.write_text(MATURE_TEST_MODULE.format(slug=PROJECT_SLUG), encoding='utf-8')
        gated = project_dir / 'src' / PROJECT_SLUG / 'generation.py'
        gated.write_text(MATURE_GATED_MODULE.format(slug=PROJECT_SLUG, boundary=(major, minor + 1)), encoding='utf-8')

    init_steps = (
        'git init -b main',
        *((f'git remote add origin {MATURE_ORIGIN}',) if mature else ()),
        'git add -A',
        ('git -c commit.gpgsign=false -c user.name=ci -c user.email=ci@localhost '
         'commit -m "feat: initial project from template" '
         '--author "ci <ci@localhost>"'),
        'uv sync --all-extras --dev',
    )
    for step in init_steps:
        if not run_command(step, cwd=project_dir, log_file=log_file):
            return False

    step_env = {'CI': 'true'}
    override_parts = []
    file_overrides = read_template_overrides()
    if file_overrides:
        override_parts.append(file_overrides)
    env_override = os.environ.get(TEMPLATE_SECURITY_OVERRIDE_ENV, '').strip()
    if env_override:
        override_parts.append(env_override)
    if override_parts:
        step_env[f'{PROJECT_SLUG.upper()}_SECURITY_OVERRIDE'] = ','.join(override_parts)

    # Accumulate rather than stop at the first failure, matching what the matrix already does
    # across cells and what `run_scope` does across steps. This loop is the slowest feedback
    # in the system — eight cells at tens of seconds each — so one run reporting everything is
    # worth the seconds it costs when something is already red. Stopping early also skipped the
    # litter check below in precisely the cells that were already unhappy.
    steps = qa_sequence(audit=mature)
    failed = [step for step in steps
              if not run_command(f'./workflow.cmd {step}', cwd=project_dir, env=step_env, log_file=log_file)]

    untracked = untracked_after_qa(project_dir)
    if untracked:
        report_failure(
            f'[{label}] the workflow left untracked files, so .gitignore has a hole: '
            f'{", ".join(untracked)}',
            log_file,
        )
    if failed or untracked:
        if failed:
            report_failure(f'[{label}] failed: {", ".join(failed)}', log_file)
        return False
    return True


@task
def test(context):
    """Generate the template with default context and run the full QA cycle."""
    tmpdir = Path(tempfile.mkdtemp(prefix='paleofuturistic_test_'))
    try:
        template_repo = prepare_snapshot(tmpdir)
        output_root = tmpdir / 'generated'
        output_root.mkdir()
        ok = run_combo(template_repo, output_root, extra_context={}, label='default')
        if not ok:
            print(emojize_message('Template QA failed', success=False))
            raise SystemExit(1)
        print(emojize_message('All template QA tasks passed successfully'))
    finally:
        shutil.rmtree(str(tmpdir), ignore_errors=True)


@task(
    help={
        'git_hosting_service': 'github (default) or gitlab',
        'integrate_dependency_track': 'Bool — opt the SBOM-upload code in (default true)',
        'integrate_pages': 'Bool — opt the Pages workflow + task in (default true)',
        'mature': 'Bool — day-two project: no smoke test, an origin, and the dependency audit',
    }
)
def combo(context, git_hosting_service='github', integrate_dependency_track=True, integrate_pages=True,
          mature=False):
    """Run the full QA cycle for one matrix cell across all three template knobs."""
    tmpdir = Path(tempfile.mkdtemp(prefix='paleofuturistic_combo_'))
    try:
        template_repo = prepare_snapshot(tmpdir)
        output_root = tmpdir / 'generated'
        output_root.mkdir()
        label = combo_label(
            git_hosting_service=git_hosting_service,
            integrate_dependency_track=integrate_dependency_track,
            integrate_pages=integrate_pages,
            mature=mature,
        )
        ok = run_combo(
            template_repo,
            output_root,
            extra_context=combo_context(
                git_hosting_service=git_hosting_service,
                integrate_dependency_track=integrate_dependency_track,
                integrate_pages=integrate_pages,
            ),
            label=label,
            mature=mature,
        )
        if not ok:
            print(emojize_message(f'Combo {label} failed', success=False))
            raise SystemExit(1)
        print(emojize_message(f'Combo {label} passed'))
    finally:
        shutil.rmtree(str(tmpdir), ignore_errors=True)


@task(help={'workers': 'Parallel combos; default 1 (sequential) to avoid pytest-xdist races'})
def matrix(context, workers=1):
    """Run every matrix cell; summarize and exit non-zero on any failure.

    Defaults to sequential (workers=1) because each combo internally runs tox
    run-parallel + pytest-xdist, so running combos in parallel on a single host
    over-subscribes CPU and triggers xdist worker-teardown races. On GitHub
    Actions each matrix cell runs on its own VM, so the outer parallelism is
    handled by the fan-out workflow instead. Pass --workers=2 to opt into
    local host-level parallelism.
    """
    combos = qa_cells()
    effective_workers = max(1, min(len(combos), workers))

    tmpdir = Path(tempfile.mkdtemp(prefix='paleofuturistic_matrix_'))
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        template_repo = prepare_snapshot(tmpdir)
        output_root = tmpdir / 'generated'
        output_root.mkdir()

        def worker(cell):
            label = cell['label']
            log_path = REPORTS_DIR / f'{label}.log'
            if log_path.exists():
                log_path.unlink()
            start = time.monotonic()
            try:
                ok = run_combo(
                    template_repo,
                    output_root,
                    extra_context=combo_context(
                        git_hosting_service=cell['git_hosting_service'],
                        integrate_dependency_track=cell['integrate_dependency_track'],
                        integrate_pages=cell['integrate_pages'],
                    ),
                    label=label,
                    log_file=log_path,
                    mature=cell['mature'],
                )
            except Exception as exc:  # noqa: BLE001 — worker must not crash the pool
                with log_path.open('a', encoding='utf-8') as handle:
                    handle.write(f'\nEXCEPTION: {exc}\n')
                ok = False
            return label, ok, time.monotonic() - start

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=effective_workers) as pool:
            for outcome in pool.map(worker, combos):
                results.append(outcome)

        print()
        print(f'{"combo":<8} {"result":<7} duration')
        any_failed = False
        for label, ok, duration in results:
            mins, secs = divmod(int(duration), 60)
            status = 'PASS' if ok else 'FAIL'
            log_hint = '' if ok else f'  (log: {REPORTS_DIR.relative_to(PROJECT_ROOT_DIRECTORY)}/{label}.log)'
            print(f'{label:<8} {status:<7} {mins}m{secs:02d}s{log_hint}')
            any_failed = any_failed or not ok

        if any_failed:
            print(emojize_message('Matrix had failing combos', success=False))
            raise SystemExit(1)
        print(emojize_message('All matrix combos passed'))
    finally:
        shutil.rmtree(str(tmpdir), ignore_errors=True)


@task(help={'as_json': 'Emit the matrix as JSON (for GH Actions consumption)'})
def list_combos(context, as_json=False):
    """Print the matrix — table by default, JSON array with --as-json."""
    combos = qa_cells()
    if as_json:
        print(json.dumps(combos, separators=(',', ':')))
        return
    print(f'{"label":<24} {"host":<7} {"dep_track":<10} {"pages":<6} {"mature":<6}')
    for cell in combos:
        print(
            f'{cell["label"]:<24} '
            f'{cell["git_hosting_service"]:<7} '
            f'{str(cell["integrate_dependency_track"]):<10} '
            f'{str(cell["integrate_pages"]):<6} '
            f'{str(cell["mature"]):<6}'
        )


@task
def invariants(context):
    """Run the fast pytest invariants against the cartesian-product matrix."""
    if not run_command('uv run --group test pytest tests/ -v', cwd=PROJECT_ROOT_DIRECTORY):
        print(emojize_message('Template invariants failed', success=False))
        raise SystemExit(1)
    print(emojize_message('Template invariants passed'))
