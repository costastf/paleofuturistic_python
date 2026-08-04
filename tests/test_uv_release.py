"""Unit tests for the uv release resolver shared by this repo and generated projects.

Network-free: PyPI's payload is injected so the cool-down boundary can be tested against a
frozen clock. `template/_CI/uv_release.py` is loaded from source because it ships into generated
projects and is imported here from the same file — one implementation, one set of tests.
"""

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def load_module():
    """Import the resolver from the template source."""
    path = REPO_ROOT / 'template' / '_CI' / 'uv_release.py'
    spec = importlib.util.spec_from_file_location('uv_release_unit', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def uv_release():
    return load_module()


def payload(releases):
    """Build a PyPI-shaped payload from `{version: datetime}`."""
    return {
        'releases': {
            version: [{'upload_time_iso_8601': moment.isoformat().replace('+00:00', 'Z')}]
            for version, moment in releases.items()
        }
    }


def with_releases(uv_release, monkeypatch, releases):
    """Point the resolver at a canned release set instead of PyPI."""
    monkeypatch.setattr(uv_release, 'fetch_json', lambda _url: payload(releases))


def test_picks_the_newest_release_past_the_cooldown(uv_release, monkeypatch):
    with_releases(
        uv_release,
        monkeypatch,
        {
            '0.11.30': NOW - timedelta(days=20),
            '0.11.32': NOW - timedelta(days=11),
            '0.11.33': NOW - timedelta(days=2),  # too new
        },
    )
    version, released = uv_release.latest_eligible(now=NOW)
    assert version == '0.11.32'
    assert released == NOW - timedelta(days=11)


def test_cooldown_boundary_is_inclusive(uv_release, monkeypatch):
    """A release exactly at the cool-down age is eligible; a second later it is not.

    Pinning the boundary matters because it decides, on any given day, whether a release is
    taken — the difference between two adjacent versions.
    """
    with_releases(
        uv_release,
        monkeypatch,
        {'0.11.30': NOW - timedelta(days=30), '0.12.0': NOW - timedelta(days=7)},
    )
    assert uv_release.latest_eligible(now=NOW)[0] == '0.12.0'

    with_releases(
        uv_release,
        monkeypatch,
        {'0.11.30': NOW - timedelta(days=30), '0.12.0': NOW - timedelta(days=7) + timedelta(seconds=1)},
    )
    assert uv_release.latest_eligible(now=NOW)[0] == '0.11.30'


def test_pre_releases_are_never_chosen(uv_release, monkeypatch):
    """An rc is never picked automatically, however old it is."""
    with_releases(
        uv_release,
        monkeypatch,
        {
            '0.11.32': NOW - timedelta(days=11),
            '0.12.0rc1': NOW - timedelta(days=30),
            '0.12.0b2': NOW - timedelta(days=30),
            '0.12.0.dev1': NOW - timedelta(days=30),
        },
    )
    assert uv_release.latest_eligible(now=NOW)[0] == '0.11.32'


def test_versions_compare_numerically_not_lexically(uv_release, monkeypatch):
    """0.11.9 must not beat 0.11.10 — string ordering would get this wrong."""
    with_releases(
        uv_release,
        monkeypatch,
        {'0.11.9': NOW - timedelta(days=30), '0.11.10': NOW - timedelta(days=20)},
    )
    assert uv_release.latest_eligible(now=NOW)[0] == '0.11.10'


def test_earliest_upload_dates_a_release(uv_release, monkeypatch):
    """A release is aged from its first file, not its last.

    Later platform wheels can trail the first by hours; the cool-down should run from when the
    release first became usable.
    """
    first = NOW - timedelta(days=7)
    monkeypatch.setattr(
        uv_release,
        'fetch_json',
        lambda _url: {
            'releases': {
                '0.12.0': [
                    {'upload_time_iso_8601': (first + timedelta(hours=6)).isoformat().replace('+00:00', 'Z')},
                    {'upload_time_iso_8601': first.isoformat().replace('+00:00', 'Z')},
                ]
            }
        },
    )
    version, released = uv_release.latest_eligible(now=NOW)
    assert version == '0.12.0'
    assert released == first


def test_nothing_eligible_raises(uv_release, monkeypatch):
    with_releases(uv_release, monkeypatch, {'0.12.0': NOW - timedelta(days=1)})
    with pytest.raises(uv_release.UvReleaseError, match='older than 7 days'):
        uv_release.latest_eligible(now=NOW)


@pytest.mark.parametrize('releases', [{}, {'0.12.0': None}], ids=['empty', 'undated'])
def test_unusable_payloads_raise(uv_release, monkeypatch, releases):
    """An empty or undated payload is an error, never silently 'no update available'."""
    monkeypatch.setattr(
        uv_release,
        'fetch_json',
        lambda _url: {'releases': {version: [] for version in releases}},
    )
    with pytest.raises(uv_release.UvReleaseError):
        uv_release.latest_eligible(now=NOW)


@pytest.mark.parametrize(
    ('current', 'candidate', 'expected'),
    [
        ('0.11.30', '0.11.32', False),
        ('0.11.30', '0.12.0', True),
        ('0.11.30', '1.0.0', True),
        ('0.12.1', '0.12.9', False),
    ],
)
def test_crosses_minor(uv_release, current, candidate, expected):
    """uv is pre-1.0, so a minor bump is the one that warrants a warning."""
    assert uv_release.crosses_minor(current, candidate) is expected


def test_current_pin_requires_an_exact_pin(uv_release):
    assert uv_release.current_pin('required-version = "==0.11.30"\n') == '0.11.30'
    with pytest.raises(uv_release.UvReleaseError, match='exact'):
        uv_release.current_pin('required-version = ">=0.11.30"\n')
