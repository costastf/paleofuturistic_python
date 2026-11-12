"""Invariants over what copier generates: the answers, the validators, the pins and the vendored tree."""

import re
import tomllib
from datetime import date

import pytest
import yaml

# conftest.py wires sys.path so _CI.tasks.* is importable; pytest loads it
# before this module, which is why no path setup is needed here.
from _CI.tasks.configuration import (
    PROJECT_SLUG,
    UV_VERSION_ENV,
    combo_context,
    template_uv_version,
)

from .support import (
    REPO_ROOT,
    VENDOR_TREES,
    WELL_KNOWN_URL_LABELS,
    lines_naming_main,
    load_generated_configuration,
    manifest_packages,
    normalize_url_label,
    python_floor,
    source_files,
    uv_pins,
    vendored_packages,
)


def test_pyproject_is_valid_toml(generated_project):
    """The generated pyproject.toml parses cleanly and carries the expected blocks."""
    project, _ = generated_project
    data = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    assert data['project']['name']
    assert 'dependency-groups' in data


def test_ci_tooling_never_claims_a_newer_python_than_the_project(generated_project):
    """`_CI/pyproject.toml` must not require a newer Python than the project itself.

    Ruff resolves that file for everything under `_CI/` and infers its Python target from
    it, but `_CI/tasks/*` runs on the *project's* interpreter. When it claimed 3.12 against a
    3.11 project, ruff offered fixes that would break the generated project at runtime,
    because they need syntax or standard library the project's interpreter does not have.
    """
    project, _ = generated_project
    assert python_floor(project / '_CI' / 'pyproject.toml') <= python_floor(project / 'pyproject.toml'), (
        '_CI tooling is linted against a newer Python than the project supports'
    )


def test_project_urls_use_well_known_labels(generated_project):
    """`[project.urls]` renders in every cell, every label is well-known, and links fit the host."""
    project, cell = generated_project
    urls = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))['project']['urls']
    unknown = sorted(label for label in urls if normalize_url_label(label) not in WELL_KNOWN_URL_LABELS)
    assert not unknown, f'labels PyPI will not recognise: {unknown}'
    repository = urls['Source']
    assert not repository.endswith(('/', '.git'))
    issues = '/-/issues' if cell['git_hosting_service'] == 'gitlab' else '/issues'
    assert urls['Issues'] == f'{repository}{issues}'
    pages = cell['git_hosting_service'] == 'github' and cell['integrate_pages']
    assert ('Documentation' in urls) == pages
    if pages:
        assert urls['Homepage'] == urls['Documentation']
        assert urls['Homepage'].endswith('.github.io/' + repository.rsplit('/', 1)[1] + '/')
    else:
        assert urls['Homepage'] == repository


def test_no_repository_url_ships_no_project_urls(generate, tmp_path_factory):
    """Without `repository_url`, `[project.urls]` is absent rather than full of dead links."""
    workdir = tmp_path_factory.mktemp('no-repository-url')
    generate(workdir / PROJECT_SLUG, {'repository_url': ''})
    pyproject = tomllib.loads((workdir / PROJECT_SLUG / 'pyproject.toml').read_text(encoding='utf-8'))
    assert 'urls' not in pyproject['project']


def test_repository_url_is_normalised(generate, tmp_path_factory):
    """A pasted clone URL (`.git`, trailing slash, surrounding space) yields clean links."""
    workdir = tmp_path_factory.mktemp('clone-url')
    generate(workdir / PROJECT_SLUG, {'repository_url': ' https://github.com/Acme/widget.git/ '})
    urls = tomllib.loads((workdir / PROJECT_SLUG / 'pyproject.toml').read_text(encoding='utf-8'))['project']['urls']
    assert urls['Source'] == 'https://github.com/Acme/widget'
    assert urls['Documentation'] == 'https://acme.github.io/widget/'


@pytest.mark.parametrize(
    'bad_url',
    [
        pytest.param('http://github.com/acme/widget', id='plain-http'),
        pytest.param('git@github.com:acme/widget.git', id='ssh'),
        pytest.param('https://github.com', id='no-path'),
        pytest.param('github.com/acme/widget', id='no-scheme'),
    ],
)
def test_repository_url_validator_rejects_invalid(generate, tmp_path_factory, bad_url):
    """The validator refuses anything but an https URL with a path, before writing a project."""
    workdir = tmp_path_factory.mktemp('bad-repository-url')
    result = generate(workdir / PROJECT_SLUG, {'repository_url': bad_url}, check=False)
    assert result.returncode != 0, f'copier accepted repository_url={bad_url!r}'
    assert not (workdir / PROJECT_SLUG / 'pyproject.toml').exists()


@pytest.mark.parametrize(
    'bad_branch',
    [
        pytest.param('', id='empty'),
        pytest.param('-trunk', id='leading-dash'),
        pytest.param('.trunk', id='leading-dot'),
        pytest.param('release..next', id='double-dot'),
        pytest.param('trunk/', id='trailing-slash'),
        pytest.param('trunk.lock', id='lock-suffix'),
        pytest.param('my branch', id='space'),
        pytest.param('trunk~1', id='revision-syntax'),
    ],
)
def test_default_branch_validator_rejects_invalid(generate, tmp_path_factory, bad_branch):
    """A branch name git would refuse, or one that needs quoting in YAML or a URL, never renders."""
    workdir = tmp_path_factory.mktemp('bad-default-branch')
    result = generate(workdir / PROJECT_SLUG, {'default_branch': bad_branch}, check=False)
    assert result.returncode != 0, f'copier accepted default_branch={bad_branch!r}'
    assert not (workdir / PROJECT_SLUG / 'pyproject.toml').exists()


@pytest.mark.parametrize(
    ('host', 'pages'),
    [pytest.param('github', True, id='github-pages'), pytest.param('gitlab', False, id='gitlab')],
)
def test_default_branch_is_spelled_from_one_answer(generate, tmp_path_factory, host, pages):
    """Generated for `trunk`, nothing in the project says `main` as a branch (ADR-0040).

    The trigger in a workflow file cannot be computed when the workflow runs, so the answer is
    written into the YAML at generation; the tasks read the same answer from `DEFAULT_BRANCH`
    in `configuration.py`. The four matrix cells all answer `main`, which is what `release` and
    the badge spelled before the question existed, so only a generation with another name can
    tell a rendered answer from a leftover literal.
    """
    workdir = tmp_path_factory.mktemp('default-branch')
    project = workdir / PROJECT_SLUG
    generate(project, {**combo_context(git_hosting_service=host, integrate_pages=pages), 'default_branch': 'trunk'})

    assert load_generated_configuration(project).DEFAULT_BRANCH == 'trunk'
    if host == 'github':
        workflows = project / '.github' / 'workflows'
        publish = yaml.safe_load((workflows / 'publish.yaml').read_text(encoding='utf-8'))
        assert publish[True]['push']['branches'] == ['trunk']
        pages_workflow = yaml.safe_load((workflows / 'pages.yaml').read_text(encoding='utf-8'))
        assert pages_workflow[True]['push']['branches'] == ['trunk']
        # The `${{ }}` expressions survive the file becoming a Jinja template.
        assert '${{ needs.build-deps-image.outputs.image }}' in (workflows / 'pages.yaml').read_text(encoding='utf-8')
    else:
        pipeline = (project / '.gitlab-ci.yml').read_text(encoding='utf-8')
        assert '$CI_DEFAULT_BRANCH' in pipeline, 'the GitLab pipeline no longer keys on the default branch'

    host_module = (project / '_CI' / 'tasks' / f'{host}.py').read_text(encoding='utf-8')
    assert 'DEFAULT_BRANCH' in host_module, 'the badge and the release request do not read the answer'
    release_py = (project / '_CI' / 'tasks' / 'release.py').read_text(encoding='utf-8')
    assert 'current_branch != DEFAULT_BRANCH' in release_py, '`release` does not check against the answer'

    assert lines_naming_main(project) == []


def test_exclude_newer_is_a_fixed_date(generated_project):
    """`exclude-newer` is an absolute date, not a rolling window.

    A relative `"1 week"` moved forward daily, so a resolution — and a green gate — could
    change with no commit behind it. That is how the toolchain drifted into a red lint run
    with no code change.
    """
    project, _ = generated_project
    for pyproject in (project / 'pyproject.toml', REPO_ROOT / 'pyproject.toml'):
        value = tomllib.loads(pyproject.read_text(encoding='utf-8'))['tool']['uv']['exclude-newer']
        assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', value), f'{pyproject} has a relative window: {value!r}'


def test_generated_quarantine_date_is_stamped_not_inherited(generated_project):
    """A new project's `exclude-newer` is its generation date, not a literal from the template.

    The template's own value recedes into the past between bumps; inheriting it would hand a
    project created a year later a boundary pinned to year-old packages. `tasks_render.py`
    overwrites it at generation, and this catches the stamp silently not running — in which
    case the fallback literal shows through and is already days stale.
    """
    project, _ = generated_project
    stamped = date.fromisoformat(
        tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))['tool']['uv']['exclude-newer']
    )
    # A day of slack absorbs a suite running across midnight; a missed stamp is far staler.
    today = date.today()  # noqa: DTZ011 - compared against a stamped calendar date
    assert abs((today - stamped).days) <= 1, f'quarantine date {stamped} was not stamped at generation'


def test_base_image_is_pinned_by_digest(generated_project):
    """The base image carries a digest and its tag matches the project's minimum Python.

    `[tool.docker-versions]` holds exactly one image. It used to also carry an `alpine-image`
    that nothing read — dead since the copier migration — which still had to be kept
    version-consistent with uv on every bump.
    """
    project, _ = generated_project
    data = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))
    images = data['tool']['docker-versions']
    minimum = data['project']['requires-python'].removeprefix('>=')
    base = images['base-image']
    assert '@sha256:' in base, f'base image not pinned by digest: {base}'
    assert f'python{minimum}-trixie-slim@' in base, f'tag does not match requires-python {minimum}: {base}'
    extra = sorted(set(images) - {'base-image'})
    assert set(images) == {'base-image'}, f'unused image references reintroduced: {extra}'


def test_generated_project_ships_a_lockfile(generated_project):
    """A resolved `uv.lock` ships, and it is not ignored.

    `Dockerfile.deps` runs `uv sync --frozen` and the deps-image tag hashes the lockfile;
    both previously relied on a lock created as a side effect of the first `uv run`.
    """
    project, _ = generated_project
    lock = project / 'uv.lock'
    assert lock.is_file(), 'no uv.lock was resolved at generation time'
    data = tomllib.loads(lock.read_text(encoding='utf-8'))
    assert data['package'], 'lockfile resolved no packages'
    ignore = (project / '.gitignore').read_text(encoding='utf-8')
    assert not re.search(r'^\s*/?uv\.lock\s*$', ignore, re.MULTILINE), 'uv.lock is gitignored'


def test_generation_honours_the_uv_version_override(generated_project):
    """Generation stamps exactly the version `TEMPLATE_UV_VERSION` asks for.

    The template's own CI depends on this: it installs the uv the template pins, then generates
    projects and runs `uv sync` with it. A freshly resolved `required-version` the ambient uv
    cannot satisfy would fail every matrix cell, so the fixture pins generation via this
    variable — and this asserts the pin actually took effect.
    """
    project, _ = generated_project
    assert set(uv_pins(project).values()) == {template_uv_version()}


def test_committed_digests_resolve_to_their_tags(uv_release):
    """Every digest in the template is the one its tag actually resolves to.

    The failure `maintain.bump-uv` exists to prevent: move the tag, leave a digest behind, and
    the reference still resolves to the *digest* — so projects keep building the old image while
    the file claims otherwise. Checks all five Pythons at once rather than once per matrix cell.

    Skipped when the registry cannot be reached: an unreachable ghcr is not a defect in this
    repository, and failing here would make the suite depend on network weather.
    """
    template = (REPO_ROOT / 'template' / 'pyproject.toml.jinja').read_text(encoding='utf-8')
    version = uv_release.current_pin(template)
    committed = dict(re.findall(r"^\s*'(\d+\.\d+)': '(sha256:[0-9a-f]+)',$", template, re.MULTILINE))
    assert committed, 'no per-Python digests found in the template'
    for python_version, digest in sorted(committed.items()):
        try:
            live = uv_release.image_digest(version, python_version)
        except uv_release.UvReleaseError as exc:
            pytest.skip(f'registry unreachable: {exc}')
        assert live == digest, f'uv {version} python{python_version}: committed {digest}, registry has {live}'


def test_every_uv_site_points_at_the_bump_command(generated_project):
    """Each uv pin carries a comment naming the command that moves them all.

    Five places hold the same version; editing one by hand is how they drift apart.
    """
    project, _ = generated_project
    content = (project / 'pyproject.toml').read_text(encoding='utf-8')
    for anchor in ('"uv==', 'requires = ["uv_build', 'required-version = "==', 'base-image = "'):
        index = content.index(anchor)
        # The pointer should be in the comment block immediately above the pin.
        preceding = content[:index].rsplit('\n\n', 1)[-1]
        assert 'develop.bump-uv' in preceding, f'no bump-uv pointer above {anchor!r}'


def test_override_variable_name_matches_the_generation_hook():
    """The harness and `tasks_render.py` agree on the override variable's name.

    They are two separate constants. If they drift the override silently stops working: every
    generated project resolves a fresh uv, the ambient uv no longer satisfies it, and all eight
    matrix cells fail on a version mismatch — a long way from the renamed string.
    """
    render = (REPO_ROOT / 'tasks_render.py').read_text(encoding='utf-8')
    assert f"UV_VERSION_ENV = '{UV_VERSION_ENV}'" in render, (
        f'tasks_render.py does not read {UV_VERSION_ENV}; the harness override would be ignored'
    )


def test_repo_uv_pin_points_at_its_own_command():
    """This repo's pin names `maintain.bump-uv`, which also refreshes the template's digests."""
    content = (REPO_ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    index = content.index('required-version = "==')
    assert 'maintain.bump-uv' in content[:index].rsplit('\n\n', 1)[-1]


def test_lock_task_derives_the_uv_version_from_the_project():
    """The copier lock task reads the uv version out of the rendered pyproject.

    Hardcoding it in copier.yml would silently drift from `[tool.uv] required-version`, and
    the generated project pins uv exactly — so a stale value there fails generation outright.
    """
    # Parsed, not grepped: the surrounding comments also mention `uvx uv@`.
    tasks = yaml.safe_load((REPO_ROOT / 'copier.yml').read_text(encoding='utf-8'))['_tasks']
    commands = [task['command'] if isinstance(task, dict) else task for task in tasks]
    lock_task = next(command for command in commands if 'uvx uv@' in command)
    assert 'required-version' in lock_task, 'lock task hardcodes a uv version instead of deriving it'
    assert 'pyproject.toml' in lock_task, 'lock task does not read the version from the rendered project'


def test_local_task_module_is_protected_from_updates():
    """`local.py` is in `_skip_if_exists`, without which the seam is pointless.

    The whole reason it exists is that template-owned modules are replaced on
    `copier update`. If it were not skipped it would be overwritten or conflict on every
    update — exactly the problem it is meant to remove.
    """
    config = yaml.safe_load((REPO_ROOT / 'copier.yml').read_text(encoding='utf-8'))
    skipped = config.get('_skip_if_exists') or []
    assert '_CI/tasks/local.py' in skipped, f'local.py is not protected from updates; skipped={skipped}'


def test_no_predecessor_template_name_survives(generated_project):
    """Nothing still calls the CI tooling package by the template's former name.

    `_CI/pyproject.toml` named it `backbone-template`, which `uv pip compile` then stamped into
    every `# via …` comment in `vendor.txt` — so the stale name was reproduced on each
    re-vendor.
    """
    project, _ = generated_project
    for relative in ('_CI/pyproject.toml', '_CI/lib/vendor.txt'):
        for root in (project, REPO_ROOT):
            content = (root / relative).read_text(encoding='utf-8')
            assert 'backbone' not in content.lower(), f'{root / relative} still names backbone-template'


def test_vendor_comments_agree_with_the_package_name(generated_project):
    """`vendor.txt`'s `# via <name>` comments match `_CI/pyproject.toml`'s project name.

    `uv pip compile` derives them from that name, so a mismatch means the two would diverge again
    the next time the vendored tree is regenerated.
    """
    project, _ = generated_project
    for root in (project, REPO_ROOT):
        name = re.search(
            r"^name = ['\"]([^'\"]+)['\"]", (root / '_CI' / 'pyproject.toml').read_text(encoding='utf-8'), re.MULTILINE
        ).group(1)
        vendor = (root / '_CI' / 'lib' / 'vendor.txt').read_text(encoding='utf-8')
        # `uv pip compile` indents the `# via …` comment under the requirement it belongs to.
        cited = set(re.findall(r'^\s*#\s+via ([a-z0-9-]+) \(pyproject\.toml\)\s*$', vendor, re.MULTILINE))
        assert cited, f'{root}: no self-referential via comments found in vendor.txt'
        assert cited == {name}, f'{root}: vendor.txt cites {cited}, pyproject declares {name!r}'


def test_project_slug_sanitizes_punctuated_name(generate, tmp_path_factory):
    """A punctuated project_name still derives a usable slug.

    The derived slug must be both a valid Python identifier and a valid
    (normalizable) PyPI project name.
    """
    project = tmp_path_factory.mktemp('slug-punctuation') / 'out'
    generate(project, {'project_name': "Username's Toolkit"})
    slug = tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))['project']['name']
    assert slug == 'username_s_toolkit'
    # Valid import name (Python identifier) and valid PyPI name per name-normalization spec:
    # start with a letter, end with a letter/digit, only lowercase letters/digits/underscores.
    assert slug.isidentifier()
    assert re.fullmatch(r'[a-z]([a-z0-9_]*[a-z0-9])?', slug)
    assert (project / 'src' / slug).is_dir()


@pytest.mark.parametrize(
    'bad_data',
    [
        pytest.param({'project_slug': '3d_vision'}, id='leading-digit'),
        pytest.param({'project_slug': 'bad-slug!'}, id='punctuation'),
        pytest.param({'project_slug': '_foo'}, id='leading-underscore'),
        pytest.param({'project_slug': 'foo_'}, id='trailing-underscore'),
        pytest.param({'project_slug': ''}, id='empty'),
        pytest.param({'project_name': '3D Vision'}, id='derived-leading-digit'),
    ],
)
def test_project_slug_validator_rejects_invalid(generate, tmp_path_factory, bad_data):
    """The project_slug validator aborts generation instead of writing a broken project.

    A slug must be both a valid Python identifier and a valid PyPI name, whether it
    was supplied directly or derived from project_name.
    """
    project = tmp_path_factory.mktemp('slug-invalid') / 'out'
    result = generate(project, bad_data, check=False)
    assert result.returncode != 0, 'copier should have aborted on an invalid project_slug'
    assert not (project / 'pyproject.toml').exists(), 'no project should be written on validation failure'


@pytest.mark.parametrize('license_choice', ['Apache-2.0', 'MIT', 'BSD-3-Clause', 'None'])
def test_license_file_matches_choice(generate, tmp_path_factory, license_choice):
    """Each license choice produces (or skips) a LICENSE file at the project root."""
    project = tmp_path_factory.mktemp(f'license-{license_choice}') / PROJECT_SLUG
    generate(project, {'license': license_choice})
    if license_choice == 'None':
        assert not (project / 'LICENSE').exists()
    else:
        assert (project / 'LICENSE').exists()


@pytest.mark.parametrize('tree', VENDOR_TREES)
def test_vendored_tree_matches_its_manifest(tree):
    """Every vendored package is pinned in vendor.txt, and every pin is present in the tree.

    The tree is copied verbatim by `maintain.sync-vendor`, not a place to add or delete files. A package
    present without a pin means someone edited the tree by hand; a pin without a package means
    the tree is stale. Either way it no longer reproduces from its declared input.
    """
    lib = REPO_ROOT / tree
    on_disk, pinned = vendored_packages(lib), manifest_packages(lib)
    assert on_disk == pinned, f'{tree}: unpinned {sorted(on_disk - pinned)}, missing {sorted(pinned - on_disk)}'


@pytest.mark.parametrize('tree', VENDOR_TREES)
def test_vendored_tree_is_pure_python(tree):
    """No compiled extensions in a tree whose entire purpose is running anywhere.

    Vendoring `tomli` produced a `__mypyc.cpython-314-darwin.so`: 427 KiB usable on exactly one
    operating system, architecture and Python version, shipped to every generated project.
    A binary here is portability quietly lost, and nothing else would report it.
    """
    vendor = REPO_ROOT / tree / 'vendor'
    binaries = [str(p.relative_to(vendor)) for p in vendor.rglob('*') if p.suffix in {'.so', '.pyd', '.dylib'}]
    assert not binaries, f'{tree}: platform-specific binaries vendored: {binaries}'


def test_both_vendored_trees_are_identical():
    """This repository and the template ship the same vendored invoke, byte for byte.

    They are two copies of one upstream artefact. Letting them drift means a generated project
    runs different code from the repository that produced it, and the difference would only
    surface as a bug somewhere downstream.
    """
    parent, template = (REPO_ROOT / tree / 'vendor' for tree in VENDOR_TREES)
    parent_files = {p.relative_to(parent): p.read_bytes() for p in source_files(parent)}
    template_files = {p.relative_to(template): p.read_bytes() for p in source_files(template)}
    assert parent_files.keys() == template_files.keys(), (
        f'only in _CI: {sorted(map(str, parent_files.keys() - template_files.keys()))}; '
        f'only in template: {sorted(map(str, template_files.keys() - parent_files.keys()))}'
    )
    differing = sorted(str(name) for name, data in parent_files.items() if template_files[name] != data)
    assert not differing, f'vendored files differ between the two trees: {differing}'


def test_vendored_invoke_records_an_immutable_pin():
    """The vendored tree names the exact upstream commit it came from.

    A tag can be moved; a commit cannot. This is the same reason every action in these
    workflows is pinned by SHA, and it is what lets `maintain.sync-vendor` be re-run to prove
    the committed tree still matches its source.
    """
    pin = tomllib.loads((REPO_ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['tool']['vendored-invoke']
    assert pin['repository'] == 'schubergphilis/vendored_invoke'
    assert re.fullmatch(r'v\d+\.\d+\.\d+', pin['version']), f'version {pin["version"]!r} is not a release tag'
    assert re.fullmatch(r'[0-9a-f]{40}', pin['commit']), f'commit {pin["commit"]!r} is not a full SHA'
