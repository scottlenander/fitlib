"""The committed fixtures in tests/fixtures/fit/ must match what the specs generate.

If this fails after changing ``specs.py`` or ``generate.py``, regenerate with
``uv run python -m tests.fixtures.generate`` and commit the result.
"""

from __future__ import annotations

from tests.fixtures.generate import FIT_DIR, build_all

REGENERATE = "run `uv run python -m tests.fixtures.generate` and commit the result"


def test_generation_is_deterministic():
    """Generating the fixtures twice gives byte-identical files.

    Given: the specs in ``specs.py``, built twice in a row.
    Expect: the same file names with the same bytes, so committed fixtures can be checked.
    """
    first = build_all()

    second = build_all()

    assert first == second, "fixture generation should not depend on time or randomness"


def test_committed_fixtures_match_the_specs():
    """The ``.fit`` files in the repo are exactly what the current specs generate.

    Given: the committed files in ``tests/fixtures/fit/`` and a fresh build from the specs.
    Expect: the same set of file names, each with identical bytes.
    """
    expected = build_all()

    committed = {path.name: path.read_bytes() for path in FIT_DIR.glob("*.fit")}
    stale = [name for name, data in expected.items() if committed.get(name) != data]

    assert sorted(committed) == sorted(expected), f"Fixture files differ; {REGENERATE}"
    assert not stale, f"Stale fixtures {stale}; {REGENERATE}"
