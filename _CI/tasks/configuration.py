"""Centralized constants for CI task definitions."""

import re
import shutil

import yaml

from _CI import PROJECT_ROOT_DIRECTORY

TEMPLATE_PYPROJECT = PROJECT_ROOT_DIRECTORY / 'template' / 'pyproject.toml.jinja'

# Generation normally stamps the newest uv release that has cleared its cool-down, so a new
# project starts current. That would break the template's own tests: CI installs the uv the
# template pins, then generates projects and runs `uv sync` with it, and a freshly stamped
# `required-version` the ambient uv cannot satisfy fails every matrix cell. Setting this to the
# committed pin makes generation deterministic and keeps it matching the installed uv.
UV_VERSION_ENV = 'TEMPLATE_UV_VERSION'

PROJECT_SLUG = 'paleofuturistic_python_project'
IGNORE_PATTERNS = shutil.ignore_patterns('.git', '.venv', '__pycache__', '*.pyc', '.copier-answers.yml')
# `preflight` covers format, lint, ty, pyscn, the tox matrix, the wheel and the derived files,
# so what is left to list is what it deliberately does not do: the dependency audit, whose
# answer depends on the advisory database rather than on the generated tree, and the docs build.
#
# Every step runs even after one fails — `run_combo` accumulates, as the matrix already does
# across cells. The feedback loop here is the slowest in the system, eight cells at tens of
# seconds each, so a fix-rerun cycle is what costs most and complete information is worth most.
#
# `--write` because a freshly generated project's badges all read "unknown", and the matrix is
# exercising the command that produces them. The pipeline the template ships runs the bare
# `preflight`, which compares instead.
QA_STEPS = ('preflight --write', 'document')
# The dependency audit, run in one cell rather than all of them. Every cell resolves the same
# lockfile and ships the same `vendor.txt`, so the audit's answer cannot differ between them —
# what differed was the exposure: nine jobs each querying the advisory database for ~125
# packages, where one transient service error fails a cell for a reason that has nothing to do
# with the template. It rides with the matured cell rather than carrying a knob of its own,
# there being one of those and a dependency audit belonging to a day-two project anyway. It
# still runs, so the `<PROJECT>_SECURITY_OVERRIDE` plumbing below and the `.security-overrides`
# expiry mechanism are still exercised, and `test.test` audits its own project too.
#
# Last, as in the generated project's own registry: it reports on the world rather than on this
# tree, so the top of a cell's log should be about the thing under test.
AUDIT_STEP = 'secure.audit'
# Run after the writers: a project whose derived files were just written has to satisfy the
# read-only gate the pipeline runs. A failure here is the writer and the checker disagreeing
# about a value, which is invisible to a run that only ever writes.
QA_SETTLE_STEP = 'preflight'
TEMPLATE_SECURITY_OVERRIDE_ENV = 'TEMPLATE_SECURITY_OVERRIDE'
SECURITY_OVERRIDES_FILE = PROJECT_ROOT_DIRECTORY / '.security-overrides'


def read_template_overrides():
    """Return comma-joined entries from the parent `.security-overrides` file.

    Entries are validated and parsed by the inner template's `secure.audit`
    task when the merged string is forwarded via `<PROJECT>_SECURITY_OVERRIDE`,
    so the parent only needs to strip `#` comments and blank lines.
    """
    if not SECURITY_OVERRIDES_FILE.exists():
        return ''
    entries = []
    for raw in SECURITY_OVERRIDES_FILE.read_text(encoding='utf-8').splitlines():
        entry = raw.split('#', 1)[0].strip()
        if entry:
            entries.append(entry)
    return ','.join(entries)


def template_uv_version() -> str:
    """Return the uv version the template currently pins.

    Read from the template source rather than hardcoded, so it follows `maintain.bump-uv`
    automatically. Used to pin what generation stamps during the template's own tests.

    Raises:
        RuntimeError: If the template has no exact `required-version` to read.
    """
    match = re.search(
        r'^required-version = "==([^"]+)"$', TEMPLATE_PYPROJECT.read_text(encoding='utf-8'), re.MULTILINE
    )
    if not match:
        msg = f'no exact [tool.uv] required-version found in {TEMPLATE_PYPROJECT}'
        raise RuntimeError(msg)
    return match.group(1)


def generation_env() -> dict:
    """Environment for invoking copier in tests: pins the uv version generation stamps."""
    return {UV_VERSION_ENV: template_uv_version()}


def version_sort_key(version: str) -> tuple[int, ...]:
    """Sort key for dotted version strings so 3.10 sorts above 3.9."""
    return tuple(int(part) for part in version.split('.'))


def base_context() -> dict:
    """Widest supported context, derived from copier.yml's python-version choices."""
    copier_data = yaml.safe_load((PROJECT_ROOT_DIRECTORY / 'copier.yml').read_text(encoding='utf-8'))
    known_versions = sorted(copier_data['min_python_version']['choices'], key=version_sort_key)
    return {'min_python_version': known_versions[0], 'max_python_version': known_versions[-1]}


def combo_context(*, git_hosting_service: str, integrate_dependency_track: bool, integrate_pages: bool) -> dict:
    """Matrix-cell context: widest Python range plus the three binary template knobs."""
    return {
        **base_context(),
        'git_hosting_service': git_hosting_service,
        'integrate_dependency_track': integrate_dependency_track,
        'integrate_pages': integrate_pages,
    }


def combo_label(*, git_hosting_service: str, integrate_dependency_track: bool, integrate_pages: bool, mature: bool = False) -> str:
    """Stable short label for log files and CI job names: e.g. ``gh-dep1-pages0``."""
    host_short = 'gh' if git_hosting_service == 'github' else 'gl'
    suffix = '-mature' if mature else ''
    return f'{host_short}-dep{int(integrate_dependency_track)}-pages{int(integrate_pages)}{suffix}'


def matrix_combos() -> list[dict]:
    """Cartesian product over git_hosting_service x integrate_dependency_track x integrate_pages."""
    return [
        {
            'label': combo_label(
                git_hosting_service=host,
                integrate_dependency_track=dep_track,
                integrate_pages=pages,
            ),
            'git_hosting_service': host,
            'integrate_dependency_track': dep_track,
            'integrate_pages': pages,
        }
        for host in ('github', 'gitlab')
        for dep_track in (False, True)
        for pages in (False, True)
    ]


def qa_sequence(*, audit: bool) -> tuple[str, ...]:
    """The steps one matrix cell runs, in order: the writers, the audit, then the gate.

    A function rather than a tuple literal in `run_combo`, so what a cell runs is a thing this
    suite can ask about. The guard it replaces asserted `secure.audit` was in `QA_STEPS`, which
    stopped meaning anything when the audit moved out of that tuple.
    """
    return (*QA_STEPS, *((AUDIT_STEP,) if audit else ()), QA_SETTLE_STEP)


def qa_cells() -> list[dict]:
    """Cells `test.matrix` runs: every generation shape, plus one matured project.

    A generated project is a day-one project: the scaffolded smoke test keeps coverage at 100%
    and the ratchet dormant, and there is no remote for the CI badge to name. That leaves the
    ratchet, the coverage floor and the badge slug unexercised by the eight knob cells, which
    differ only in what copier renders. The matured cell removes the smoke test and adds an
    origin, so those paths run too. It is one extra cell rather than a fourth axis because
    nothing it touches interacts with the knobs.
    """
    cells = [{**cell, 'mature': False} for cell in matrix_combos()]
    cells.append(
        {
            'label': combo_label(
                git_hosting_service='github',
                integrate_dependency_track=True,
                integrate_pages=True,
                mature=True,
            ),
            'git_hosting_service': 'github',
            'integrate_dependency_track': True,
            'integrate_pages': True,
            'mature': True,
        }
    )
    return cells
