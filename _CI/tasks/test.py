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
                                     QA_STEPS,
                                     TEMPLATE_SECURITY_OVERRIDE_ENV,
                                     combo_context,
                                     combo_label,
                                     matrix_combos,
                                     read_template_overrides)

REPORTS_DIR = PROJECT_ROOT_DIRECTORY / 'reports' / 'matrix'


def run_command(cmd, cwd=None, env=None, log_file=None):
    """Run a shell command. Return True on exit 0. Stream to log_file if given, else stdout."""
    proc_env = {**os.environ, **(env or {})}
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
    """Copy the template into a temp git repo so cruft sees all current files."""
    template_repo = tmpdir / 'template'
    shutil.copytree(str(PROJECT_ROOT_DIRECTORY), str(template_repo), ignore=IGNORE_PATTERNS)
    snapshot_steps = (
        'git init -b main',
        'git add -A',
        # Force-add the vendored CI lib (gitignored by the broad `lib/` pattern).
        'git add -f "{{ cookiecutter.project_slug }}/_CI/lib/"',
        ('git -c commit.gpgsign=false -c user.name=ci -c user.email=ci@localhost '
         'commit -m "temp: template snapshot for testing" '
         '--author "ci <ci@localhost>"'),
    )
    for step in snapshot_steps:
        if not run_command(step, cwd=template_repo):
            raise SystemExit(f'Snapshot step failed: {step}')
    return template_repo


def run_combo(template_repo, output_root, extra_context, label, log_file=None):
    """Generate the template with extra_context and run QA_STEPS. Return True on success."""
    output_dir = output_root / label / 'generated'
    output_dir.mkdir(parents=True, exist_ok=True)

    cruft_parts = ['uvx cruft create --no-input']
    if extra_context:
        cruft_parts.append(f"--extra-context '{json.dumps(extra_context)}'")
    cruft_parts.append(f'--output-dir {output_dir}')
    cruft_parts.append(str(template_repo))
    if not run_command(' '.join(cruft_parts), log_file=log_file):
        return False

    project_dir = output_dir / PROJECT_SLUG
    make_file_executable(project_dir / 'workflow.cmd')

    init_steps = (
        'git init -b main',
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

    for step in QA_STEPS:
        if not run_command(f'./workflow.cmd {step}', cwd=project_dir, env=step_env, log_file=log_file):
            failure_msg = f'[{label}] task "{step}" failed'
            if log_file is not None:
                with log_file.open('a', encoding='utf-8') as handle:
                    handle.write(f'\n{failure_msg}\n')
            else:
                print(emojize_message(failure_msg, success=False))
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


@task(help={'dep_track': 'Set integrate_dependency_track=true (omit for false)'})
def combo(context, dep_track=False):
    """Run the full QA cycle for one matrix cell (one integrate_dependency_track value)."""
    tmpdir = Path(tempfile.mkdtemp(prefix='paleofuturistic_combo_'))
    try:
        template_repo = prepare_snapshot(tmpdir)
        output_root = tmpdir / 'generated'
        output_root.mkdir()
        label = combo_label(dep_track)
        ok = run_combo(
            template_repo,
            output_root,
            extra_context=combo_context(dep_track),
            label=label,
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
    combos = matrix_combos()
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
                    extra_context=combo_context(cell['integrate_dependency_track']),
                    label=label,
                    log_file=log_path,
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
    combos = matrix_combos()
    if as_json:
        print(json.dumps(combos, separators=(',', ':')))
        return
    print(f'{"label":<8} integrate_dependency_track')
    for cell in combos:
        print(f'{cell["label"]:<8} {cell["integrate_dependency_track"]}')
