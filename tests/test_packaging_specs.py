"""Conformance of a generated project's distributions to the PyPA packaging specifications.

https://packaging.python.org/en/latest/specifications/ is the source of truth for every
assertion here. Each test names the spec it checks. The suite builds one generated project
(GitHub, Pages on, a repository URL, the default Apache-2.0 licence) with the uv the template
pins, then reads the sdist and the wheel the way an index or an installer would, and installs
the wheel into a scratch virtual environment to check what an installer records.

One cell rather than the matrix: the knobs change CI files and docs, not the build. What
differs between cells in pyproject.toml (`[project.urls]`) is covered per cell by
`test_project_urls_use_well_known_labels` in the invariants suite.
"""

import base64
import csv
import hashlib
import io
import json
import os
import subprocess
import tarfile
import tomllib
import zipfile
from email.parser import HeaderParser
from pathlib import Path

import pytest
from packaging.licenses import canonicalize_license_expression
from packaging.metadata import Metadata
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import Tag
from packaging.utils import canonicalize_name, parse_sdist_filename, parse_wheel_filename
from packaging.version import Version
from validate_pyproject import api as validate_pyproject_api

from _CI.tasks.configuration import PROJECT_SLUG, combo_context, template_uv_version


def uv(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run the uv the template pins, so the build matches what a generated project does."""
    return subprocess.run(
        ['uvx', f'uv@{template_uv_version()}', *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope='module')
def built_project(generate, tmp_path_factory):
    """Generate one project, build it, and return ``(project, wheel, sdist)``."""
    project = tmp_path_factory.mktemp('packaging-specs') / PROJECT_SLUG
    generate(project, combo_context(git_hosting_service='github', integrate_pages=True))
    uv('build', '--quiet', cwd=project)
    dist = project / 'dist'
    wheels = list(dist.glob('*.whl'))
    sdists = list(dist.glob('*.tar.gz'))
    assert len(wheels) == 1, f'expected one wheel, got {wheels}'
    assert len(sdists) == 1, f'expected one sdist, got {sdists}'
    return project, wheels[0], sdists[0]


@pytest.fixture(scope='module')
def pyproject(built_project):
    """The generated pyproject.toml, parsed."""
    project, _, _ = built_project
    return tomllib.loads((project / 'pyproject.toml').read_text(encoding='utf-8'))


def dist_info(wheel):
    """Return the ``<name>-<version>.dist-info`` directory name inside ``wheel``."""
    name, version, _, _ = parse_wheel_filename(wheel.name)
    return f'{str(name).replace("-", "_")}-{version}.dist-info'


def read_wheel_file(wheel, member):
    """Return one member of the wheel as text."""
    with zipfile.ZipFile(wheel) as archive:
        return archive.read(member).decode('utf-8')


def wheel_metadata(wheel):
    """Parse the wheel's METADATA with `packaging`, validating every field it knows."""
    return Metadata.from_email(read_wheel_file(wheel, f'{dist_info(wheel)}/METADATA'), validate=True)


def test_pyproject_validates_against_the_pypa_schemas(pyproject):
    """pyproject.toml spec, dependency-groups spec, PyPA schemas: validate-pyproject accepts it."""
    validate_pyproject_api.Validator()(pyproject)


def test_project_name_is_normalized_everywhere(built_project, pyproject):
    """Names and normalization: the sdist, the wheel and METADATA all name the same project."""
    _, wheel, sdist = built_project
    canonical = canonicalize_name(pyproject['project']['name'])
    wheel_name, _, _, _ = parse_wheel_filename(wheel.name)
    sdist_name, _ = parse_sdist_filename(sdist.name)
    assert wheel_name == canonical
    assert sdist_name == canonical
    assert canonicalize_name(wheel_metadata(wheel).name) == canonical
    # Filename components escape the normalized name with underscores, per both format specs.
    assert wheel.name.startswith(canonical.replace('-', '_') + '-')
    assert sdist.name.startswith(canonical.replace('-', '_') + '-')


def test_version_is_canonical_pep440(built_project, pyproject):
    """Version specifiers: the version is in canonical PEP 440 form and matches the filenames."""
    _, wheel, sdist = built_project
    version = pyproject['project']['version']
    assert str(Version(version)) == version
    assert parse_wheel_filename(wheel.name)[1] == Version(version)
    assert parse_sdist_filename(sdist.name)[1] == Version(version)


def test_core_metadata_is_valid_and_current(built_project, pyproject):
    """Core metadata: METADATA parses with validation, at a version that carries License-Expression."""
    _, wheel, _ = built_project
    metadata = wheel_metadata(wheel)
    assert Version(metadata.metadata_version) >= Version('2.4'), 'License-Expression needs Metadata-Version 2.4'
    assert metadata.summary == pyproject['project']['description']
    assert metadata.description_content_type == 'text/markdown'
    assert metadata.requires_python == SpecifierSet(pyproject['project']['requires-python'])


def test_license_expression_is_canonical_spdx(built_project, pyproject):
    """License expression: canonical SPDX, and no legacy `License ::` classifier beside it."""
    _, wheel, _ = built_project
    expression = pyproject['project']['license']
    assert canonicalize_license_expression(expression) == expression
    metadata = wheel_metadata(wheel)
    assert metadata.license_expression == expression
    assert not [c for c in metadata.classifiers or [] if c.startswith('License ::')]


def test_license_file_ships_under_licenses(built_project):
    """Glob patterns + binary distribution format: `license-files` lands in `.dist-info/licenses/`."""
    _, wheel, _ = built_project
    with zipfile.ZipFile(wheel) as archive:
        assert f'{dist_info(wheel)}/licenses/LICENSE' in archive.namelist()
    assert wheel_metadata(wheel).license_files == ['LICENSE']


def test_dependency_specifiers_parse(built_project, pyproject):
    """Dependency specifiers: every requirement, runtime or grouped, is valid PEP 508."""
    _, wheel, _ = built_project
    for requirement in wheel_metadata(wheel).requires_dist or []:
        assert isinstance(requirement, Requirement)
    for group, entries in pyproject['dependency-groups'].items():
        for entry in entries:
            if isinstance(entry, str):
                Requirement(entry)
            else:
                assert set(entry) == {'include-group'}, f'{group}: unknown table entry {entry}'


def test_dependency_group_includes_resolve(pyproject):
    """Dependency groups: every `include-group` names a group that exists, with no cycle."""
    groups = pyproject['dependency-groups']

    def expand(name, seen):
        assert name in groups, f'include-group {name!r} names no group'
        assert name not in seen, f'include-group cycle through {name!r}'
        for entry in groups[name]:
            if isinstance(entry, dict):
                expand(entry['include-group'], seen | {name})

    for name in groups:
        expand(name, frozenset())


def test_wheel_is_pure_python(built_project):
    """Platform compatibility tags + binary distribution format: one `py3-none-any` wheel, purelib."""
    _, wheel, _ = built_project
    _, _, build, tags = parse_wheel_filename(wheel.name)
    assert build == ()
    assert tags == frozenset({Tag('py3', 'none', 'any')})
    headers = HeaderParser().parsestr(read_wheel_file(wheel, f'{dist_info(wheel)}/WHEEL'))
    assert headers['Wheel-Version'] == '1.0'
    assert headers['Root-Is-Purelib'] == 'true'
    assert headers.get_all('Tag') == ['py3-none-any']


def test_wheel_record_covers_every_file_with_its_hash(built_project):
    """Binary distribution format: RECORD lists every file, each with a matching sha256."""
    _, wheel, _ = built_project
    record_name = f'{dist_info(wheel)}/RECORD'
    with zipfile.ZipFile(wheel) as archive:
        rows = {row[0]: row[1:] for row in csv.reader(io.StringIO(archive.read(record_name).decode('utf-8')))}
        # Directory entries are allowed in the zip, but RECORD lists files.
        files = [name for name in archive.namelist() if not name.endswith('/')]
        assert set(rows) == set(files), 'RECORD and the archive list different files'
        for name in files:
            digest, size = rows[name]
            if name == record_name:
                assert digest == '', 'RECORD must not hash itself'
                assert size == '', 'RECORD must not size itself'
                continue
            content = archive.read(name)
            expected = 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b'=').decode()
            assert digest == expected, f'{name}: RECORD hash does not match'
            assert int(size) == len(content), f'{name}: RECORD size does not match'


def test_wheel_ships_the_typing_marker(built_project, pyproject):
    """The package is typed: `py.typed` ships so type checkers read the inline annotations."""
    _, wheel, _ = built_project
    with zipfile.ZipFile(wheel) as archive:
        assert f'{pyproject["project"]["name"]}/py.typed' in archive.namelist()


def test_sdist_layout(built_project, pyproject):
    """Source distribution format: one top-level directory, PKG-INFO >= 2.2, pyproject.toml inside."""
    _, _, sdist = built_project
    name, version = parse_sdist_filename(sdist.name)
    root = f'{str(name).replace("-", "_")}-{version}'
    with tarfile.open(sdist) as archive:
        members = archive.getnames()
        assert {member.split('/', 1)[0] for member in members} == {root}
        assert f'{root}/pyproject.toml' in members
        pkg_info = archive.extractfile(f'{root}/PKG-INFO').read().decode('utf-8')
    metadata = Metadata.from_email(pkg_info, validate=True)
    assert Version(metadata.metadata_version) >= Version('2.2'), 'sdists need Metadata-Version 2.2 or later'
    assert metadata.version == Version(pyproject['project']['version'])


def test_installed_wheel_is_recorded(built_project, pyproject, tmp_path):
    """Recording installed projects + direct URL: an installer records what it installed, and how.

    Installs the wheel into a scratch environment with the pinned uv and checks the
    `.dist-info` it leaves: RECORD, INSTALLER, `direct_url.json` with `archive_info` (installed
    from a file, not an index), and that the package imports and reports its version.
    """
    _, wheel, _ = built_project
    venv = tmp_path / 'venv'
    uv('venv', '--quiet', str(venv), cwd=tmp_path)
    python = venv / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    uv('pip', 'install', '--quiet', '--python', str(python), str(wheel), cwd=tmp_path)
    name = pyproject['project']['name']
    probe = (
        'import importlib.metadata as m, json, sys;'
        f'import {name};'
        f'd = m.distribution({name!r});'
        'print(json.dumps({"version": d.version, "installer": d.read_text("INSTALLER"),'
        ' "direct_url": json.loads(d.read_text("direct_url.json")),'
        ' "record": d.read_text("RECORD") is not None}))'
    )
    report = json.loads(subprocess.run([str(python), '-c', probe], check=True, capture_output=True, text=True).stdout)
    assert report['version'] == pyproject['project']['version']
    assert report['installer'].strip() == 'uv'
    assert report['record']
    assert 'archive_info' in report['direct_url']
    assert report['direct_url']['url'] == Path(wheel).resolve().as_uri()
