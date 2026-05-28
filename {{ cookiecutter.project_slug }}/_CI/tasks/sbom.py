"""Compose a CycloneDX 1.6 SBOM covering runtime deps, vendored CI deps, and pipeline components."""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
import warnings
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

from cyclonedx.model.bom import Bom
from cyclonedx.model.component import Component, ComponentType
from cyclonedx.output.json import JsonV1Dot6
from packageurl import PackageURL

from .configuration import SBOM_FILE, VENDOR_TXT
from .{{ cookiecutter.git_hosting_service }} import iter_pipeline_components
from .shared import PipelineComponent

REQUIREMENT_PATTERN = re.compile(r'^([A-Za-z0-9._\-]+)==([A-Za-z0-9._\-+]+)')


class PinnedRequirement(NamedTuple):
    """A single `name==version` requirement, normalised to lowercase name."""

    name: str
    version: str


def iter_runtime_requirements() -> Iterator[PinnedRequirement]:
    """Yield runtime dependencies from `uv export --no-dev` (lockfile-pinned, dev groups excluded)."""
    result = subprocess.run(
        ['uv', 'export', '--no-dev', '--format', 'requirements-txt', '--no-hashes', '--no-header'],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f'uv export failed: {result.stderr}', file=sys.stderr)
        raise SystemExit(1)
    yield from iter_requirements_lines(result.stdout.splitlines())


def iter_vendored_requirements() -> Iterator[PinnedRequirement]:
    """Yield vendored CI deps from `_CI/lib/vendor.txt` (pip-compile output)."""
    if not VENDOR_TXT.exists():
        return
    yield from iter_requirements_lines(VENDOR_TXT.read_text(encoding='utf-8').splitlines())


def iter_requirements_lines(lines: Iterable[str]) -> Iterator[PinnedRequirement]:
    """Parse `name==version` requirements out of a sequence of requirements.txt-style lines."""
    for raw in lines:
        clean = raw.split('#', 1)[0].strip()
        if not clean or clean.startswith('-'):
            continue
        match = REQUIREMENT_PATTERN.match(clean)
        if not match:
            continue
        yield PinnedRequirement(name=match.group(1).lower(), version=match.group(2))


def read_project_metadata() -> tuple[str, str]:
    """Return (project name, version) from pyproject.toml."""
    data = tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8'))
    project = data['project']
    return project['name'], project['version']


def pypi_component(req: PinnedRequirement):
    """Build a PyPI-typed CycloneDX component from a pinned requirement."""
    return Component(
        name=req.name,
        version=req.version,
        type=ComponentType.LIBRARY,
        purl=PackageURL(type='pypi', name=req.name, version=req.version),
    )


def pipeline_to_component(spec: PipelineComponent):
    """Build a CycloneDX component from a host-supplied pipeline-component spec."""
    return Component(
        name=spec.name,
        version=spec.version,
        type=ComponentType.LIBRARY,
        purl=PackageURL.from_string(spec.purl),
    )


def build_bom():
    """Build the in-memory CycloneDX Bom covering all three sources."""
    name, version = read_project_metadata()
    root = Component(
        name=name,
        version=version,
        type=ComponentType.LIBRARY,
        purl=PackageURL(type='pypi', name=name, version=version),
    )
    bom = Bom()
    bom.metadata.timestamp = datetime.now(UTC)
    bom.metadata.component = root
    runtime_components = []
    seen: set[tuple[str, str]] = set()
    for req in iter_runtime_requirements():
        if (req.name, req.version) in seen:
            continue
        seen.add((req.name, req.version))
        component = pypi_component(req)
        runtime_components.append(component)
        bom.components.add(component)
    for req in iter_vendored_requirements():
        if (req.name, req.version) in seen:
            continue
        seen.add((req.name, req.version))
        bom.components.add(pypi_component(req))
    for spec in iter_pipeline_components():
        bom.components.add(pipeline_to_component(spec))
    # Declare the root's direct runtime dependencies so the BOM carries a
    # NTIA-compliant dependency graph. Vendored and pipeline components are
    # parallel artefacts of the codebase, not transitive deps of the wheel.
    bom.register_dependency(root, runtime_components)
    return bom


def render_sbom() -> str:
    """Return the CycloneDX 1.6 JSON serialization of the assembled Bom."""
    with warnings.catch_warnings():
        # cyclonedx-python-lib warns when the root component declares zero
        # runtime dependencies — which is the legitimate case for a freshly
        # generated project with `dependencies = []`. The warning is
        # informational, not actionable for an empty-deps project.
        warnings.filterwarnings(
            'ignore',
            message='The Component this BOM is describing .* has no defined dependencies',
            category=UserWarning,
        )
        return JsonV1Dot6(build_bom()).output_as_string(indent=2)


def write_sbom(target: Path = SBOM_FILE) -> None:
    """Write the CycloneDX SBOM to `target`, creating parent dirs as needed."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_sbom() + '\n', encoding='utf-8')


VALIDATE_SCRIPT = (
    'import sys\n'
    'from pathlib import Path\n'
    'from cyclonedx.validation.json import JsonStrictValidator\n'
    'from cyclonedx.schema import SchemaVersion\n'
    'validator = JsonStrictValidator(SchemaVersion.V1_6)\n'
    'error = validator.validate_str(Path(sys.argv[1]).read_text(encoding="utf-8"))\n'
    'if error is not None:\n'
    '    print(str(error), file=sys.stderr)\n'
    '    sys.exit(1)\n'
)


def validate_sbom(target: Path = SBOM_FILE) -> list[str]:
    """Validate the SBOM at `target` against the CycloneDX 1.6 JSON schema.

    Runs in a `uv run python` subprocess so the venv-installed
    cyclonedx-python-lib + jsonschema win over the vendored CI libs that the
    workflow.cmd launcher places earlier on sys.path. Returns a list of
    error messages (empty when the SBOM is valid).
    """
    result = subprocess.run(
        ['uv', 'run', 'python', '-c', VALIDATE_SCRIPT, str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return []
    return [(result.stderr or result.stdout).strip()]
