"""The committed fixtures in tests/fixtures/fit/ must match what the specs generate.

If this fails after changing ``specs.py`` or ``generate.py``, regenerate with
``uv run python -m tests.fixtures.generate`` and commit the result.
"""

from __future__ import annotations

import pytest

from tests.fixtures.generate import EXTRA_DIR, FIT_DIR, build_all, build_extra

REGENERATE = "run `uv run python -m tests.fixtures.generate` and commit the result"


# Module scope: building every fixture takes a few seconds, so both tests share one build.
@pytest.fixture(scope="module")
def generated() -> dict[str, bytes]:
    """Build every fixture once for this module.

    Returns:
        File contents keyed by file name.
    """
    return build_all()


def test_generation_is_deterministic(generated: dict[str, bytes]):
    """Generating the fixtures twice gives byte-identical files.

    Given: the specs in ``specs.py``, built twice in a row.
    Expect: the same file names with the same bytes, so committed fixtures can be checked.
    """
    second = build_all()

    assert generated == second, "fixture generation should not depend on time or randomness"


def test_committed_fixtures_match_the_specs(generated: dict[str, bytes]):
    """The files in ``tests/fixtures/fit/`` are exactly what the current specs generate.

    Given: the committed ``.fit`` and ``.zip`` files and a fresh build from the specs.
    Expect: the same set of file names, each with identical bytes.
    """
    expected = generated

    committed = {path.name: path.read_bytes() for path in FIT_DIR.iterdir() if path.is_file()}
    stale = [name for name, data in expected.items() if committed.get(name) != data]

    assert sorted(committed) == sorted(expected), f"Fixture files differ; {REGENERATE}"
    assert not stale, f"Stale fixtures {stale}; {REGENERATE}"


def test_committed_extra_rides_match_the_specs():
    """The rides in ``tests/fixtures/extra/`` are exactly what their specs generate.

    Given: the committed extra rides and a fresh build of ``EXTRA_RIDES``.
    Expect: the same file names with identical bytes.
    """
    committed = {path.name: path.read_bytes() for path in EXTRA_DIR.iterdir() if path.is_file()}

    assert committed == build_extra(), f"Extra fixtures differ; {REGENERATE}"
