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


def run_combo(template_repo, output_root, extra_context, label, log_file=None):
    """Generate the template with extra_context and run QA_STEPS. Return True on success."""
    combo_root = output_root / label
    combo_root.mkdir(parents=True, exist_ok=True)

    data_file = combo_root / 'data.json'
    data_file.write_text(json.dumps(extra_context or {}), encoding='utf-8')
    project_dir = combo_root / 'generated' / PROJECT_SLUG
    copier_cmd = (
        f'uvx copier copy --defaults --trust '
        f'--data-file {data_file} {template_repo} {project_dir}'
    )
    if not run_command(copier_cmd, log_file=log_file):
        return False

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


@task(
    help={
        'git_hosting_service': 'github (default) or gitlab',
        'integrate_dependency_track': 'Bool — opt the SBOM-upload code in (default true)',
        'integrate_pages': 'Bool — opt the Pages workflow + task in (default true)',
    }
)
def combo(context, git_hosting_service='github', integrate_dependency_track=True, integrate_pages=True):
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
                    extra_context=combo_context(
                        git_hosting_service=cell['git_hosting_service'],
                        integrate_dependency_track=cell['integrate_dependency_track'],
                        integrate_pages=cell['integrate_pages'],
                    ),
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
    print(f'{"label":<18} {"host":<7} {"dep_track":<10} {"pages":<6}')
    for cell in combos:
        print(
            f'{cell["label"]:<18} '
            f'{cell["git_hosting_service"]:<7} '
            f'{str(cell["integrate_dependency_track"]):<10} '
            f'{str(cell["integrate_pages"]):<6}'
        )


@task
def invariants(context):
    """Run the fast pytest invariants against the cartesian-product matrix."""
    if not run_command('uv run --group test pytest tests/ -v', cwd=PROJECT_ROOT_DIRECTORY):
        print(emojize_message('Template invariants failed', success=False))
        raise SystemExit(1)
    print(emojize_message('Template invariants passed'))
