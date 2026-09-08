"""Preflight task definitions.

One registry, three consumers. Every check is declared once in ``STEPS``; the pre-commit hook,
``preflight`` and the CI preflight job all read that declaration rather than keeping their own
lists, so a check added here reaches its tier without editing three files. An invariant asserts
the commit-stage hook holds exactly the per-file steps.

*Scope decides the tier.* ``PER_FILE`` steps answer correctly from the staged files alone, so
they run on every commit and cost time proportional to the change. ``WHOLE_PROGRAM`` steps
cannot: ty needs the callers of a changed signature, pyscn needs every file to know what is dead
or duplicated, the matrix needs the suite on every interpreter, and a wheel builds from the whole
tree or not at all. Those cost time proportional to the *project*, so they run once per push,
which keeps commit latency flat as the project grows. It is a rule about correctness rather than
speed: a whole-program check narrowed to a diff does not run faster, it answers wrongly.

*Verifying is the default; writing is a flag.* ``preflight`` compares the derived files against
what the tools measured; ``preflight --write`` updates them. So the bare command is what the
hooks and the pipeline run, and reproducing a pipeline failure needs no flag. ``artifacts`` is
the only step that behaves differently between the two, and it does so by swapping one callable —
nothing here re-implements a check for the verifying side, which is how a gate drifts from its
generator.

*Nothing here edits your code.* What ``--write`` writes is derived: the badges and the coverage
ratchet. No step has a source-writing variant, so this file has no notion of fixing at all.
Formatting is applied by ``./workflow.cmd format``, named for the mutation it performs.

The default does write ``reports/`` — pytest's coverage JSON and pyscn's analysis are the
*inputs* the comparison reads, and both are gitignored. What it never touches is a tracked file.
"""

import re
from collections.abc import Callable, Iterator
from functools import partial
from typing import NamedTuple, cast

from invoke import Collection, Context, Task, task

from .build import build
from .document import build as document_build
from .document import update_package_version_badge, update_pipeline_badge, update_python_badge
from .lint import commitizen, complexipy, format_check, pylint, ruff_lint, ty
from .quality import pyscn_check, pyscn_json_report, update_pyscn_badge
from .secure import audit
from .shared import logged, run_steps, staged_files
from .test import ratchet_fail_under, tox_matrix, update_coverage_badge

PER_FILE = 'per-file'
WHOLE_PROGRAM = 'whole-program'

# Which paths each per-file step accepts. These moved out of `.pre-commit-config.yaml`: with one
# hook for the whole bundle there is only one `files:` filter left, so the per-tool distinction
# has to live somewhere it can still be applied — and here it is one source of truth that the
# invariant suite can read, rather than six YAML patterns nobody diffs.
CODE_FILES = re.compile(r'^(_CI/tasks/|src/|tests/).*\.py$')
SRC_FILES = re.compile(r'^src/.*\.py$')

FIX_COMMAND = './workflow.cmd preflight --write'


class Step(NamedTuple):
    """One check, with everything the three consumers need to know about it.

    Attributes:
        name: Display name, and the identifier the invariant tests match hooks against.
        scope: ``PER_FILE`` or ``WHOLE_PROGRAM``. See the module docstring — this is what
            assigns the step to the commit tier or the push tier.
        check: The callable to run in check mode.
        write: The callable for write mode, where it differs from ``check``. Only steps that
            produce *derived* files have one.
        files: Which paths the step accepts, for per-file steps handed a staged subset.
        network: True for steps that reach the network, which are opt-in — a push should not
            fail because a train went into a tunnel.
    """

    name: str
    scope: str
    check: Callable[..., None]
    write: Callable[..., None] | None = None
    files: re.Pattern[str] | None = None
    network: bool = False

    def runner(self, *, write: bool) -> Callable[..., None]:
        """Return the callable this step uses in the requested mode."""
        return self.write if write and self.write is not None else self.check


def formatting(context: Context, paths: str = '') -> None:
    """Verify formatting, and name the command that fixes it.

    The gate reports rather than reformats, so it owes the reader the way out.

    Raises:
        SystemExit: If anything is not formatted.
    """
    try:
        format_check(context, paths=paths)
    except SystemExit:
        print('Run `./workflow.cmd format` to fix the formatting reported above.')
        raise


def pyscn(context: Context) -> None:
    """Analyse with pyscn and gate on the result, without touching the badge.

    The analysis runs in both modes: its JSON report is what the ``artifacts`` step compares the
    badge against, and ``pyscn check`` writes no report, so it has no grade to offer. Writing
    the badge belongs to ``artifacts``, which keeps one writer for it.

    JSON only. pyscn allows one output format per run, so an HTML report costs a second full
    analysis and a second identical summary table, and nothing in this path opens one.
    `quality.pyscn-analyze` does, which is where that is worth paying for.
    """
    run_steps(pyscn_json_report, pyscn_check)(context)


@logged('preflight.artifacts')
def artifacts(context: Context, *, write: bool) -> None:
    """Bring every derived value committed to the repository up to date, or verify it.

    The badges and the coverage ratchet's ``fail_under``, all computed from reports produced
    earlier in this same run, so the inputs exist by the time this executes. Verifying collects
    every stale value before failing, so one run tells you everything to fix.

    Decorated, unlike the other wrappers here, because its work is entirely its own —
    `formatting` and `pyscn` delegate to tasks that announce themselves. Without a banner it
    printed nothing at all when every value was already correct, which is the case most worth
    having evidence of.

    Raises:
        SystemExit: In check mode, if any derived value is stale or its input is missing.
    """
    reasons = [
        reason
        for reason in (
            update_package_version_badge(write=write),
            update_python_badge(write=write),
            update_pipeline_badge(context, write=write),
            update_coverage_badge(write=write),
            update_pyscn_badge(write=write),
            ratchet_fail_under(write=write),
        )
        if reason
    ]
    if not reasons:
        return
    for reason in reasons:
        print(reason)
    # A reason survives `--write` only when a value could not be computed at all — a report
    # missing, or unreadable. Both modes fail on it: "wrote nothing, exited 0" is the shape
    # that lets a stale badge reach main through the command meant to refresh it.
    if not write:
        print(f'Run `{FIX_COMMAND}` and commit the result.')
    raise SystemExit(1)


STEPS = (
    Step('format', PER_FILE, check=formatting, files=CODE_FILES),
    Step('ruff', PER_FILE, check=ruff_lint, files=CODE_FILES),
    Step('pylint', PER_FILE, check=pylint, files=CODE_FILES),
    Step('complexipy', PER_FILE, check=complexipy, files=SRC_FILES),
    Step('ty', WHOLE_PROGRAM, check=ty),
    # `cz bump` derives the version and the changelog from commit messages, so their format is
    # a whole-program property of the history rather than of any file. The commit-msg hook
    # catches a bad message as it is written; this catches one that arrived any other way — an
    # unhooked clone, or `--no-verify`. Scoped to the commits this push adds, not to all of
    # history, which no run can fix — see `lint.unpushed_range`.
    Step('commitizen', WHOLE_PROGRAM, check=commitizen),
    # Early, being cheap: `properdocs build --strict` fails on a broken cross-reference or a
    # page missing from the nav in well under a second, and publishing happens on a release
    # tag, so without this step a bad link is first discovered by the release pipeline — after
    # the tag is pushed, the one moment there is no cheap way back.
    Step('docs', WHOLE_PROGRAM, check=document_build),
    Step('pyscn', WHOLE_PROGRAM, check=pyscn),
    # The whole matrix, not one interpreter: the project promises every version in `env_list`,
    # and a single-interpreter gate would leave that the one thing CI knows and you cannot. It
    # costs about one extra suite-length, the envs running in parallel. `test.pytest` is the
    # fast inner-loop task; this is the gate.
    #
    # `tox_matrix` rather than the `test.tox` task, which reports on the coverage badge and can
    # write it — this step runs inside a hook and a pipeline, where nothing may.
    Step('tox', WHOLE_PROGRAM, check=tox_matrix),
    Step('build', WHOLE_PROGRAM, check=build),
    # After pyscn and tox, which produce the reports it reads.
    Step(
        'artifacts',
        WHOLE_PROGRAM,
        check=partial(artifacts, write=False),
        write=partial(artifacts, write=True),
    ),
    Step('audit', WHOLE_PROGRAM, check=audit, network=True),
)


def steps_for(scope: str | None = None, *, network: bool = False) -> Iterator[Step]:
    """Yield the registry's steps, filtered by scope and by whether network steps are wanted.

    Args:
        scope: Keep only steps of this scope. None keeps every scope.
        network: Include steps that reach the network. They are excluded by default.
    """
    for step in STEPS:
        if scope is not None and step.scope != scope:
            continue
        if step.network and not network:
            continue
        yield step


def scoped_paths(step: Step, paths: str) -> str | None:
    """Return the subset of ``paths`` this step accepts, or None when it accepts none of them.

    An empty ``paths`` means "no subset was requested", and each task falls back to its own
    project-wide default. None is distinct from that: it means the step was handed files and
    none of them are its business, so it is skipped rather than widened to the whole project.
    """
    if not paths:
        return ''
    if step.files is None:
        return ''
    kept = [path for path in paths.split() if step.files.search(path)]
    return ' '.join(kept) if kept else None


def plan_scope(
    scope: str | None,
    *,
    write: bool,
    paths: str = '',
    network: bool = False,
) -> list[tuple[Callable[[Context], None], bool]]:
    """Return ``(runner, writes_derived_files)`` for every step in ``scope``, in registry order.

    The second element is what lets ``run_scope`` skip the derived-value steps after a failure,
    in either mode: their inputs are reports the failed step should have produced.
    """
    planned: list[tuple[Callable[[Context], None], bool]] = []
    for step in steps_for(scope, network=network):
        derived = step.write is not None
        runner = step.runner(write=write)
        if step.scope == WHOLE_PROGRAM:
            planned.append((runner, derived))
            continue
        narrowed = scoped_paths(step, paths)
        if narrowed is None:
            continue
        planned.append((partial(runner, paths=narrowed), derived))
    return planned


def run_scope(
    context: Context,
    scope: str | None,
    *,
    write: bool,
    paths: str = '',
    network: bool = False,
) -> None:
    """Run every registry step in ``scope``, accumulating failures.

    Every step runs even after one fails, so a single run reports everything that is wrong —
    except the derived-value steps, skipped once anything before them has failed, in either
    mode. A badge computed from a tree whose checks just failed is a claim the tree does not
    support, and comparing against one is worse: the reports it would read are the ones the
    failed step never produced.

    Skipped rather than reordered, so a late failure cannot retroactively undo an earlier
    write. `secure.audit` being last and opt-in also means an advisory published this morning
    does not stop a coverage badge updating; it says nothing about whether that badge is right.

    Verifying is unaffected: nothing is written, and the comparison *is* the reporting that
    benefits from running everything.

    Args:
        context: Invoke context.
        scope: Which scope to run, or None for the whole registry.
        write: Run each step's write-mode callable, where it has one.
        paths: Space-separated paths to narrow per-file steps to.
        network: Include network steps.

    Raises:
        SystemExit: If any step failed, after every step that could still run has run.
    """
    # Not `run_steps`, which cannot express the skip — it runs everything it is given. The
    # accumulate-and-report-at-the-end behaviour is the same.
    failed = False
    skipped = False
    for runner, derived in plan_scope(scope, write=write, paths=paths, network=network):
        if failed and derived:
            skipped = True
            continue
        try:
            runner(context)
        except SystemExit:
            failed = True
    if skipped:
        print(f'Derived files skipped: a check failed, so there is nothing trustworthy for `{FIX_COMMAND}` to')
        print('compare against or write — the reports they are computed from were not produced.')
    if failed:
        raise SystemExit(1)


@task
@logged('preflight.staged')
def staged(context: Context, paths: str = '') -> None:
    """Run the checks that can be judged from the staged files alone.

    What the pre-commit hook calls, in a single invocation: `./workflow.cmd` costs about 1.3s
    of interpreter and import startup before any tool runs, so one hook pays that once where
    four paid it four times.

    It reports rather than fixes, like every entry point here; `./workflow.cmd format` applies
    formatting.

    Args:
        context: Invoke context.
        paths: Space-separated paths to check. Defaults to the files staged for commit.
    """
    targets = paths or staged_files(context)
    if not targets:
        print('Nothing staged, so nothing to check. `./workflow.cmd preflight` checks the project.')
        return
    run_scope(context, PER_FILE, write=False, paths=targets)


@task
@logged('preflight')
def preflight(context: Context, write: bool = False, audit_dependencies: bool = False) -> None:
    """Run every check this project has, and bring the derived files up to date.

    The bare command is what the pre-push hook and the CI pipeline run, so reproducing a
    pipeline failure needs no flag. It verifies formatting, lints, type-checks, runs pyscn, runs
    the test matrix, builds the wheel, and compares the badges and the coverage ratchet against
    what the tools just measured, failing with everything out of date.

    `--write` updates those derived values. Opt-in, because a command named for an inspection
    should not modify the tree; commands named for a mutation may, which is why `format` and
    `release.bump` do.

    Neither mode edits source. Unformatted code fails here and is fixed by
    `./workflow.cmd format`, which is named for the mutation it performs.

    There is no flag for running a lighter version: the pipeline runs this exact command, so a
    switch that trimmed it would be a documented way to make the two disagree, and the obvious
    thing to reach for in a hurry. `env_list` in pyproject.toml is the knob that shortens the
    matrix, and it shortens CI with it. For fast feedback while writing code the individual
    tasks are there: `test.pytest`, `lint.pylint --paths=…`.

    Args:
        context: Invoke context.
        write: Update the derived values instead of comparing them. The same steps run either
            way.
        audit_dependencies: Also run the dependency audit. Off by default because its answer
            depends on the advisory database on the day it runs rather than on this tree, so it
            cannot have the property that makes the rest worth gating a push on. Its homes are
            a daily schedule, the dependency-change job, and `release.dist` before publishing;
            this flag runs it here as well.
    """
    run_scope(context, None, write=write, network=audit_dependencies)


namespace = Collection('preflight')
namespace.add_task(cast(Task, preflight), default=True, name='all')
namespace.add_task(cast(Task, staged))
