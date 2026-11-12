"""Helpers and constants shared by the invariant modules; the fixtures are in ``tests/conftest.py``."""

import ast
import importlib.util
import os
import re
import subprocess
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

# conftest.py wires sys.path so _CI.tasks.* is importable; pytest loads it
# before this module, which is why no path setup is needed here.

REPO_ROOT = Path(__file__).resolve().parents[2]


# The one shape both GitHub jobs and the GitLab job hand the push to a release task in: the
# previous and new tips, and where to write the answer. `$GITHUB_OUTPUT` is where a step's
# outputs go; GitLab reads nothing back, so its job passes no `--output`.
RELEASE_DETECTION = (
    './workflow.cmd {task} --before "${{{{ github.event.before }}}}" --after "${{{{ github.sha }}}}"'
    ' --output "$GITHUB_OUTPUT"'
)


# Rules switched off for `_CI/tasks/sbom.py` because py-serializable annotates an
# intersection as a union. They are the rules most likely to catch a real bug, so the
# scoping is the whole point — see the comment beside the override in the template.
UNION_WORKAROUND_RULES = {
    'unknown-argument',
    # Called `unresolved-attribute` before ty 0.0.100, which renamed it and split out
    # `missing-union-attribute` for an attribute missing from some members of a union.
    'missing-attribute',
    'missing-union-attribute',
    'too-many-positional-arguments',
    'invalid-argument-type',
}


def python_floor(pyproject):
    """Return the `requires-python` lower bound of a pyproject as a (major, minor) tuple."""
    spec = tomllib.loads(pyproject.read_text(encoding='utf-8'))['project']['requires-python']
    match = re.search(r'>=\s*(\d+)\.(\d+)', spec)
    assert match, f'{pyproject} has no >= lower bound: {spec!r}'
    return int(match.group(1)), int(match.group(2))


def collect_nav_pages(nav_entry):
    """Recursively collect the `.md` leaf paths from a properdocs/mkdocs nav structure."""
    pages = []
    if isinstance(nav_entry, str):
        pages.append(nav_entry)
    elif isinstance(nav_entry, list):
        for item in nav_entry:
            pages.extend(collect_nav_pages(item))
    elif isinstance(nav_entry, dict):
        for value in nav_entry.values():
            pages.extend(collect_nav_pages(value))
    return pages


CREDENTIALED_URLS = [
    # (origin URL as CI leaves it, expected published form)
    ('https://x-access-token:ghs_SECRETTOKEN@github.com/owner/repo.git', 'https://github.com/owner/repo.git'),
    ('https://gitlab-ci-token:glcbt-SECRETTOKEN@gitlab.com/group/proj.git', 'https://gitlab.com/group/proj.git'),
    ('https://user:pw@git.example.com:8443/o/r.git', 'https://git.example.com:8443/o/r.git'),
    ('ssh://git@github.com/owner/repo.git', 'ssh://github.com/owner/repo.git'),
    # No userinfo — must pass through byte-for-byte.
    ('https://github.com/owner/repo.git', 'https://github.com/owner/repo.git'),
    ('https://github.com/owner/repo', 'https://github.com/owner/repo'),
    # An `@` outside the netloc is not a credential.
    ('https://github.com/owner/repo@v1.2.3', 'https://github.com/owner/repo@v1.2.3'),
]


def load_generated_configuration(project):
    """Import the generated project's `_CI/tasks/configuration.py` as a standalone module.

    Pure stdlib (`re`, `pathlib`), so it loads without the rest of the `_CI.tasks` package.
    """
    path = project / '_CI' / 'tasks' / 'configuration.py'
    spec = importlib.util.spec_from_file_location('generated_configuration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_generated_shared(project):
    """Import the generated project's `_CI/tasks/shared.py` as a standalone module.

    It imports only `invoke`, which ``conftest.py`` already puts on ``sys.path`` via the
    vendored tree, so the module loads without the rest of the `_CI.tasks` package.
    """
    path = project / '_CI' / 'tasks' / 'shared.py'
    spec = importlib.util.spec_from_file_location('generated_shared', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def strip_prose(source):
    """Return `source` as code only — no comments, no docstrings.

    Both routinely mention the very literals a "don't hardcode this" assertion looks for, so
    matching raw text would fail on an explanation of the fix. `ast.unparse` drops comments;
    the docstrings have to be removed by hand.
    """
    tree = ast.parse(source)
    scopes = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, scopes) or len(node.body) < 2:
            continue
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            node.body.pop(0)
    return ast.unparse(tree)


REMOTE_URLS = [
    ('https://gitlab.com/group/project.git', 'gitlab.com', 'group/project'),
    ('git@gitlab.com:group/project.git', 'gitlab.com', 'group/project'),
    # The case the hardcoded gitlab.com match silently dropped.
    ('https://gitlab.example.com/group/project.git', 'gitlab.example.com', 'group/project'),
    ('git@gitlab.example.com:group/project.git', 'gitlab.example.com', 'group/project'),
    # Nested groups: every path segment has to survive.
    ('https://gitlab.example.com/group/sub/deeper/project.git', 'gitlab.example.com', 'group/sub/deeper/project'),
    # No .git suffix, and a trailing slash.
    ('https://gitlab.example.com/group/project/', 'gitlab.example.com', 'group/project'),
    # An https port belongs in the web URL...
    ('https://gitlab.example.com:8443/group/project.git', 'gitlab.example.com:8443', 'group/project'),
    # ...but an ssh port does not.
    ('ssh://git@gitlab.example.com:2222/group/project.git', 'gitlab.example.com', 'group/project'),
]


def stub_result(*, ok=True, stdout='', stderr=''):
    """A stand-in for invoke's `Result`, carrying only what the code under test reads."""
    return SimpleNamespace(ok=ok, failed=not ok, stdout=stdout, stderr=stderr)


class StubContext:
    """Minimal invoke-`Context` stand-in returning canned results and recording every command.

    `responses` is an ordered list of `(fragment, result)` pairs and the first fragment
    contained in the command wins, so more specific commands must come first —
    `git commit --no-gpg-sign` contains `git commit`.
    """

    def __init__(self, responses) -> None:
        """Store the ordered `(fragment, result)` pairs this context will answer with."""
        self.responses = responses
        self.commands = []

    def run(self, cmd, **_kwargs: object):
        """Record `cmd` and return the canned result for the first matching fragment."""
        self.commands.append(cmd)
        for fragment, result in self.responses:
            if fragment in cmd:
                return result
        message = f'unexpected command: {cmd!r}'
        raise AssertionError(message)


# Real `git commit` stderr, captured from git 2.x. The ssh case is used deliberately: it
# contains none of the plausible-looking "signing failed"/"failed to sign" phrasings, so a
# marker matched against those instead of git's summary line fails this test.
SIGNING_FAILED = (
    "error: Couldn't load public key /nonexistent/key.pub: No such file or directory?\n"
    'fatal: failed to write commit object\n'
)


HOOK_FAILED = 'hook says no\n'


FORK_HEAD = 'github.event.pull_request.head.repo.full_name != github.repository'


def fork_pair(workflow, container_job, fork_job):
    """Return (container job, fork job) from a workflow, asserting the fork job's shape (ADR-0041).

    The fork job has no container, since the token of a pull request from a fork cannot push
    the deps image; it runs only for a head that is another repository; and it carries the
    container job's name, so one required check is satisfied by whichever of the two ran.
    """
    jobs = workflow['jobs']
    container, fork = jobs[container_job], jobs[fork_job]
    assert 'container' not in fork, f'{fork_job} runs in the deps image, which a fork cannot build'
    assert FORK_HEAD in fork['if'], f'{fork_job} does not key on the head being a fork: {fork["if"]!r}'
    assert "github.event_name == 'pull_request'" in fork['if'], f'{fork_job} could run on a push'
    assert fork['name'] == container['name'], f'{fork_job} is not the check {container_job} is'
    assert fork['permissions'] == {'contents': 'read'}, f'{fork_job} asks for more than it can get'
    assert any(str(step.get('uses', '')).startswith('astral-sh/setup-uv@') for step in fork['steps']), (
        f'{fork_job} has no uv to run the launcher with'
    )
    return container, fork


def run_commands(job):
    """The `run:` lines of a job, in order."""
    return [step['run'] for step in job['steps'] if 'run' in step]


def workflow_run_scripts(workflow):
    """Yield every `run:` script in a parsed GitHub workflow, with a `job/step` label."""
    for job_name, job in (workflow.get('jobs') or {}).items():
        for index, step in enumerate(job.get('steps') or []):
            script = step.get('run')
            if script:
                yield f'{job_name}/step{index}', script


def suppression_calls(secure_py, function_name='audit'):
    """Return `{source label: {keyword: value}}` for each `parse_suppressions()` call in `audit`.

    Parsed with `ast`, not matched textually. Line-based matching broke the moment a call was
    wrapped across lines, and a regex stops at the wrong parenthesis because one call nests
    `os.environ.get(...)` inside it. The AST is indifferent to both.
    """
    tree = ast.parse(secure_py)
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function_name)
    calls = {}
    for node in ast.walk(func):
        if not (isinstance(node, ast.Call) and getattr(node.func, 'id', '') == 'parse_suppressions'):
            continue
        label = ast.unparse(node.args[1]) if len(node.args) > 1 else ''
        calls[label] = {kw.arg: ast.unparse(kw.value) for kw in node.keywords}
    return calls


def github_workflows(project):
    """Yield (name, parsed) for every shipped GitHub workflow."""
    directory = project / '.github' / 'workflows'
    for path in sorted(directory.iterdir()):
        yield path.name, yaml.safe_load(path.read_text(encoding='utf-8'))


def step_index(steps, needle):
    """Return the index of the first step whose `run` or `uses` contains `needle`."""
    for index, step in enumerate(steps):
        if needle in (step.get('run') or '') or needle in (step.get('uses') or ''):
            return index
    return -1


# The labels the well-known-project-urls spec lists, after its own normalisation
# (lowercase, punctuation and whitespace removed). PyPI shows these with dedicated icons.
WELL_KNOWN_URL_LABELS = {
    'homepage',
    'source',
    'download',
    'changelog',
    'releasenotes',
    'documentation',
    'issues',
    'funding',
}


def normalize_url_label(label):
    """Normalise a Project-URL label per the well-known-project-urls spec."""
    return re.sub(r'[^a-z0-9]', '', label.lower())


# Where a generated project may still say `main` and mean something other than the branch.
MAIN_NOT_THE_BRANCH = (
    '__main__',
    'cli:main',
    'invoke.main',
    'main()',
    'test for `main`',
    'the main pieces',
    'the main ',
)


MAIN_WORD = re.compile(r'\bmain\b')


def lines_naming_main(project):
    """Every `path:line` in a generated project that says `main` as a branch would be said."""
    found = []
    for path in sorted(project.rglob('*')):
        if not path.is_file() or '.git' in path.parts or '_CI/lib' in path.as_posix() or path.name == '.gitignore':
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        found.extend(
            f'{path.relative_to(project)}:{number}'
            for number, line in enumerate(text.splitlines(), start=1)
            if MAIN_WORD.search(line) and not any(allowed in line for allowed in MAIN_NOT_THE_BRANCH)
        )
    return found


TEMPLATE_WORKFLOWS = REPO_ROOT / 'template' / "{% if git_hosting_service == 'github' %}.github{% endif %}" / 'workflows'


# `uses: owner/repo@ref  # vX.Y.Z`. Local refs (`uses: ./.github/...`) carry no `@` and are
# skipped by the pattern, which is correct: they are versioned by the commit being built.
ACTION_USE = re.compile(r'^\s*-?\s*uses:\s*(?P<action>[^@\s]+)@(?P<ref>\S+)(?:\s+#\s*(?P<comment>.+?))?\s*$')


def action_pins(directory):
    """Return {action: {ref: [where, ...]}} for every third-party `uses:` under `directory`."""
    pins = {}
    for path in sorted(directory.glob('*')):
        if not path.is_file():
            continue
        for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
            match = ACTION_USE.match(line)
            if match:
                where = f'{path.name}:{lineno}'
                pins.setdefault(match.group('action'), {}).setdefault(match.group('ref'), []).append(where)
    return pins


class RecordingContext:
    """Minimal stand-in for an Invoke context that records commands instead of running them."""

    def __init__(self, stdout_for=None) -> None:
        """Optionally map command prefixes to the stdout each should return."""
        self.commands = []
        self.stdout_for = stdout_for or {}

    def run(self, cmd, **_kwargs: object):
        """Record `cmd` and return canned stdout when a prefix matches."""
        self.commands.append(cmd)
        for prefix, stdout in self.stdout_for.items():
            if cmd.startswith(prefix):
                return SimpleNamespace(stdout=stdout, failed=False)
        return SimpleNamespace(stdout='', failed=False)


def opener(project, system, *, has_wslview=False, interop=False):
    """Load the generated `shared.py` and drive `open_target` for one platform.

    Returns (commands issued via context.run, commands routed through `execute`). The
    split matters: `execute` fails the task on a non-zero exit, so which list a command
    lands in *is* the failure-semantics contract.
    """
    shared = load_generated_shared(project)
    executed = []
    shared.get_operating_system = lambda: system
    shared.shutil = SimpleNamespace(which=lambda n: '/wslview' if (n == 'wslview' and has_wslview) else None)
    shared.wsl_interop_available = lambda: interop
    shared.execute = lambda _ctx, cmd: executed.append(cmd)
    context = RecordingContext({'wslpath': r'\\wsl.localhost\Ubuntu\home\me\site\index.html'})
    shared.open_target(context, 'site/index.html')
    return context.commands, executed


OUTDATED_TREE = """\
paleofuturistic-python-project v0.0.0
├── check-wheel-contents v0.6.3 (group: build)
├── ty v0.0.100 (group: dev) (latest: v0.0.101)
├── uv v0.13.7 (group: dev) (latest: v0.13.9)
├── validate-pyproject[all] v0.27 (group: dev) (latest: v0.28)
├── Pytest_Env v1.8.5 (group: test) (latest: v1.9.0)
└── ruff v0.17.4 (group: lint)
"""


PINNED_PYPROJECT = """\
[build-system]
requires = ["uv_build>=0.8.15,<=0.13.7"]

[dependency-groups]
lint = [
    # Newest version clearing the [tool.uv] exclude-newer boundary.
    "ty==0.0.100",
    "validate-pyproject[all]==0.27",
    "ruff==0.17.4",
]
test = [
    "pytest-env==1.8.5",
    "uv==0.13.7",  # moves with develop.bump-uv
]
"""


def uv_pins(project):
    """Return every uv version a generated project pins, keyed by where it came from.

    Five places have to agree. They are collected together because the failure that matters is
    *disagreement* — most of all a base-image tag that has moved while its digest has not,
    since a reference carrying both resolves to the digest and silently keeps the old image.
    """
    data = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    base = data['tool']['docker-versions']['base-image']
    lock_data = tomllib.loads((project / 'uv.lock').read_text(encoding='utf-8'))
    locked = {p['name']: p['version'] for p in lock_data['package']}
    return {
        'required-version': data['tool']['uv']['required-version'].removeprefix('=='),
        'test group': next(d for d in data['dependency-groups']['test'] if d.startswith('uv==')).removeprefix('uv=='),
        'uv_build bound': data['build-system']['requires'][0].split('<=')[1],
        'base-image tag': base.split('@')[0].split(':')[-1].split('-python')[0],
        'uv.lock': locked['uv'],
    }


def pre_commit_hooks(project):
    """Yield every hook defined in the generated `.pre-commit-config.yaml`."""
    config = yaml.safe_load((project / '.pre-commit-config.yaml').read_text(encoding='utf-8'))
    for repo in config['repos']:
        yield from repo['hooks']


def hook_stages(hook):
    """Return a hook's stages, defaulting to pre-commit as pre-commit itself does."""
    return hook.get('stages') or ['pre-commit']


def invoked_task(hook):
    """Return the workflow task a hook runs, seeing through any `sh -c …` wrapper."""
    match = re.search(r'\./workflow\.cmd\s+([\w.-]+)', hook['entry'])
    return match.group(1) if match else ''


def registry_steps(project):
    """Return ``{step name: scope}`` parsed out of the generated `_CI/tasks/preflight.py`.

    Read as source rather than imported: importing it would pull in invoke and every task
    module behind it, which this suite has no reason to install just to read a declaration.
    """
    source = (project / '_CI' / 'tasks' / 'preflight.py').read_text(encoding='utf-8')
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Assign):
            continue
        if not any(getattr(target, 'id', None) == 'STEPS' for target in node.targets):
            continue
        # Keywords as well as positions, and a failed read fails the assertion rather than
        # raising out of the helper: `Step('ty', scope=WHOLE_PROGRAM)` is the same declaration.
        steps = {}
        for call in node.value.elts:
            supplied = dict(zip(('name', 'scope'), call.args, strict=False))
            supplied.update({word.arg: word.value for word in call.keywords})
            name, scope = supplied.get('name'), supplied.get('scope')
            assert isinstance(name, ast.Constant), f'a step in STEPS declares no literal name: {ast.dump(call)}'
            assert isinstance(scope, ast.Name), f'step {name.value!r} declares no plain scope name'
            steps[name.value] = scope.id
        return steps
    pytest.fail('preflight.py declares no STEPS registry')


def per_file_step_filters(project):
    """Return ``{step name: compiled files pattern}`` for every per-file step in the registry.

    The pattern constants are read from the generated `configuration.py`, which is the one
    place they are declared, so this follows a filter that is renamed or tightened.
    """
    source = (project / '_CI' / 'tasks' / 'preflight.py').read_text(encoding='utf-8')
    constants = load_generated_configuration(project)
    filters = {}
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Assign) and any(getattr(t, 'id', None) == 'STEPS' for t in node.targets)):
            continue
        for call in node.value.elts:
            supplied = dict(zip(('name', 'scope'), call.args, strict=False))
            supplied.update({word.arg: word.value for word in call.keywords})
            if getattr(supplied.get('scope'), 'id', None) != 'PER_FILE':
                continue
            files = supplied.get('files')
            assert isinstance(files, ast.Name), f'per-file step {supplied["name"].value!r} has no files= constant'
            filters[supplied['name'].value] = getattr(constants, files.id)
    return filters


# Paths a commit can plausibly stage, chosen so that every per-file filter accepts at least one
# and some accept none. The hook is judged on what it does with each.
STAGEABLE_PATHS = (
    'src/pkg/module.py',
    '_CI/tasks/local.py',
    'tests/test_module.py',
    'pyproject.toml',
    'README.md',
    'docs/index.md',
    'src/pkg/py.typed',
    'uv.lock',
    '_CI/tasks/README.md',
    'nested/pyproject.toml',
)


def git(repository, *arguments: str, check: bool = True):
    """Run git in `repository` with a fixed identity, so nothing depends on the host config."""
    identity = ('-c', 'user.name=t', '-c', 'user.email=t@example.invalid', '-c', 'commit.gpgsign=false')
    return subprocess.run(
        ['git', *identity, *arguments],
        cwd=str(repository),
        capture_output=True,
        text=True,
        check=check,
    )


def range_resolver(project):
    """Return the generated `unpushed_range`, bound to a context that runs git for real.

    Read out of the generated source rather than imported: importing `_CI.tasks.lint` pulls in
    invoke and every sibling task module behind it. These three functions depend on nothing but
    `os` and the context's `run`, so the smallest honest harness execs them alone.
    """
    source = (project / '_CI' / 'tasks' / 'lint.py').read_text(encoding='utf-8')
    namespace = exec_from(source, 'resolves', 'unpushed_range', os=os, Context=object)

    class GitContext:
        """The slice of invoke's Context these functions touch: `run` returning stdout and failure."""

        def __init__(self, repository) -> None:
            self.repository = repository

        def run(self, command, *, hide=False, warn=False):  # noqa: ARG002
            done = subprocess.run(  # noqa: S602 — the commands are this test's own git literals
                command, shell=True, cwd=str(self.repository), capture_output=True, text=True, check=False
            )
            return SimpleNamespace(failed=done.returncode != 0, stdout=done.stdout)

    return lambda repository: namespace['unpushed_range'](GitContext(repository))


def commits_in(repository, revision_range):
    """Return the subjects `cz check` would be handed for `revision_range`."""
    if revision_range is None:
        return []
    listed = git(repository, 'log', '--format=%s', revision_range)
    return [line for line in listed.stdout.splitlines() if line]


def function_named(source, name):
    """Return the top-level `ast.FunctionDef` called `name`, or None."""
    return next(
        (node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == name),
        None,
    )


def command_strings(node):
    """Yield every string literal in `node`, with f-string pieces stitched back together.

    An f-string is a `JoinedStr` of constants and substitutions, so asking for `ast.Constant`
    alone sees `'uv run pip-audit -r '` and loses every flag after the first placeholder.
    """
    # `ast.walk` also descends *into* an f-string, so its pieces are collected and skipped
    # rather than yielded next to the whole they belong to.
    pieces = set()
    joined = []
    for inner in ast.walk(node):
        if isinstance(inner, ast.JoinedStr):
            parts = [part for part in inner.values if isinstance(part, ast.Constant)]
            pieces.update(id(part) for part in parts)
            joined.append(''.join(part.value for part in parts))
    yield from joined
    for inner in ast.walk(node):
        if isinstance(inner, ast.Constant) and isinstance(inner.value, str) and id(inner) not in pieces:
            yield inner.value


def calls_in(node):
    """Return the names of every function called anywhere inside `node`."""
    called = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Call):
            func = inner.func
            called.add(getattr(func, 'id', None) or getattr(func, 'attr', None))
    return called


def exec_from(source, *names: str, **namespace: object):
    """Exec the named top-level functions and assignments from `source`, and return the namespace.

    One dict as globals, so the extracted definitions can see each other and the stubs. Reading
    the generated source and running a slice of it is how this suite tests behaviour without
    importing `_CI.tasks.*`, which pulls invoke and every sibling module behind it.
    """
    wanted = set(names)
    body = [
        node
        for node in ast.parse(source).body
        if (isinstance(node, ast.FunctionDef) and node.name in wanted)
        or (isinstance(node, ast.Assign) and any(getattr(t, 'id', None) in wanted for t in node.targets))
    ]
    found = {node.name if isinstance(node, ast.FunctionDef) else node.targets[0].id for node in body}
    assert wanted <= found, f'missing from the source: {sorted(wanted - found)}'
    exec(compile(ast.Module(body=body, type_ignores=[]), '<generated>', 'exec'), namespace)  # noqa: S102
    return namespace


def failing(*, failed: bool = True):
    """A context whose `run` reports `failed`, recording the keyword arguments it was given."""

    class Context:
        def __init__(self) -> None:
            self.calls = []

        def run(self, command, **kwargs: object):
            self.calls.append((command, kwargs))
            return SimpleNamespace(failed=failed, stdout='', stderr='')

    return Context()


def registered_tasks(project):
    """Return ``{namespace: (task names, default task name)}`` from the generated `_CI/tasks/`.

    Read from source, like `registry_steps`: every module builds `namespace = Collection(name)`
    and registers with `namespace.add_task(cast(Task, fn), name=..., default=...)`. Invoke names
    a task after its function with underscores turned into dashes unless `name=` says otherwise.
    """
    registered = {}
    for module in sorted((project / '_CI' / 'tasks').glob('*.py')):
        tree = ast.parse(module.read_text(encoding='utf-8'))
        collection, names, default = None, set(), None
        for node in tree.body:
            value = node.value if isinstance(node, ast.Assign) else None
            if isinstance(value, ast.Call) and getattr(value.func, 'id', None) == 'Collection' and value.args:
                collection = value.args[0].value
            call = node.value if isinstance(node, ast.Expr) else None
            if not (isinstance(call, ast.Call) and getattr(call.func, 'attr', None) == 'add_task'):
                continue
            target = call.args[0]
            if isinstance(target, ast.Call):  # cast(Task, fn)
                target = target.args[1]
            words = {word.arg: word.value for word in call.keywords}
            name = words['name'].value if 'name' in words else target.id.replace('_', '-')
            names.add(name)
            if 'default' in words and words['default'].value is True:
                default = name
        if collection and names:
            registered[collection] = (names, default)
    return registered


VENDOR_TREES = ('_CI/lib', 'template/_CI/lib')


def source_files(vendor):
    """Yield the committed files of a vendored tree, skipping bytecode caches.

    Only one of the two trees is ever executed — this repository runs `_CI/lib/vendor`, while
    the template's copy is only ever copied — so `__pycache__` appears in one and not the
    other. Comparing them would make the result depend on whether anything had run yet, which
    is how this passed locally and failed in CI.
    """
    return [
        path
        for path in vendor.rglob('*')
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc'
    ]


def vendored_packages(lib_directory):
    """Return the importable top-level package directories in a vendored tree."""
    vendor = lib_directory / 'vendor'
    ignored = {'bin', '__pycache__'}
    return {path.name for path in vendor.iterdir() if path.is_dir() and path.name not in ignored}


def manifest_packages(lib_directory):
    """Return the distribution names pinned in a tree's vendor.txt, mapped to directory names."""
    text = (lib_directory / 'vendor.txt').read_text(encoding='utf-8')
    names = {line.split('==')[0].strip() for line in text.splitlines() if re.match(r'^[A-Za-z]', line)}
    return {name.replace('-', '_') for name in names}


DECISIONS_DIR = REPO_ROOT / 'docs' / 'maintaining' / 'decisions'


DECISION_STATUSES = {'accepted', 'superseded', 'deprecated'}


DECISION_REFERENCE = re.compile(r'\bADR-(\d{4})\b')


# Where a record may be named from: every text file this repository ships or reads.
DECISION_REFERENCE_ROOTS = ('docs', 'template', '_CI', 'tests')


DECISION_REFERENCE_SUFFIXES = {'.md', '.jinja', '.py', '.toml', '.yaml', '.yml', '.txt', '.cfg'}


def decision_records():
    """Return the numbered records, in order."""
    return sorted(DECISIONS_DIR.glob('[0-9][0-9][0-9][0-9]-*.md'))
