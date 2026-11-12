"""Invariants over this repository's own matrix runner."""

import json
import os
from pathlib import Path
from typing import NamedTuple

# conftest.py wires sys.path so _CI.tasks.* is importable; pytest loads it
# before this module, which is why no path setup is needed here.
from .support import (
    REPO_ROOT,
    exec_from,
)


def test_qa_steps_cover_what_preflight_does_not():
    """The matrix runs the generated project's own gate, plus the two things it leaves out.

    `preflight` covers format, lint, pyproject validation, ty, commit messages, the docs build,
    pyscn, the tox matrix, the wheel and the derived files, so naming those separately would
    re-run them in a different shape and leave the matrix with two lists of checks to keep in
    step — the same duplication the generated project's pipeline shed. What has to be listed is
    the one thing `preflight` deliberately omits: the dependency audit.

    The audit runs in one cell, not all five. Every cell resolves the same lockfile and ships the
    same `vendor.txt`, so its answer cannot differ between them, while its exposure does: five
    jobs querying an advisory database for ~125 packages each, where one transient service error
    fails a cell for a reason that has nothing to do with the template. It still has to run
    somewhere, because it is the step the `<PROJECT>_SECURITY_OVERRIDE` plumbing serves and the
    only automated run the `.security-overrides` expiry mechanism gates.
    """
    from _CI.tasks.configuration import AUDIT_STEP, QA_STEPS, qa_cells  # noqa: PLC0415

    assert AUDIT_STEP == 'secure.audit', 'the matrix no longer audits dependencies anywhere'
    assert AUDIT_STEP not in QA_STEPS, 'the audit is back in every cell'
    assert QA_STEPS == ('preflight --write',), 'the matrix runs something the generated gate already covers'

    # It rides with the matured cell rather than carrying a knob of its own, and there is
    # exactly one of those. Which cell actually audits is visible in the matrix logs rather
    # than here: a grep for how `run_combo` spells its argument would fail on a rename with
    # nothing broken.
    matured = [cell['label'] for cell in qa_cells() if cell['mature']]
    assert len(matured) == 1, f'expected exactly one matured cell to carry the audit, got {matured}'
    assert not any('audit' in cell for cell in qa_cells()), 'the audit has a knob of its own again'


def test_the_matrix_verifies_what_it_wrote():
    """The matrix runs the read-only gate after the writers, on a cell that has values to write.

    `preflight --write` alone cannot catch a writer and a checker disagreeing: it writes and is
    happy. Running the bare `preflight` afterwards asks the question the pipeline asks — is this
    tree consistent with its derived files? — about a tree whose derived files were just
    produced. A deadlock where writing a coverage floor makes the next run fail is invisible
    until something re-reads.

    The four knob cells have nothing interesting to write: a generated project keeps the
    scaffolded smoke test, so coverage is 100% and the ratchet stays dormant, and it has no
    remote for the CI badge to name. One matured cell removes both of those, which is where a
    disagreement can exist at all.
    """
    from _CI.tasks.configuration import QA_SETTLE_STEP, QA_STEPS, qa_cells  # noqa: PLC0415

    assert QA_SETTLE_STEP == 'preflight', 'the matrix no longer re-checks the tree it wrote'
    assert QA_SETTLE_STEP not in QA_STEPS, 'the gate has to run after the writers, not among them'

    matured = [cell for cell in qa_cells() if cell['mature']]
    assert len(matured) == 1, f'expected exactly one matured cell, got {[c["label"] for c in matured]}'

    from _CI.tasks.test import MATURE_ORIGIN, MATURE_TEST_MODULE  # noqa: PLC0415

    assert 'test_sanity' not in MATURE_TEST_MODULE, 'the ratchet stays dormant while test_sanity exists'
    assert MATURE_ORIGIN, 'without an origin the CI badge has no slug to write'


def test_exactly_one_matrix_cell_audits_its_dependencies(tmp_path):
    """Driving `run_combo` over every cell, `secure.audit` is run once across the whole matrix.

    Executed rather than read. The guard this replaces asserted `secure.audit` was in
    `QA_STEPS`, which implied execution until the audit moved out of that tuple; after that,
    reducing the step list so no cell audited at all left the suite green. Asserting
    `qa_sequence` in isolation is closer but still one refactor from `run_combo` ignoring it.

    Every cell resolves the same lockfile and ships the same `vendor.txt`, so the audit's answer
    cannot differ between them — what differs is the exposure, five concurrent jobs querying an
    advisory service about ~125 packages each.
    """
    runner_source = (REPO_ROOT / '_CI' / 'tasks' / 'test.py').read_text(encoding='utf-8')
    # `run_combo` was split so it reads in one pass; the two extracted helpers are exec'd
    # alongside it rather than stubbed, since `write_mature_project` is exactly the branch this
    # test does not otherwise exercise the content of, and `security_override_env` needs to
    # observe the same `os.environ`/`read_template_overrides` stubs the rest of this namespace
    # sets up, not new ones of its own.

    from _CI.tasks.configuration import PROJECT_SLUG, qa_sequence  # noqa: PLC0415

    workflow_commands: list[tuple[str, str]] = []
    current_label = {'value': ''}

    def record(command, cwd=None, env=None, log_file=None):  # noqa: ARG001
        if command.startswith('./workflow.cmd '):
            workflow_commands.append((current_label['value'], command.removeprefix('./workflow.cmd ')))
        return True

    class ComboWorkspace(NamedTuple):
        """Mirrors `_CI.tasks.test.ComboWorkspace`'s shape for this exec'd slice."""

        template_repo: Path
        output_root: Path

    namespace = {
        'json': json,
        'os': os,
        'Path': Path,
        'run_command': record,
        'untracked_after_qa': lambda _project: [],
        'report_failure': lambda *_: None,
        'generation_env': dict,
        'read_template_overrides': lambda: '',
        'base_context': lambda: {'min_python_version': '3.11'},
        'qa_sequence': qa_sequence,
        'PROJECT_SLUG': PROJECT_SLUG,
        'TEMPLATE_SECURITY_OVERRIDE_ENV': 'TEMPLATE_SECURITY_OVERRIDE',
        'DEFAULT_BRANCH': 'main',
        'MATURE_ORIGIN': 'git@example.invalid:acme/widget.git',
        'MATURE_TEST_MODULE': '"""{slug}."""\n',
        'MATURE_GATED_MODULE': '"""{slug} {boundary}."""\n',
        'ComboWorkspace': ComboWorkspace,
    }
    namespace = exec_from(runner_source, 'write_mature_project', 'security_override_env', 'run_combo', **namespace)

    from _CI.tasks.configuration import qa_cells  # noqa: PLC0415

    for cell in qa_cells():
        current_label['value'] = cell['label']
        project = tmp_path / cell['label'] / 'generated' / PROJECT_SLUG
        for directory in ('tests', f'src/{PROJECT_SLUG}'):
            (project / directory).mkdir(parents=True, exist_ok=True)
        assert namespace['run_combo'](
            namespace['ComboWorkspace'](tmp_path / 'template', tmp_path),
            {'min_python_version': '3.11'},
            cell['label'],
            mature=cell['mature'],
        ), f'{cell["label"]} failed with every command stubbed as successful'

    audited = [label for label, command in workflow_commands if command == 'secure.audit']
    assert len(audited) == 1, f'{len(audited)} cells audit their dependencies, not one: {audited}'
    matured = [cell['label'] for cell in qa_cells() if cell['mature']]
    assert audited == matured, f'the audit rides with {audited} rather than the matured cell {matured}'

    # And every cell still writes, documents and then re-checks itself.
    for cell in qa_cells():
        ran = [command for label, command in workflow_commands if label == cell['label']]
        assert ran == list(qa_sequence(audit=cell['mature'])), f'{cell["label"]} ran {ran}'
