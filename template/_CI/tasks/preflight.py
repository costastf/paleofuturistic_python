"""Preflight task definitions.

One registry, three consumers. Every check this project can run is declared once in ``STEPS``,
and the three things that want to run checks — the pre-commit hook, ``preflight``, and the CI
preflight job — all read that one declaration instead of keeping their own list. A check added
here reaches its tier automatically, and an invariant test asserts the commit-stage hook holds
exactly the per-file steps, so the hook cannot silently fall behind the registry.

Two ideas do most of the work:

*Scope decides the tier.* ``PER_FILE`` steps can answer correctly from the staged files alone,
so they run on every commit and cost time proportional to the change. ``WHOLE_PROGRAM`` steps
cannot: ty needs the callers of a changed signature, pyscn needs every file to know what is
dead or duplicated, the matrix needs the suite on every interpreter, and a wheel builds from
the whole tree or not at all. Those cost time proportional to the *project*, so they run once
per push instead of once per commit, which keeps commit latency flat as the project grows.
This is a rule about correctness, not speed: a whole-program check narrowed to a diff does not
run faster, it answers wrongly.

*Write mode and check mode are the same steps.* ``preflight`` brings the derived files up to
date; ``preflight --check`` runs the identical registry and fails on anything it would have
changed. Only ``build`` and ``artifacts`` differ between the two, and each differs by swapping
one callable, not by taking a separate path. Nothing in this file re-implements a check for the
verifying side, because that is how a gate drifts from the generator it guards.

*No whole-project run edits your code.* What ``preflight`` writes is derived — the four badges
and the coverage ratchet — never source. Formatting is verified here and fixed either by a
deliberate ``./workflow.cmd format`` or by the commit hook, which fixes only the files you just
staged and hands the result back through pre-commit's "files were modified by this hook". The
alternative was a command you run before opening a pull request quietly reformatting files you
were not looking at and folding them into your commit. ``fixes_source`` on a step and ``fix``
on ``run_scope`` are what enforce it; see ``Step.runner``.

Note that check mode still writes ``reports/`` — pytest's coverage JSON and pyscn's analysis
are the *inputs* the artifact comparison reads, and they are gitignored derived files. What
neither mode touches is source, and what check mode additionally leaves alone is every tracked
file: README.md and pyproject.toml.
"""

import re
from collections.abc import Callable, Iterator
from functools import partial
from typing import NamedTuple, cast

from invoke import Collection, Context, Task, task

from .build import build
from .document import update_package_version_badge, update_python_badge
from .format_ import ruff_format
from .lint import complexipy, format_check, pylint, ruff_lint, ty
from .quality import pyscn_check, pyscn_json_report, update_pyscn_badge
from .secure import audit
from .shared import logged, run_steps
from .test import ratchet_fail_under, tox, update_coverage_badge

PER_FILE = 'per-file'
WHOLE_PROGRAM = 'whole-program'

# Which paths each per-file step accepts. These moved out of `.pre-commit-config.yaml`: with one
# hook for the whole bundle there is only one `files:` filter left, so the per-tool distinction
# has to live somewhere it can still be applied — and here it is one source of truth that the
# invariant suite can read, rather than six YAML patterns nobody diffs.
CODE_FILES = re.compile(r'^(_CI/tasks/|src/|tests/).*\.py$')
SRC_FILES = re.compile(r'^src/.*\.py$')

FIX_COMMAND = './workflow.cmd preflight'


class Step(NamedTuple):
    """One check, with everything the three consumers need to know about it.

    Attributes:
        name: Display name, and the identifier the invariant tests match hooks against.
        scope: ``PER_FILE`` or ``WHOLE_PROGRAM``. See the module docstring — this is what
            assigns the step to the commit tier or the push tier.
        check: The callable to run in check mode.
        write: The callable to run in write mode, when it differs from ``check``. ``artifacts``
            writes derived values where its check compares them; ``format`` formats where its
            check merely reports, but only for the staged bundle (see ``fixes_source``). Every
            other step is read-only and leaves this None.
        files: Which paths the step accepts, for per-file steps handed a staged subset.
        network: True for steps that reach the network, which are opt-in — a push should not
            fail because a train went into a tunnel.
        fixes_source: True when the write variant edits the project's own code rather than a
            derived file. Only the staged bundle may run one — see ``runner``.
    """

    name: str
    scope: str
    check: Callable[..., None]
    write: Callable[..., None] | None = None
    files: re.Pattern[str] | None = None
    network: bool = False
    fixes_source: bool = False

    def runner(self, *, write: bool, fix: bool) -> Callable[..., None]:
        """Return the callable this step uses in the requested mode.

        ``fix`` is what separates the two entry points, and only ``preflight.staged`` passes
        it. A write variant that edits *source* is reachable only through that hook, where the
        files are ones the author just staged and pre-commit's "files were modified by this
        hook" puts the result in front of them. No whole-project run can reach it, so
        ``preflight`` cannot quietly reformat a file nobody was looking at and fold the change
        into someone's commit. Write variants that produce *derived* files — the badges, the
        coverage ratchet — are unaffected: computing those is what write mode is for.
        """
        if self.write is None or not write:
            return self.check
        if self.fixes_source and not fix:
            return self.check
        return self.write


def formatting(context: Context, paths: str = '') -> None:
    """Verify formatting, and name the command that fixes it.

    The gate reports rather than reformats, so it owes the reader the one-line way out — the
    same courtesy the derived-files step extends when a badge is stale. Fixing is a deliberate
    `./workflow.cmd format`, or the commit hook doing it to files you staged.

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

    The analysis runs in both modes because its JSON report is what the ``artifacts`` step
    compares the badge against — the gate alone writes no report and so has no grade to offer,
    which is the reason the badge used to sit at "not rated" forever. Writing the badge is the
    ``artifacts`` step's job, which keeps exactly one writer for it.

    Only the JSON report, though. pyscn allows one output format per run, so an HTML report
    would mean a second full analysis printing a second identical summary table — and nothing
    in this path opens an HTML report. `quality.pyscn-analyze` is where that is worth paying
    for, because it opens the thing it produced.
    """
    run_steps(pyscn_json_report, pyscn_check)(context)


@logged('preflight.artifacts')
def artifacts(context: Context, *, write: bool) -> None:  # noqa: ARG001
    """Bring every derived value committed to the repository up to date, or verify it.

    Decorated, unlike the other two wrappers here, because it is the only step whose work is
    entirely its own: `formatting` and `pyscn` delegate to tasks that announce themselves, so
    they are already bracketed in the log. This one wrote nothing to the log at all when every
    derived value was already correct — which is the case you most want evidence of, since
    verifying the badges and the ratchet is the one thing `preflight` does that no other step
    covers. Silence read as "it did not run".

    The four README badges and the coverage ratchet's ``fail_under`` are all computed from
    reports produced earlier in this same run, so by the time this step executes the inputs
    exist. In check mode nothing is written and every stale value is collected before failing,
    so one run tells you everything you have to fix rather than one thing per run.

    Raises:
        SystemExit: In check mode, if any derived value is stale or its input is missing.
    """
    reasons = [
        reason
        for reason in (
            update_package_version_badge(write=write),
            update_python_badge(write=write),
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
    if not write:
        print(f'Run `{FIX_COMMAND}` and commit the result.')
        raise SystemExit(1)


STEPS = (
    Step('format', PER_FILE, check=formatting, write=ruff_format, files=CODE_FILES, fixes_source=True),
    Step('ruff', PER_FILE, check=ruff_lint, files=CODE_FILES),
    Step('pylint', PER_FILE, check=pylint, files=CODE_FILES),
    Step('complexipy', PER_FILE, check=complexipy, files=SRC_FILES),
    Step('ty', WHOLE_PROGRAM, check=ty),
    Step('pyscn', WHOLE_PROGRAM, check=pyscn),
    # The whole matrix, not one interpreter. A single-interpreter gate would leave the one
    # thing CI could tell you that you could not have known locally, and the project promises
    # every version in `env_list`. It costs about one extra suite-length, because the envs run
    # in parallel. `test.pytest` remains the fast inner-loop task; this is the gate.
    Step('tox', WHOLE_PROGRAM, check=tox),
    # The build badge is the one derived value that records an *event* — what happened when
    # the package was last built — rather than a value recomputable from a report. So write
    # mode records it, and check mode passes `badge=False` and leaves it alone: README.md is
    # tracked, and check mode touches no tracked file. That does mean a stale build badge is
    # the one thing `--check` cannot catch. It is also the one badge CI could never fix, since
    # its checkout has no credentials and its token is read-only.
    Step('build', WHOLE_PROGRAM, check=partial(build, badge=False), write=partial(build, badge=True)),
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


def plan_scope(  # noqa: PLR0913
    scope: str | None,
    *,
    write: bool,
    paths: str = '',
    network: bool = False,
    fix: bool = False,
) -> list[tuple[Callable[[Context], None], bool]]:
    """Return ``(runner, writes_derived_files)`` for every step in ``scope``, in registry order.

    The second element is what lets ``run_scope`` refuse to write from a failing run: it is
    True for a step whose callable in *this* mode writes a derived file — ``artifacts`` and the
    build badge. A source fixer is not one of those; it belongs to the staged bundle, where the
    author is standing right there.
    """
    planned: list[tuple[Callable[[Context], None], bool]] = []
    for step in steps_for(scope, network=network):
        writes_derived = write and step.write is not None and not step.fixes_source
        runner = step.runner(write=write, fix=fix)
        if step.scope == WHOLE_PROGRAM:
            planned.append((runner, writes_derived))
            continue
        narrowed = scoped_paths(step, paths)
        if narrowed is None:
            continue
        planned.append((partial(runner, paths=narrowed), writes_derived))
    return planned


def run_scope(  # noqa: PLR0913
    context: Context,
    scope: str | None,
    *,
    write: bool,
    paths: str = '',
    network: bool = False,
    fix: bool = False,
) -> None:
    """Run every registry step in ``scope``, accumulating failures.

    Every step runs even after one fails, so a single run tells you everything that is wrong
    rather than one thing per run — except the steps that *write* derived files, which are
    skipped once anything before them has failed. A badge or a coverage bar computed from a
    tree whose checks just failed is a claim the tree does not support: this is what stopped
    `preflight` reporting "Updated build badge to passing" on a run that went on to fail, and
    writing a grade-A pyscn badge over a project whose tests were red.

    Skipped rather than reordered, so a failure late in the registry does not retroactively
    undo an earlier write. `secure.audit` is deliberately last and opt-in, which means an
    advisory published this morning does not stop your coverage badge from updating — it says
    nothing about whether the derived values are right.

    Check mode is unaffected: nothing is written there, and the comparison is exactly the
    reporting that benefits from running everything.

    Args:
        context: Invoke context.
        scope: Which scope to run, or None for the whole registry.
        write: Run each step's write-mode callable, where it has one.
        paths: Space-separated paths to narrow per-file steps to.
        network: Include network steps.
        fix: Allow the write variants that edit source. Only the staged bundle asks for this.

    Raises:
        SystemExit: If any step failed, after every step that could still run has run.
    """
    # `run_steps` is not used here because it cannot express the skip: it runs everything it is
    # given. The accumulate-and-report-at-the-end behaviour is the same.
    failed = False
    skipped = False
    for runner, writes_derived in plan_scope(scope, write=write, paths=paths, network=network, fix=fix):
        if failed and writes_derived:
            skipped = True
            continue
        try:
            runner(context)
        except SystemExit:
            failed = True
    if skipped:
        print(f'Derived files left alone: a check failed, so `{FIX_COMMAND}` has nothing trustworthy to write.')
    if failed:
        raise SystemExit(1)


@task
@logged('preflight.staged')
def staged(context: Context, paths: str = '') -> None:
    """Run the checks that can be judged from the staged files alone.

    This is what the pre-commit hook calls, as a single invocation: `./workflow.cmd` costs
    about 1.3s of interpreter and import startup before any tool runs, so the six hooks this
    replaces spent most of a commit's budget starting up rather than checking. One hook pays
    that once.

    Formatting is applied rather than merely reported, as it was before: these are files the
    author staged, so rewriting them is fair game, and pre-commit's "files were modified by
    this hook" is the intended signal to stage the result. The tracked files nobody staged —
    README.md, pyproject.toml — belong to `preflight` and are never touched from here.

    Args:
        context: Invoke context.
        paths: Space-separated paths, normally the staged files. Each step sees only the
            paths it accepts, and is skipped when none of them are its business. Defaults to
            the whole project.
    """
    run_scope(context, PER_FILE, write=True, fix=True, paths=paths)


@task
@logged('preflight')
def preflight(context: Context, check: bool = False, audit_dependencies: bool = False) -> None:
    """Run every check this project has, and bring the derived files up to date.

    The command to run before you open a pull request, and — as `--check` — the whole of the
    CI pipeline as well as the pre-push hook. It verifies formatting, lints, type-checks, runs
    pyscn, runs the test matrix and builds the wheel; then write mode writes the badges and the
    coverage ratchet, and check mode compares them instead and fails listing everything out of
    date. Neither mode edits source: unformatted code fails here and is fixed by
    `./workflow.cmd format`.

    There is deliberately no flag for running a lighter version. The pipeline runs this exact
    command, so any switch that trimmed it would be a documented way to make the two disagree
    — and the obvious thing to reach for when in a hurry. The knob that shortens the matrix is
    `env_list` in pyproject.toml, which shortens it for CI too and so cannot open a gap. For
    fast feedback while writing code, the individual tasks are still there: `test.pytest`,
    `lint.pylint --paths=…`.

    Args:
        context: Invoke context.
        check: Verify instead of write. Nothing tracked is modified; a stale badge or an
            unratcheted `fail_under` fails the run.
        audit_dependencies: Also run the dependency audit. Off by default, and not because of
            the network alone: an audit's answer depends on the advisory database on the day it
            runs rather than on this tree, so it can never have the property that makes the
            rest of this worth gating a push on. It has its own homes — a daily schedule, the
            dependency-change job, and `release.dist` before publishing. This flag is for
            running it here too, when you want everything in one command.
    """
    run_scope(context, None, write=not check, network=audit_dependencies)


namespace = Collection('preflight')
namespace.add_task(cast(Task, preflight), default=True, name='all')
namespace.add_task(cast(Task, staged))
