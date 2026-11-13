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


# -- phase 1b: training, athlete, units, recompute --------------------------------------------


def ride_prefix(config: Path, day: str, next_day: str) -> str:
    listing = run(config, "list", "--since", day, "--until", next_day)
    return ride_ids(listing.output)[0][:6]


def test_athlete_set_show_and_remove(config: Path):
    """``fitlib athlete`` records dated values, shows them in display units, and removes them.

    Given: an empty library; ``set --from 2025-08-10 --ftp 250 --weight 165 --max-hr 190``
    (imperial, so 165 lb); then ``show``; then ``remove 2025-08-10``.
    Expect: the entry listed with 165.0 lb; ``--units metric`` shows 74.8 kg; after removing,
    no history.
    """
    saved = run(config, "athlete", "set", "--from", "2025-08-10", "--ftp", "250",
                "--weight", "165", "--max-hr", "190")  # fmt: skip
    shown = run(config, "athlete", "show")
    metric = run(config, "athlete", "show", "--units", "metric")
    removed = run(config, "athlete", "remove", "2025-08-10")
    empty = run(config, "athlete", "show")

    assert "Saved athlete values from 2025-08-10." in saved.output
    assert re.search(r"2025-08-10\s+250 W\s+165.0 lb\s+190 bpm", shown.output)
    assert "74.8 kg" in metric.output, "weight is stored in kg and shown in metric on request"
    assert removed.exit_code == 0
    assert "No athlete history yet." in empty.output


def test_athlete_set_needs_a_value_and_remove_needs_an_entry(config: Path):
    """Setting nothing, or removing a date with no entry, is an error.

    Given: ``athlete set --from 2025-08-10`` with no values; ``athlete remove 2025-01-01``
    on an empty history.
    Expect: an error and exit code 2 for both.
    """
    nothing = run(config, "athlete", "set", "--from", "2025-08-10")
    missing = run(config, "athlete", "remove", "2025-01-01")

    assert "Give at least one of" in nothing.output
    assert nothing.exit_code == EXIT_ERROR
    assert "No athlete entry on 2025-01-01." in missing.output
    assert missing.exit_code == EXIT_ERROR


def test_show_prints_training_zones_and_best_efforts(imported: Path):
    """``fitlib show`` adds training figures, zones and best efforts once an FTP is set.

    Given: FTP 250 W, 165 lb and max HR 190 from 10 Aug; the 12 Aug ride (30 min, 180 W).
    Expect: "Training (FTP 250 W)", NP 180 W, IF 0.72, TSS 26, W/kg, power and heart-rate
    zone tables, and best efforts.
    """
    run(imported, "athlete", "set", "--from", "2025-08-10", "--ftp", "250", "--weight", "165",
        "--max-hr", "190")  # fmt: skip

    result = run(imported, "show", ride_prefix(imported, "2025-08-12", "2025-08-13"))

    assert "Training (FTP 250 W)" in result.output
    assert re.search(r"Normalized Power\s+180 W", result.output)
    assert re.search(r"Intensity Factor\s+0.72", result.output)
    assert re.search(r"TSS\s+26\b", result.output)
    assert "W/kg" in result.output
    assert "Power zones" in result.output and "Heart-rate zones" in result.output
    assert re.search(r"20 min\s+180 W", result.output), "best 20 min should be 180 W"


def test_show_marks_an_estimated_ftp(imported: Path):
    """Without an FTP for the ride's date, ``show`` says the FTP is estimated.

    Given: no athlete history; the 2 Aug Zwift ride (60 min at 200 W).
    Expect: "Training (estimated FTP 190 W)" and TSS 111; no W/kg row (no weight set).
    """
    result = run(imported, "show", ride_prefix(imported, "2025-08-02", "2025-08-03"))

    assert "Training (estimated FTP 190 W)" in result.output
    assert re.search(r"TSS\s+111\b", result.output)
    assert "W/kg" not in result.output, "without a weight there is no W/kg"


@pytest.mark.parametrize(
    ("units", "distance", "climbing"),
    [(None, "10.0 mi", "222 ft"), ("metric", "16.1 km", "68 m")],
    ids=["imperial-default", "metric"],
)
def test_show_units(imported: Path, units: str | None, distance: str, climbing: str):
    """Distances and climbing are imperial by default and metric with ``--units metric``.

    Given: the 12 Aug ride (16.1 km, 68 m of climbing).
    Expect: 10.0 mi and 222 ft (67.7 m) by default; 16.1 km and 68 m in metric.
    """
    args = ["--units", units] if units else []

    result = run(imported, "show", ride_prefix(imported, "2025-08-12", "2025-08-13"), *args)

    assert re.search(rf"Distance\s+{distance}", result.output)
    assert re.search(rf"Climbing\s+{climbing}", result.output)


def test_list_shows_tss_and_marks_estimates(imported: Path):
    """``fitlib list`` has a TSS column; TSS from an estimated FTP is starred and explained.

    Given: FTP 250 from 10 Aug; the 12 Aug ride (TSS 26) and the 2 Aug ride (estimated, 111).
    Expect: "26" unstarred, "111*" starred, and the footnote.
    """
    run(imported, "athlete", "set", "--from", "2025-08-10", "--ftp", "250")

    result = run(imported, "list")

    assert re.search(r"2025-08-12 .* 26 ", result.output), "set FTP: plain TSS"
    assert re.search(r"2025-08-02 .* 111\* ", result.output), "estimated FTP: starred TSS"
    assert "* TSS from an estimated FTP" in result.output


def test_recompute_when_up_to_date_and_for_one_ride(imported: Path):
    """``fitlib recompute`` does nothing when every ride is current, and can redo one ride.

    Given: a freshly imported library.
    Expect: "Every ride is up to date." with no arguments; "Recomputed 1, failed 0." for one
    ride by prefix; an error (exit 2) for an unknown prefix.
    """
    nothing = run(imported, "recompute")
    one = run(imported, "recompute", ride_prefix(imported, "2025-08-12", "2025-08-13"))
    unknown = run(imported, "recompute", "ffffffff")

    assert "Every ride is up to date." in nothing.output
    assert "Recomputed 1, failed 0." in one.output
    assert unknown.exit_code == EXIT_ERROR
