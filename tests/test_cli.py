"""The ``fitlib`` command line, run through Typer's test runner against a temp library."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fitlib.cli import EXIT_ERROR, EXIT_IMPORT_FAILURES, app
from tests.fixtures.generate import FIT_DIR

# Wide output so tables don't wrap and assertions can match whole rows.
runner = CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1"})


@pytest.fixture
def config(tmp_path: Path) -> Path:
    path = tmp_path / "fitlib.toml"
    path.write_text(f'library = "{tmp_path / "library"}"\n')
    return path


def run(config: Path, *args: str):
    return runner.invoke(app, ["--config", str(config), *args])


@pytest.fixture
def imported(config: Path) -> Path:
    """A library with the fixture folder already imported."""
    run(config, "import", str(FIT_DIR), "--workers", "1")
    return config


def ride_ids(output: str) -> list[str]:
    return re.findall(r"^\s*([0-9a-f]{8})\s", output, flags=re.MULTILINE)


def test_import_reports_counts_and_problem_files(config: Path):
    """``fitlib import`` prints a one-line summary and lists skipped and failed files.

    Given: the fixture folder, which includes a run, an overlapping recording and a
    truncated file.
    Expect: "Imported 8, already in library 1, skipped 2, failed 1", the problem files named
    with reasons, and exit code 1 because a file failed.
    """
    result = run(config, "import", str(FIT_DIR), "--workers", "1")

    assert "Imported 8, already in library 1, skipped 2, failed 1." in result.output
    assert "not a ride (running)" in result.output
    assert "corrupt_truncated.fit" in result.output
    assert result.exit_code == EXIT_IMPORT_FAILURES, "a failed file should give exit code 1"


def test_clean_import_exits_zero(config: Path, tmp_path: Path):
    """An import where every file is fine exits 0.

    Given: a folder holding one good ride.
    Expect: "Imported 1" and exit code 0.
    """
    folder = tmp_path / "rides"
    folder.mkdir()
    shutil.copy(FIT_DIR / "garmin_nord_pause_10min.fit", folder)

    result = run(config, "import", str(folder))

    assert "Imported 1, already in library 0, skipped 0, failed 0." in result.output
    assert result.exit_code == 0


def test_import_of_a_missing_path_is_an_error(config: Path, tmp_path: Path):
    """A path that doesn't exist stops the import before anything is read.

    Given: a folder path that doesn't exist.
    Expect: an error naming it and exit code 2.
    """
    result = run(config, "import", str(tmp_path / "nowhere"))

    assert "No such file or folder" in result.output
    assert result.exit_code == EXIT_ERROR


def test_list_shows_newest_first(imported: Path):
    """``fitlib list`` shows rides newest first with their figures and a count.

    Given: the imported fixture library.
    Expect: 8 rows, the newest (24 Aug) first and the Zwift ride (2 Aug) last, and
    "Showing 1–8 of 8."
    """
    result = run(imported, "list")
    lines = [line for line in result.output.splitlines() if re.match(r"^\s*[0-9a-f]{8}\s", line)]

    assert len(lines) == 8
    assert "2025-08-24" in lines[0], "the newest ride should be first"
    assert "Zwift ride, 2 Aug 2025" in lines[-1]
    assert "Showing 1–8 of 8." in result.output
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("args", "expected_rows"),
    [
        (["--source", "zwift"], 1),
        (["--indoor"], 2),
        (["--outdoor", "--min-minutes", "40"], 2),
        (["--since", "2025-08-20"], 2),
        (["--text", "edge"], 7),
        (["--limit", "3", "--offset", "6"], 2),
    ],
    ids=["source", "indoor", "outdoor-long", "since", "text", "page"],
)
def test_list_filters(imported: Path, args: list[str], expected_rows: int):
    """Each ``list`` option narrows or pages the results.

    Given: the imported library: 1 Zwift ride, 7 Garmin rides (1 indoor; 2 outdoor rides of
    40 min or more; 2 rides on or after 20 Aug).
    Expect: the stated number of rows for each option.
    """
    result = run(imported, "list", *args)

    assert len(ride_ids(result.output)) == expected_rows
    assert result.exit_code == 0


def test_list_with_no_matches(imported: Path):
    """A search that finds nothing says so.

    Given: a text search for a word no ride contains.
    Expect: "No rides found." and exit code 0.
    """
    result = run(imported, "list", "--text", "tourmalet")

    assert "No rides found." in result.output
    assert result.exit_code == 0


def test_show_prints_a_readable_summary(imported: Path):
    """``fitlib show`` prints a ride by short id: when, device, figures and laps.

    Given: the interval ride, referred to by the first 6 characters of its id.
    Expect: its name, local start time (19:00 CEST), device, riding time, power, and a laps
    table with 12 laps.
    """
    listing = run(imported, "list", "--since", "2025-08-05", "--until", "2025-08-06")
    prefix = ride_ids(listing.output)[0][:6]

    result = run(imported, "show", prefix)

    assert "Garmin ride, 5 Aug 2025" in result.output
    assert "Tue 05 Aug 2025, 19:00" in result.output, "start time should be local (CEST)"
    assert "Garmin Edge 540" in result.output
    assert "187 W avg, 300 W max" in result.output
    assert "Laps" in result.output
    assert re.search(r"^\s*│?\s*12\s", result.output, flags=re.MULTILINE), "12 laps listed"
    assert result.exit_code == 0


def test_show_unknown_ride_is_an_error(imported: Path):
    """Asking for a ride that doesn't exist is an error.

    Given: an id prefix no ride has.
    Expect: "No ride matches" and exit code 2.
    """
    result = run(imported, "show", "ffffffff")

    assert "No ride matches 'ffffffff'" in result.output
    assert result.exit_code == EXIT_ERROR


def test_bad_config_is_an_error(tmp_path: Path):
    """A broken config file is reported instead of crashing.

    Given: a config naming an unknown store backend.
    Expect: the problem in the output and exit code 2.
    """
    config = tmp_path / "fitlib.toml"
    config.write_text('[store]\nbackend = "cloud"\n')

    result = run(config, "list")

    assert "Unknown store backend" in result.output
    assert result.exit_code == EXIT_ERROR
