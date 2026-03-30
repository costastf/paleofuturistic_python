import shutil
import tempfile
from pathlib import Path

from invoke import task

from _CI import (PROJECT_ROOT_DIRECTORY,
                 emojize_message,
                 make_file_executable)

PROJECT_SLUG = 'paleofuturistic_python_project'
IGNORE_PATTERNS = shutil.ignore_patterns('.git', '.venv', '__pycache__', '*.pyc', '.cruft.json')


@task
def test(context):
    """Generate the template into a tmp dir and run lint, test, build and document tasks."""
    tmpdir = Path(tempfile.mkdtemp(prefix='paleofuturistic_test_'))
    try:
        # Copy the full working tree into a temp git repo so cruft sees all current files,
        # including any uncommitted changes to the template.
        template_repo = tmpdir / 'template'
        shutil.copytree(str(PROJECT_ROOT_DIRECTORY), str(template_repo), ignore=IGNORE_PATTERNS)
        with context.cd(str(template_repo)):
            context.run('git init -b main', echo=True)
            context.run('git add -A', echo=True)
            # Force-add the vendored CI lib so cruft includes it in generated projects.
            # It is git-ignored by the broad `lib/` pattern in .gitignore.
            context.run('git add -f "{{ cookiecutter.project_slug }}/_CI/lib/"', echo=True)
            context.run('git commit -m "temp: template snapshot for testing" '
                        '--author "ci <ci@localhost>"', echo=True)

        output_dir = tmpdir / 'generated'
        output_dir.mkdir()
        result = context.run(
            f'uvx cruft create --no-input --output-dir {output_dir} {template_repo}',
            warn=True, echo=True
        )
        if result.failed:
            print(emojize_message('Template generation failed', success=False))
            raise SystemExit(1)

        project_dir = output_dir / PROJECT_SLUG
        make_file_executable(project_dir / 'workflow')

        with context.cd(str(project_dir)):
            context.run('uv sync --all-extras --dev', echo=True)
            for step in ('lint', 'test', 'build', 'document'):
                result = context.run(f'./workflow {step}', warn=True, echo=True)
                if result.failed:
                    print(emojize_message(f'Task "{step}" failed', success=False))
                    raise SystemExit(1)

        print(emojize_message('All template QA tasks passed successfully'))
    finally:
        shutil.rmtree(str(tmpdir), ignore_errors=True)
