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
dead or duplicated, pytest needs the suite. Those cost time proportional to the *project*, so
they run once per push instead of once per commit, which keeps commit latency flat as the
project grows. This is a rule about correctness, not speed: a whole-program check narrowed to a
diff does not run faster, it answers wrongly.

*Write mode and check mode are the same steps.* ``preflight`` brings the tree up to date;
``preflight --check`` runs the identical registry and fails on anything it would have changed.
Only ``format`` and ``artifacts`` differ between the two, and they differ by swapping one
callable, not by taking a separate path. Nothing in this file re-implements a check for the
verifying side, because that is how a gate drifts from the generator it guards.

Note that check mode still writes ``reports/`` — pytest's coverage JSON and pyscn's analysis
are the *inputs* the artifact comparison reads, and they are gitignored derived files. What
check mode never touches is a tracked file: README.md and pyproject.toml.
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
from .quality import pyscn_analyze_only, pyscn_check, update_pyscn_badge
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
        write: The callable to run in write mode, when it differs from ``check``. ``format``
            formats where its check merely reports; ``artifacts`` writes derived values where
            its check compares them. Every other step is read-only and leaves this None.
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


def pyscn(context: Context) -> None:
    """Analyse with pyscn and gate on the result, without touching the badge.

    The analysis runs in both modes because its JSON report is what the ``artifacts`` step
    compares the badge against — the gate alone writes no report and so has no grade to offer,
    which is the reason the badge used to sit at "not rated" forever. Writing the badge is the
    ``artifacts`` step's job, so ``badge=False`` here keeps exactly one writer for it.
    """
    run_steps(partial(pyscn_analyze_only, badge=False), pyscn_check)(context)


def artifacts(context: Context, *, write: bool) -> None:  # noqa: ARG001
    """Bring every derived value committed to the repository up to date, or verify it.

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
    Step('format', PER_FILE, check=format_check, write=ruff_format, files=CODE_FILES),
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


def run_scope(context: Context, scope: str | None, *, write: bool, paths: str = '', network: bool = False) -> None:
    """Run every registry step in ``scope``, accumulating failures.

    Args:
        context: Invoke context.
        scope: Which scope to run, or None for the whole registry.
        write: Run each step's write-mode callable, where it has one.
        paths: Space-separated paths to narrow per-file steps to.
        network: Include network steps.

    Raises:
        SystemExit: If any step failed, after all of them have run.
    """
    planned: list[Callable[[Context], None]] = []
    for step in steps_for(scope, network=network):
        if step.scope == WHOLE_PROGRAM:
            planned.append(step.runner(write=write))
            continue
        narrowed = scoped_paths(step, paths)
        if narrowed is None:
            continue
        planned.append(partial(step.runner(write=write), paths=narrowed))
    run_steps(*planned)(context)


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
    run_scope(context, PER_FILE, write=True, paths=paths)


@task
@logged('preflight')
def preflight(context: Context, check: bool = False, audit_dependencies: bool = False) -> None:
    """Run every check this project has, and bring the derived files up to date.

    The command to run before you open a pull request, and — as `--check` — the whole of the
    CI pipeline as well as the pre-push hook. Write mode formats, lints, type-checks, runs
    pyscn, runs the test matrix, builds the wheel, then writes the badges and the coverage
    ratchet. Check mode runs the identical steps, writes no tracked file, and fails listing
    everything that is out of date.

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
