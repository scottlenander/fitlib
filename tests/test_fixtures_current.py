"""The committed fixtures in tests/fixtures/fit/ must match what the specs generate.

If this fails after changing ``specs.py`` or ``generate.py``, regenerate with
``uv run python -m tests.fixtures.generate`` and commit the result.
"""

from __future__ import annotations

from tests.fixtures.generate import FIT_DIR, build_all

REGENERATE = "run `uv run python -m tests.fixtures.generate` and commit the result"


def test_generation_is_deterministic():
    assert build_all() == build_all()


def test_committed_fixtures_match_the_specs():
    expected = build_all()
    committed = {path.name: path.read_bytes() for path in FIT_DIR.glob("*.fit")}
    assert sorted(committed) == sorted(expected), f"Fixture files differ; {REGENERATE}"
    stale = [name for name, data in expected.items() if committed[name] != data]
    assert not stale, f"Stale fixtures {stale}; {REGENERATE}"
