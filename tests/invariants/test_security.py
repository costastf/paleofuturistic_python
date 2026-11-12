"""Invariants over the dependency audit, its suppressions and the SBOM."""

import ast
import os
import re
import tomllib
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

# conftest.py wires sys.path so _CI.tasks.* is importable; pytest loads it
# before this module, which is why no path setup is needed here.
from .support import (
    REPO_ROOT,
    calls_in,
    command_strings,
    exec_from,
    function_named,
    load_generated_configuration,
    suppression_calls,
)


def test_sbom_file_path_is_inside_package(generated_project):
    """The SBOM file lands under `src/<slug>/` so `uv build` ships it inside the wheel."""
    project, _ = generated_project
    configuration = (project / '_CI' / 'tasks' / 'configuration.py').read_text(encoding='utf-8')
    assert "SBOM_FILE = Path('src') / PROJECT_NAME / 'sbom.cdx.json'" in configuration


def test_no_dependency_track_remnants(generated_project):
    """No generated file carries the removed Dependency-Track upload, its knob, or its page.

    A stray `OWASP_DTRACK_*` read would make a release fail on a secret nobody is told to set,
    and a stray doc link would point at a page that no longer ships. Naming Dependency-Track
    as one SCA platform a team might feed the SBOM to is fine, so the name alone is not matched.
    """
    project, _ = generated_project
    pattern = re.compile(r'OWASP_DTRACK|sbom[_-]upload|integrate_dependency_track|upload-an-sbom-to-dependency-track')
    hits = [
        str(path.relative_to(project))
        for path in project.rglob('*')
        if path.is_file()
        and '_CI/lib/vendor' not in path.as_posix()
        and pattern.search(path.read_text(encoding='utf-8', errors='ignore'))
    ]
    assert not hits, f'Dependency-Track remnants in: {hits}'


def test_sbom_and_slug_helpers_sanitize_the_remote(generated_project):
    """Every consumer of `git remote get-url origin` sanitizes it before use.

    `parse_remote_url` counts as sanitizing: it calls `strip_credentials` itself, which
    `test_parse_remote_url_strips_credentials` pins down.
    """
    project, cell = generated_project
    sbom_py = (project / '_CI' / 'tasks' / 'sbom.py').read_text(encoding='utf-8')
    assert 'strip_credentials' in sbom_py, 'sbom.py does not sanitize the origin URL'
    host_py = (project / '_CI' / 'tasks' / f'{cell["git_hosting_service"]}.py').read_text(encoding='utf-8')
    sanitizers = ('strip_credentials', 'parse_remote_url')
    assert any(name in host_py for name in sanitizers), 'origin_slug() does not sanitize the origin URL'


def test_building_a_wheel_does_not_depend_on_the_advisory_database(generated_project):
    """`build` composes the SBOM and builds; it does not audit.

    The SBOM belongs to the build — `uv build` ships it inside the wheel, and it is derived
    from the lockfile and the tree. The audit does not: its answer depends on the advisory
    database on the day it runs, so bundling them meant a newly published CVE made it
    impossible to produce a wheel from code that built yesterday, blocking a hotfix on an
    advisory it had nothing to do with.
    """
    project, _ = generated_project
    build_py = (project / '_CI' / 'tasks' / 'build.py').read_text(encoding='utf-8')
    assert 'run_steps(sbom, package)' in build_py, 'build no longer composes the SBOM before building'
    assert 'from .secure import sbom' in build_py, 'build imports more of secure than the SBOM half'
    # The word appears in the docstring explaining its absence; what must not appear is a call.
    assert 'audit(' not in build_py, 'build audits dependencies again, so a fresh CVE blocks every wheel'


def test_publishing_audits_before_it_builds(generated_project):
    """`release.dist` audits, so the decoupling above does not leave publishing unguarded.

    Publishing is the moment the outside world is exposed to what these dependencies
    contain, and the one place where refusing to proceed protects somebody.
    """
    project, _ = generated_project
    release_py = (project / '_CI' / 'tasks' / 'release.py').read_text(encoding='utf-8')
    dist = release_py.split("@logged('release.dist')", 1)[1].split('@task', 1)[0]
    assert 'audit(context)' in dist, 'release.dist publishes without auditing'
    assert dist.index('audit(context)') < dist.index('build(context)'), 'the audit runs after the build'


def test_documented_override_format_is_actually_accepted(generated_project):
    """Every `.security-overrides` example in the docs parses as a real entry.

    The how-to previously documented a space-separated `<ID> <DATE> <justification>` form
    that `validate_override_entry` rejects outright, so following the docs broke the build.
    """
    project, _ = generated_project
    pattern = load_generated_configuration(project).IGNORE_PATTERN
    # Every doc, not just the how-to: the same wrong format was also sitting in the
    # configuration-files reference, where a check scoped to one page could not see it.
    examples = []
    for doc_path in sorted((project / 'docs').rglob('*.md')):
        doc = doc_path.read_text(encoding='utf-8')
        # ```text fences hold override-file content; sample command output lives in
        # ```console fences and is deliberately not a valid entry.
        for block in re.findall(r'^```text\n(.*?)^```', doc, re.MULTILINE | re.DOTALL):
            for line in block.splitlines():
                entry = line.strip()
                # Skip comments and `<PLACEHOLDER>` format specs; the rest must be real.
                if not entry or entry.startswith('#') or '<' in entry:
                    continue
                examples.append((doc_path.relative_to(project), entry))
    # Prose can also spell the format out inline; catch the space-separated shape directly.
    for doc_path in sorted((project / 'docs').rglob('*.md')):
        doc = doc_path.read_text(encoding='utf-8')
        bad = re.search(r'`<[A-Za-z_-]*(VULN|vuln)[A-Za-z_-]*>\s+<YYYY-MM-DD>', doc)
        assert not bad, f'{doc_path.relative_to(project)} documents a space-separated override format'
    assert examples, 'no override examples found anywhere in the docs'
    for source, example in examples:
        assert pattern.fullmatch(example), f'{source}: documented example {example!r} would be rejected'


def test_suppressions_are_validated_whole_not_scanned(generated_project):
    """Suppression entries are matched with `fullmatch`, never scanned out of a joined string.

    `finditer` over the merged list failed open in the worst direction: a mistyped expiry
    like `CVE-1::2020-1-1` does not match the optional expiry group, so the bare id
    matched and the entry became a *permanent* suppression, with `2020`, `1`, `1` added
    as extra ids.
    """
    project, _ = generated_project
    secure_py = (project / '_CI' / 'tasks' / 'secure.py').read_text(encoding='utf-8')
    audit_source = secure_py.split("@logged('secure.audit')", 1)[1].split('\n@task', 1)[0]
    assert 'IGNORE_PATTERN.finditer' not in audit_source, 'audit still scans for id-shaped substrings'
    assert 'parse_suppressions' in audit_source
    assert 'IGNORE_PATTERN.fullmatch' in secure_py


def test_untracked_suppression_sources_require_an_expiry(generated_project):
    """`--ignore` and the env var must carry an expiry; `.security-overrides` need not.

    Those two leave no trace in the repo, so a permanent entry there could mute a finding
    with no code change to review.
    """
    project, _ = generated_project
    secure_py = (project / '_CI' / 'tasks' / 'secure.py').read_text(encoding='utf-8')
    calls = suppression_calls(secure_py)
    cli = next(kwargs for label, kwargs in calls.items() if '--ignore' in label)
    env = next(kwargs for label, kwargs in calls.items() if 'SECURITY_OVERRIDE_ENV' in label)
    assert cli.get('require_expiry') == 'True', '--ignore does not require an expiry'
    assert env.get('require_expiry') == 'True', 'the env var does not require an expiry'
    # The file keeps permanent entries: load_overrides_file must not opt in.
    file_loader = secure_py.split('def load_overrides_file', 1)[1].split('\n@task', 1)[0]
    assert 'require_expiry=True' not in file_loader, '.security-overrides should still allow permanent entries'


def test_applied_suppressions_are_logged_with_their_source(generated_project):
    """Whatever is applied is printed with its origin, so an env-only mute leaves a footprint."""
    project, _ = generated_project
    secure_py = (project / '_CI' / 'tasks' / 'secure.py').read_text(encoding='utf-8')
    audit_source = secure_py.split("@logged('secure.audit')", 1)[1].split('\n@task', 1)[0]
    assert 'Applying' in audit_source, 'applied suppressions are not announced'
    assert 'suppression.source' in audit_source, 'the origin of each suppression is not printed'
    assert 'expired on' in audit_source, 'expired suppressions are not reported'


def test_parent_overrides_document_the_expiry_requirement():
    """The parent's `.security-overrides` warns that its entries travel by env and need expiries.

    The matrix runner forwards them through `<PROJECT>_SECURITY_OVERRIDE`, which now rejects
    permanent entries — so an expiry-less entry here would fail every matrix cell.
    """
    header = (REPO_ROOT / '.security-overrides').read_text(encoding='utf-8')
    assert 'expiry' in header.lower()
    entries = [line.strip() for line in header.splitlines() if line.strip() and not line.startswith('#')]
    for entry in entries:
        assert '::' in entry, f'{entry!r} has no expiry but is forwarded via the environment'


def test_the_audit_routes_every_query_through_the_retry(generated_project):
    """Every pip-audit invocation in `secure.audit` is retried, and reads the lockfile.

    The runner's behaviour is asserted by `test_the_retry_reports_a_verdict_and_retries_anything_else`;
    this is the other half — that the audit uses it, passes it the verdict phrases, and gets its
    input from `uv.lock` rather than from `uv export`. The export keeps environment markers and
    pip-audit evaluates them, so an export audited on one runner silently skips every pin whose
    marker excludes that runner's interpreter — pinned, installed by the others, and in the SBOM.
    """
    project, _ = generated_project
    secure = (project / '_CI' / 'tasks' / 'secure.py').read_text(encoding='utf-8')
    task = function_named(secure, 'audit')
    assert task, 'secure.py declares no audit task'
    called = calls_in(task)
    assert 'execute_with_retries' in called, 'the audit does not retry a run that reported nothing'
    assert 'execute' not in called, 'a pip-audit invocation bypasses the retries'
    assert 'audit_requirement_files' in called, 'the audit no longer derives its input from the lock'

    # Command literals, not the docstring, which discusses pip-audit at length.
    commands = [text for text in command_strings(task) if text.startswith('uv run pip-audit')]
    assert commands, 'the audit runs no pip-audit'
    for command in commands:
        assert '--strict' in command, f'{command!r} lets an unresolvable package pass under exit 0'
        assert '--disable-pip' in command, f'{command!r} builds a resolution environment it may have no network for'

    # In the commands, not the prose: both docstrings explain why `uv export` cannot do this.
    assert not [command for command in command_strings(task) if command.startswith('uv run uv export')], (
        'the audit reads a marker-carrying export again'
    )
    reader = function_named(secure, 'audit_requirement_files')
    assert reader, 'secure.py declares no requirement-file writer'
    assert 'UV_LOCK' in ast.dump(reader), 'the writer does not read uv.lock'


def test_the_retry_reports_a_verdict_and_retries_anything_else(generated_project):
    """`execute_with_retries` raises on a reported verdict and retries a run that gave none.

    Executed rather than read. Two one-token edits used to leave the suite green while
    disabling the whole mechanism: `raise SystemExit(1)` → `return` made every failure —
    including a genuine finding — exit 0, and dropping `result.stderr` from the inspected
    output stopped it seeing anything, since the tool writes there.
    """
    project, _ = generated_project
    source = (project / '_CI' / 'tasks' / 'shared.py').read_text(encoding='utf-8')
    slept = []
    retry = exec_from(
        source,
        'execute_with_retries',
        os=os,
        time=SimpleNamespace(sleep=slept.append),
        Context=object,
        SystemExit=SystemExit,
    )['execute_with_retries']

    class Runs:
        """A context whose `run` replays prepared results and counts the calls."""

        def __init__(self, *results: SimpleNamespace) -> None:
            self.results = list(results)
            self.commands = []

        def run(self, command, **_: object):
            self.commands.append(command)
            return self.results.pop(0) if self.results else self.results[-1]

    def result(*, failed, stdout='', stderr=''):
        return SimpleNamespace(failed=failed, stdout=stdout, stderr=stderr)

    verdicts = ('known vulnerabilit',)

    # A reported finding: raised on the first attempt, never repeated.
    reported = Runs(result(failed=True, stdout='Found 4 known vulnerabilities in 1 package'))
    with pytest.raises(SystemExit):
        retry(reported, 'audit', attempts=3, verdicts=verdicts)
    assert len(reported.commands) == 1, 'a reported finding was retried'
    assert not slept, 'a reported finding cost a delay'

    # A verdict on stderr counts as a verdict: whether a tool reports there is its business,
    # and dropping either stream would make this one retry three times instead of failing.
    on_stderr = Runs(*[result(failed=True, stderr='No known vulnerabilities found')] * 3)
    with pytest.raises(SystemExit):
        retry(on_stderr, 'audit', attempts=3, verdicts=verdicts)
    assert len(on_stderr.commands) == 1, 'a verdict on stderr was treated as no verdict at all'

    # No verdict at all: retried to exhaustion, then raised.
    crashed = Runs(*[result(failed=True, stderr='ConnectionResetError(104)')] * 3)
    with pytest.raises(SystemExit):
        retry(crashed, 'audit', attempts=3, verdicts=verdicts)
    assert len(crashed.commands) == 3, f'a run with no verdict was not retried: {crashed.commands}'
    assert slept, 'the retries did not wait'

    # And a run that succeeds on the second attempt returns rather than raising.
    recovered = Runs(result(failed=True, stderr='ConnectionResetError(104)'), result(failed=False))
    retry(recovered, 'audit', attempts=3, verdicts=verdicts)
    assert len(recovered.commands) == 2, 'the retry did not stop at the first success'


def test_the_audit_input_covers_every_locked_version(generated_project, tmp_path, capsys):
    """`audit_requirement_files` writes every registry version, one file per slot.

    Executed against a fixture lock rather than read, because this function is what closed the
    marker gap: `uv export` keeps environment markers and pip-audit evaluates them, so a pin
    whose marker excluded the runner's interpreter went unaudited while the other matrix
    interpreters installed it and the SBOM listed it.

    Three properties, and a text assertion can reach none of them: every registry version
    appears exactly once across the files, no file names a package twice — pip-audit exits 1 on
    that, so a packing bug would fail every run — and a dependency with no published release is
    named on stdout rather than dropped in silence.
    """
    project, _ = generated_project
    source = (project / '_CI' / 'tasks' / 'secure.py').read_text(encoding='utf-8')
    lock = tmp_path / 'uv.lock'
    lock.write_text(
        """
version = 1

[[package]]
name = "three-ways"
version = "1.0.0"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "three-ways"
version = "2.0.0"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "three-ways"
version = "3.0.0"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "plain"
version = "0.1.0"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "from-a-url"
version = "9.9.9"
source = { url = "https://registry.example.com/from_a_url-9.9.9-py3-none-any.whl" }

[[package]]
name = "from-git"
version = "1.0.0"
source = { git = "https://github.com/acme/thing?rev=deadbeef" }

[[package]]
name = "the-project"
version = "0.0.0"
source = { editable = "." }
""",
        encoding='utf-8',
    )
    requirements = tmp_path / 'reports' / 'audit-requirements.txt'
    written = exec_from(
        source, 'audit_requirement_files', tomllib=tomllib, Path=Path, UV_LOCK=lock, AUDIT_REQUIREMENTS=requirements
    )['audit_requirement_files']()

    pins = [line for path in written for line in path.read_text(encoding='utf-8').splitlines() if line]
    assert sorted(pins) == ['plain==0.1.0', 'three-ways==1.0.0', 'three-ways==2.0.0', 'three-ways==3.0.0'], pins
    assert len(written) == 3, f'three versions of one package need three files, got {len(written)}'
    for path in written:
        names = [line.split('==')[0] for line in path.read_text(encoding='utf-8').splitlines() if line]
        assert len(names) == len(set(names)), f'{path.name} names a package twice, which pip-audit refuses'

    # A URL whose *text* contains "registry" is not a registry source, and used to be audited as
    # though a PyPI release of that name and version were the artefact in use.
    assert not [pin for pin in pins if pin.startswith(('from-a-url', 'from-git', 'the-project'))], pins
    reported = capsys.readouterr().out
    for unauditable in ('from-a-url', 'from-git'):
        assert unauditable in reported, f'{unauditable} passes unmentioned: {reported}'
    assert 'the-project' not in reported, 'the project itself is reported as an unaudited dependency'


def test_a_suppression_that_cannot_be_reviewed_is_refused(generated_project):
    """`validate_override_entry` refuses a malformed entry, and a permanent one from outside.

    Both raises survived a mutation sweep, and both are what the docstring promises: an entry
    the audit cannot parse must not become a silent permanent suppression, and `--ignore` or the
    environment variable — neither of which leaves a trace in the repository — must carry an
    expiry.
    """
    project, _ = generated_project
    secure = (project / '_CI' / 'tasks' / 'secure.py').read_text(encoding='utf-8')
    configuration = (project / '_CI' / 'tasks' / 'configuration.py').read_text(encoding='utf-8')
    constants = exec_from(configuration, 'IGNORE_PATTERN', 'MAX_SUPPRESSION_DAYS', re=re, Path=Path)
    validate = exec_from(
        secure,
        'validate_override_entry',
        re=re,
        date=date,
        timedelta=timedelta,
        IGNORE_PATTERN=constants['IGNORE_PATTERN'],
        MAX_SUPPRESSION_DAYS=constants['MAX_SUPPRESSION_DAYS'],
        SECURITY_OVERRIDES_FILE=Path('.security-overrides'),
    )['validate_override_entry']

    horizon = date.today() + timedelta(days=constants['MAX_SUPPRESSION_DAYS'] - 30)  # noqa: DTZ011
    validate(f'CVE-2024-1234::{horizon}', '--ignore', require_expiry=True)
    validate('CVE-2024-1234', '.security-overrides:1')

    # A mistyped expiry must not read as a permanent suppression with date fragments attached.
    with pytest.raises(SystemExit):
        validate('CVE-2024-1234::2026-1-1', '.security-overrides:1')
    with pytest.raises(SystemExit):
        validate('not a vulnerability id', '.security-overrides:1')
    with pytest.raises(SystemExit):
        validate('CVE-2024-1234', '--ignore', require_expiry=True)

    # Beyond the horizon is remarked on, not refused: how long an acceptance is worth carrying
    # belongs to the project.
    validate('CVE-2024-1234::2999-12-31', '--ignore', require_expiry=True)


def test_the_audits_retry_settings_still_mean_something(generated_project):
    """`AUDIT_ATTEMPTS` allows a retry, and `AUDIT_VERDICTS` matches what pip-audit prints.

    The retry runner is asserted behaviourally, but it takes both values from its caller — so it
    proves the runner honours them, not that the audit supplies sane ones. Both degrade silently:
    `AUDIT_ATTEMPTS = 1` leaves the machinery in place and retries nothing, which is the reset
    connection that failed a CI cell before any of this existed; emptying `AUDIT_VERDICTS` makes
    every failure look like "no verdict", so a genuine finding is retried instead — measured, three
    attempts over 18s printing the same four advisories six times.

    The verdict phrases are pip-audit's own wording, so they are asserted against the two
    sentences it prints rather than against themselves.
    """
    project, _ = generated_project
    configuration = (project / '_CI' / 'tasks' / 'configuration.py').read_text(encoding='utf-8')
    values = exec_from(configuration, 'AUDIT_ATTEMPTS', 'AUDIT_VERDICTS', re=re, Path=Path)

    assert values['AUDIT_ATTEMPTS'] > 1, 'the audit retries nothing, so the machinery is decoration'
    verdicts = values['AUDIT_VERDICTS']
    assert verdicts, 'with no verdict phrases every failure is retried, findings included'

    # What pip-audit 2.10 prints on each outcome. A phrase that matches neither would retry a
    # reported finding; one that matches some other line would stop retrying a crash.
    reported = ('No known vulnerabilities found', 'Found 4 known vulnerabilities in 1 package')
    for outcome in reported:
        assert any(verdict in outcome for verdict in verdicts), f'no verdict phrase matches {outcome!r}'
    crashed = 'requests.exceptions.ConnectionError: Connection aborted, ConnectionResetError(104)'
    assert not any(verdict in crashed for verdict in verdicts), 'a crash reads as a verdict, so it is not retried'
