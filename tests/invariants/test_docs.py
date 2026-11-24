"""Invariants over the shipped docs, this repository's docs and the decision records."""

import re
from pathlib import Path

import pytest
import yaml

# conftest.py wires sys.path so _CI.tasks.* is importable; pytest loads it
# before this module, which is why no path setup is needed here.
from _CI.tasks.configuration import (
    SHIPPED_RATIONALE_PAGES,
)
from _CI.tasks.maintain import render_shipped

from .support import (
    DECISION_REFERENCE,
    DECISION_REFERENCE_ROOTS,
    DECISION_REFERENCE_SUFFIXES,
    DECISION_STATUSES,
    DECISIONS_DIR,
    REPO_ROOT,
    collect_nav_pages,
    decision_records,
    registered_tasks,
)


def test_every_environment_variable_the_workflow_reads_is_documented(generated_project):
    """The reference page lists every variable the shipped tasks actually read.

    A variable nobody documents is one nobody sets until a job fails for a reason the log does
    not explain. This walks the task modules for the names they read — through the constants in
    `configuration.py` as well as literal `os.environ` lookups — and requires each to appear on
    the page. Host-specific ones only need to appear for the host that ships them.
    """
    project, _ = generated_project
    tasks = project / '_CI' / 'tasks'
    page = (project / 'docs' / 'developer' / 'reference' / 'environment-and-flags.md').read_text(encoding='utf-8')

    sources = '\n'.join(path.read_text(encoding='utf-8') for path in tasks.glob('*.py'))
    # Both forms. `os.environ['NAME']` is how the deps-image job reads its registry settings,
    # and matching only the call form meant six variables were exempt from this page.
    # Either quote style: an f-string forces the inner lookup to double quotes, and matching
    # only single ones left `os.environ["UV_PUBLISH_URL"]`-style reads invisible to this walk.
    quoted = '[\'"]'
    reads = (
        rf'os\.environ(?:\.get)?\(\s*{quoted}([A-Z][A-Z0-9_]+){quoted}',
        rf'os\.environ\[\s*{quoted}([A-Z][A-Z0-9_]+){quoted}\s*\]',
        rf'os\.getenv\(\s*{quoted}([A-Z][A-Z0-9_]+){quoted}',
        rf'password_env={quoted}([A-Z][A-Z0-9_]+){quoted}',
    )
    literal = {name for pattern in reads for name in re.findall(pattern, sources)}
    # The names the tasks reach through a constant rather than inline.
    for constant in ('UV_PUBLISH_SETTINGS', 'OIDC_ENV_VARS'):
        match = re.search(rf'^{constant} = \(([^)]*)\)', sources, re.MULTILINE)
        if match:
            literal.update(re.findall(r"'([A-Z][A-Z0-9_]+)'", match.group(1)))
    override = re.search(r"SECURITY_OVERRIDE_ENV = '([A-Z_]+)'", sources)
    if override:
        literal.add(override.group(1))

    # Set by the runner, not read by us, and covered in prose rather than the table.
    ignored = {'PATH', 'HOME', 'COMSPEC', 'PAGER'}
    # As a code span, not a substring: `GITHUB_TOKEN` must not be satisfied by a page that
    # happens to mention `GITHUB_TOKEN_SOMETHING_ELSE`.
    documented = set(re.findall(r'`([A-Z][A-Z0-9_]+)`', page))
    undocumented = sorted(literal - ignored - documented)
    assert not undocumented, f'variables the workflow reads but nobody documented: {undocumented}'


def test_docs_nav_resolves(generated_project):
    """Every page listed in the generated properdocs.yml nav exists on disk, for every knob combo."""
    project, _ = generated_project
    config = yaml.safe_load((project / 'properdocs.yml').read_text(encoding='utf-8'))
    missing = [page for page in collect_nav_pages(config['nav']) if not (project / 'docs' / page).is_file()]
    assert not missing, f'nav entries without a file: {missing}'


def test_docs_have_no_orphans(generated_project):
    """Every markdown file shipped under docs/ is reachable from the nav (no silent orphans)."""
    project, _ = generated_project
    config = yaml.safe_load((project / 'properdocs.yml').read_text(encoding='utf-8'))
    nav_pages = set(collect_nav_pages(config['nav']))
    shipped = {str(path.relative_to(project / 'docs')) for path in (project / 'docs').rglob('*.md')}
    orphans = shipped - nav_pages
    assert not orphans, f'docs pages missing from nav: {orphans}'


def test_add_a_workflow_task_directs_people_to_local(generated_project):
    """The how-to points at `local.py` and no longer tells people to edit `__init__.py`.

    The doc previously instructed readers to create a module *and* register it in
    `_CI/tasks/__init__.py`, which guaranteed a conflict on the next update.
    """
    project, _ = generated_project
    how_to = (project / 'docs' / 'developer' / 'how-to' / 'add-a-workflow-task.md').read_text(encoding='utf-8')
    assert 'local.py' in how_to, 'the how-to never mentions the project-owned module'
    assert 'Register it in `_CI/tasks/__init__.py`' not in how_to, 'the how-to still tells people to edit __init__.py'


def test_documented_launcher_matches_the_real_one(generated_project):
    """The docs describe the launcher that actually ships, and no launcher that does not.

    The architecture doc once described `uv run python -m _CI.invoke -- <args>` — a module that
    has never existed — alongside an `@echo off` first line the file does not have, and the
    configuration-files reference kept that claim, plus a `workflow.cmd.bat`, after the
    architecture doc was fixed. So the checks for what does not exist cover every shipped page.
    """
    project, _ = generated_project
    launcher = (project / 'workflow.cmd').read_text(encoding='utf-8')
    doc = (project / 'docs' / 'developer' / 'explanation' / 'the-ci-tasks-architecture.md').read_text(encoding='utf-8')
    for page in sorted((project / 'docs').rglob('*.md')):
        text = page.read_text(encoding='utf-8')
        assert '_CI.invoke' not in text, f'{page.relative_to(project)} cites a nonexistent _CI.invoke module'
        assert 'workflow.cmd.bat' not in text, f'{page.relative_to(project)} documents a nonexistent workflow.cmd.bat'
    # Every non-shebang line of the real launcher must appear verbatim in the doc.
    for line in (line.strip() for line in launcher.splitlines()):
        if not line or line.startswith('#!'):
            continue
        assert line in doc, f'launcher line not documented: {line!r}'
    # And the dispatch mechanism the two interpreters rely on is explained, not just shown.
    assert 'exec' in doc, 'the doc omits the sh side of the dispatch'
    assert 'label' in doc, 'the doc omits the cmd label trick that makes the dispatch work'


def test_the_egress_page_places_every_registered_task(generated_project):
    """The network-egress reference names every registered task, so no command's traffic is unlisted.

    A firewall rule or a fence allowance is set from this page; a task it does not mention is a
    run that fails somewhere the page said nothing reaches. Shortcut names count as their
    default task, as the catalog's own test reads them.
    """
    project, _ = generated_project
    registered = registered_tasks(project)
    real = {f'{namespace}.{name}' for namespace, (names, _) in registered.items() for name in names}
    page = (project / 'docs' / 'developer' / 'reference' / 'network-egress.md').read_text(encoding='utf-8')
    mentioned = set(re.findall(r'`([a-z][a-z0-9_.-]*)`', page))
    placed = {name for name in mentioned if is_registered(name, real, registered)}
    covered = {name for name in real if name in placed or name.rsplit('.', 1)[0] in placed}
    missing = sorted(real - covered)
    assert not missing, f'the egress page says nothing about {missing}'


def test_task_catalog_matches_the_registered_tasks(generated_project):
    """The task catalog names every registered task, and no task that is not registered.

    The catalog drifted silently: it documented a `develop.bootstrap` that never existed,
    listed five shortcut defaults under names they do not have, and had no row for three real
    tasks. Nothing compared the page with the code, so each rename left a stale row behind.
    """
    project, _ = generated_project
    registered = registered_tasks(project)
    real = {f'{namespace}.{name}' for namespace, (names, _) in registered.items() for name in names}
    page = (project / 'docs' / 'developer' / 'reference' / 'invoke-tasks.md').read_text(encoding='utf-8')
    documented = set(re.findall(r'^\| `([a-z][a-z0-9_.-]*)`', page, re.MULTILINE))

    unknown = sorted(name for name in documented if not is_registered(name, real, registered))
    assert not unknown, f'the catalog documents tasks that are not registered: {unknown}'

    undocumented = sorted(real - documented - documented_defaults(registered, documented))
    assert not undocumented, f'registered tasks with no row in the catalog: {undocumented}'

    for namespace, default_of in shortcut_rows(page):
        _, default = registered[namespace]
        assert default_of == f'{namespace}.{default}', (
            f'the shortcut `{namespace}` runs {namespace}.{default}, the catalog says {default_of}'
        )


def is_registered(name, real, registered):
    """Whether a catalog row names a registered task (`namespace.task`) or a registered namespace."""
    return name in real if '.' in name else name in registered


def documented_defaults(registered, documented):
    """The default task of every namespace the catalog has a row for.

    A namespace's default is reachable by the bare namespace name, so a row for that counts.
    """
    return {f'{namespace}.{default}' for namespace, (_, default) in registered.items() if namespace in documented}


def shortcut_rows(page):
    """``(namespace, task it runs)`` for every row of the catalog's top-level shortcuts table."""
    shortcuts = page.split('## Top-level shortcuts', 1)[1].split('\n## ', 1)[0]
    return re.findall(r'^\| `([a-z_-]+)` \| `([a-z_.-]+)` \|', shortcuts, re.MULTILINE)


def test_sidebar_nav_override_ships(generated_project):
    """The sidebar site-nav theme override ships and is wired into properdocs.yml."""
    project, _ = generated_project
    override = project / 'docs-theme' / 'toc.html'
    assert override.is_file()
    assert 'site_nav_item' in override.read_text(encoding='utf-8')
    config = yaml.safe_load((project / 'properdocs.yml').read_text(encoding='utf-8'))
    assert config['theme']['custom_dir'] == 'docs-theme'


def test_no_hidden_dirs_in_docs(generated_project):
    """No dotfile/dotdir junk ships under docs/ (guards against tool-state directories leaking in)."""
    project, _ = generated_project
    hidden = [
        str(path.relative_to(project / 'docs'))
        for path in (project / 'docs').rglob('*')
        if any(part.startswith('.') for part in path.relative_to(project / 'docs').parts)
    ]
    assert not hidden, f'hidden paths shipped under docs/: {hidden}'


@pytest.mark.parametrize('canonical_path', sorted(SHIPPED_RATIONALE_PAGES), ids=lambda p: Path(p).stem)
def test_shipped_rationale_pages_are_rendered_from_canonical(canonical_path):
    """Each shipped explanation page is byte-for-byte what `maintain.sync-docs` renders (ADR-0046).

    The predecessor of this test compared headings, which let prose drift between the canonical
    page and its shipped copy for three commits. Rendering the copy from the canonical page's
    directives makes any difference a failure, and the fix is one command.
    """
    canonical = (REPO_ROOT / canonical_path).read_text(encoding='utf-8')
    shipped_path = SHIPPED_RATIONALE_PAGES[canonical_path]
    shipped = (REPO_ROOT / shipped_path).read_text(encoding='utf-8')
    rendered = render_shipped(canonical, canonical_path)
    assert shipped == rendered, (
        f'{shipped_path} differs from its render; run `./workflow.cmd maintain.sync-docs --write`'
    )
    assert shipped.startswith('<!-- canonical:'), f'{shipped_path} lacks the canonical marker'
    for directive in ('<!-- template-only -->', '<!-- shipped-only', '<!-- shipped:', '<!-- shipped-line:'):
        assert directive not in shipped, f'{shipped_path} still carries a {directive!r} directive'
    assert '](../decisions/' not in shipped, 'a shipped page links to a decision record that does not ship'
    assert '../../maintaining/' not in shipped, 'a shipped page links into the template repository'


def test_render_shipped_applies_every_directive():
    """The four directives do what the sync how-to says, on a page small enough to read."""
    canonical = """# Title

The template does X for a generated project.
<!-- shipped: This project does X. -->

<!-- template-only -->
Only maintainers care.
<!-- /template-only -->
<!-- shipped-only
Only developers care, `<your_package>` included.
-->
- keep
- [Parent](../how-to/parent.md)
<!-- shipped-line: - [Child](../how-to/child.md) -->

Record: [ADR-0001](../decisions/0001-x.md#why),
[Design](../../maintaining/explanation/design.md).
"""
    rendered = render_shipped(canonical, 'docs/using/explanation/page.md')
    assert rendered.splitlines()[0].startswith('<!-- canonical: rendered from docs/using/explanation/page.md')
    assert rendered.endswith(
        """# Title

This project does X.

Only developers care, `{{ project_slug }}` included.
- keep
- [Child](../how-to/child.md)

Record: [ADR-0001](https://schubergphilis.github.io/paleofuturistic_python/maintaining/decisions/0001-x.html#why),
[Design](design.md).
"""
    )
    with pytest.raises(ValueError, match='unterminated'):
        render_shipped('# T\n<!-- template-only -->\nx\n', 'p.md')


def test_decision_records_are_numbered_without_gaps():
    """Records are numbered from 0001 with no gap and no duplicate, so a reference is unambiguous."""
    numbers = [int(record.name[:4]) for record in decision_records()]
    assert numbers == list(range(1, len(numbers) + 1)), f'record numbers are {numbers}'


@pytest.mark.parametrize('record', decision_records(), ids=lambda record: record.stem)
def test_decision_record_has_the_agreed_shape(record):
    """A record carries a title naming its number, a status, a date, and the three sections.

    The shape is what makes the log readable as a log: a reader opening any record finds the
    same questions answered in the same order, and a superseded one says what replaced it.
    """
    text = record.read_text(encoding='utf-8')
    number = record.name[:4]
    assert text.startswith(f'# ADR-{number}: '), f'{record.name} does not open with its own number'
    status = re.search(r'^- \*\*Status\*\*: (\w+)(.*)$', text, re.MULTILINE)
    assert status, f'{record.name} has no Status line'
    assert status.group(1) in DECISION_STATUSES, f'{record.name} has status {status.group(1)!r}'
    if status.group(1) == 'superseded':
        assert DECISION_REFERENCE.search(status.group(2)), f'{record.name} is superseded but names no successor'
    assert re.search(r'^- \*\*Date\*\*: \d{4}-\d{2}-\d{2}', text, re.MULTILINE), f'{record.name} has no dated Date line'
    for heading in ('## Context', '## Decision', '## Consequences'):
        assert f'\n{heading}\n' in text, f'{record.name} lacks the {heading!r} section'


def test_decision_records_are_listed_in_the_nav_and_the_index():
    """Every record is reachable from the nav and from the index page, and nothing else is listed.

    A record outside the nav fails `properdocs build --strict` only once something links to
    it; one missing from the index is simply invisible. Both lists are kept by hand, so both
    are checked against the directory.
    """
    expected = {record.name for record in decision_records()}
    nav = set(
        re.findall(
            r'maintaining/decisions/(\d{4}-[a-z0-9-]+\.md)', (REPO_ROOT / 'properdocs.yml').read_text(encoding='utf-8')
        )
    )
    assert nav == expected, f'nav lists {sorted(nav ^ expected)} differently from the directory'
    index = set(re.findall(r'\]\((\d{4}-[a-z0-9-]+\.md)\)', (DECISIONS_DIR / 'index.md').read_text(encoding='utf-8')))
    assert index == expected, f'index.md lists {sorted(index ^ expected)} differently from the directory'


def test_every_decision_reference_resolves():
    """An `ADR-NNNN` named anywhere in the repository is a record that exists.

    The point of naming a record from a docstring or a page is that the reader can open it.
    A reference to a number nobody wrote, or one renumbered away, is worse than no reference.
    """
    known = {record.name[:4] for record in decision_records()}
    dangling = [
        f'{path.relative_to(REPO_ROOT)}: ADR-{number}'
        for path in referencing_files()
        for number in DECISION_REFERENCE.findall(path.read_text(encoding='utf-8'))
        if number not in known
    ]
    assert not dangling, f'references to records that do not exist: {dangling}'


PYPA_SPECIFICATION = re.compile(r'packaging\.python\.org/en/latest/specifications/([a-z0-9-]+)')


def test_both_packaging_specification_pages_cover_the_same_specifications():
    """The parent's and the shipped packaging-specifications pages name the same PyPA specs.

    The two are written by hand for two readers, someone deciding whether the template fits
    and someone developing a generated project, so neither renders from the other. What must
    not drift is coverage: a specification one page gained and the other did not.
    """
    parent = (REPO_ROOT / 'docs' / 'using' / 'reference' / 'packaging-specifications.md').read_text(encoding='utf-8')
    shipped = (
        REPO_ROOT / 'template' / 'docs' / 'developer' / 'reference' / 'packaging-specifications.md.jinja'
    ).read_text(encoding='utf-8')
    covered_by_parent = set(PYPA_SPECIFICATION.findall(parent))
    covered_by_shipped = set(PYPA_SPECIFICATION.findall(shipped))
    assert covered_by_parent, 'the parent page links no PyPA specification'
    assert covered_by_parent == covered_by_shipped, (
        f'only the parent covers {sorted(covered_by_parent - covered_by_shipped)}; '
        f'only the shipped page covers {sorted(covered_by_shipped - covered_by_parent)}'
    )


def test_no_heading_starts_with_a_digit():
    """Every heading on both sites starts with a word, so its id is a selector the theme can use.

    `## 1. Clone` slugs to the id `1-clone`, and the sidebar's ScrollSpy hands `#1-clone` to
    `querySelector` unescaped. A CSS identifier may not start with a digit, so that throws on
    page load, and the theme's `base.js` reads `keyCodes` after that call and never binds the
    header navigation: second-level dropdowns stop opening. Both defects are upstream in
    properdocs-theme-mkdocs 1.6.7, the unescaped selector and the nav bound after the access
    that throws. Numbered steps are written `## Step 1 — …` until they are fixed; this was
    done once by hand and regressed within a month.
    """
    offenders = [
        f'{path.relative_to(REPO_ROOT)}:{number}'
        for path in site_pages()
        for number, line in heading_lines(path.read_text(encoding='utf-8'))
        if re.match(r'#+\s+\d', line)
    ]
    assert not offenders, f'headings whose id would start with a digit: {offenders}'


def site_pages():
    """Every Markdown page of the parent site and of the shipped docs, decision records included."""
    for root in ('docs', 'template/docs'):
        yield from sorted(path for path in (REPO_ROOT / root).rglob('*.md*') if path.is_file())


def heading_lines(text):
    """Yield ``(line number, line)`` for every heading line, fenced code blocks skipped."""
    fenced = False
    for number, line in enumerate(text.splitlines(), start=1):
        if line.startswith('```'):
            fenced = not fenced
        elif not fenced and line.startswith('#'):
            yield number, line


def referencing_files():
    """Every file under the reference roots that may name a record, the vendored trees left out."""
    for root in DECISION_REFERENCE_ROOTS:
        for path in (REPO_ROOT / root).rglob('*'):
            if path.is_file() and path.suffix in DECISION_REFERENCE_SUFFIXES and 'lib/vendor' not in str(path):
                yield path
