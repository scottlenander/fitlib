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
    """Write a config file pointing at an empty library in a temp folder.

    Args:
        tmp_path: The test's temp folder.

    Returns:
        The config file's path.
    """
    path = tmp_path / "fitlib.toml"
    path.write_text(f'library = "{tmp_path / "library"}"\n')
    return path


def run(config: Path, *args: str):
    """Run ``fitlib`` with a config file.

    Args:
        config: The config file to pass as ``--config``.
        *args: The command and its arguments, e.g. ``"list", "--source", "zwift"``.

    Returns:
        The run's result: output and exit code.
    """
    return runner.invoke(app, ["--config", str(config), *args])


@pytest.fixture
def imported(config: Path) -> Path:
    """Import the fixture folder into the temp library.

    Args:
        config: The temp library's config file.

    Returns:
        The same config file, now pointing at a library with the fixtures imported.
    """
    run(config, "import", str(FIT_DIR), "--workers", "1")
    return config


def ride_ids(output: str) -> list[str]:
    """Pick out the ride ids printed at the start of ``fitlib list`` rows.

    Args:
        output: The command's output.

    Returns:
        The 8-character ids, in order.
    """
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
    """Find the id prefix of the ride that starts on a given day.

    Args:
        config: The library's config file.
        day: The day, ``YYYY-MM-DD``.
        next_day: The following day, ``YYYY-MM-DD``.

    Returns:
        The first 6 characters of that ride's id.
    """
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


# -- phase 1c: editing, bikes, tags ------------------------------------------------------------


def test_edit_one_ride_then_show_it(imported: Path):
    """``fitlib edit`` sets a ride's name, notes, effort, bike and tags; ``show`` prints them.

    Given: the bike "Giant Contend 1"; the 12 Aug ride edited with a name, notes, RPE 7, the
    bike by a lower-case prefix, and tags "Z2" and "Long Ride".
    Expect: the update confirmed; ``show`` prints the name, bike, effort, notes and the tags
    in stored (lower-case) form.
    """
    run(imported, "bikes", "add", "Giant Contend 1", "--kind", "road")
    prefix = ride_prefix(imported, "2025-08-12", "2025-08-13")

    edited = run(imported, "edit", prefix, "--name", "Arenberg evening", "--note",
                 "Windy on the cobbles", "--rpe", "7", "--bike", "giant c", "--tag", "Z2",
                 "--tag", "Long Ride")  # fmt: skip
    shown = run(imported, "show", prefix)

    assert "Updated 1 ride(s)." in edited.output
    assert "Arenberg evening" in shown.output
    assert "Bike: Giant Contend 1 · Effort: 7/10" in shown.output
    assert "Notes: Windy on the cobbles" in shown.output
    assert "Tags: long ride, z2" in shown.output, "tags are stored lower-case, sorted"


def test_edit_several_rides_and_clear_values(imported: Path):
    """Effort, bike and tags can be set on several rides at once, and cleared again.

    Given: two rides given RPE 6 and tag "z2" together; then the first has its RPE cleared and
    tag "z2" removed.
    Expect: both rides updated at first; afterwards ``list --tag z2`` finds only the second.
    """
    first = ride_prefix(imported, "2025-08-12", "2025-08-13")
    second = ride_prefix(imported, "2025-08-09", "2025-08-10")

    both = run(imported, "edit", first, second, "--rpe", "6", "--tag", "z2")
    run(imported, "edit", first, "--clear-rpe", "--untag", "z2")
    tagged = run(imported, "list", "--tag", "z2")

    assert "Updated 2 ride(s)." in both.output
    assert [i[:6] for i in ride_ids(tagged.output)] == [second], "only the second keeps z2"


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--name", "x"], "--name and --note can only be used with one ride."),
        (["--rpe", "5", "--clear-rpe"], "Give --rpe or --clear-rpe, not both."),
        ([], "Nothing to change."),
        (["--bike", "trek"], "No bike matches 'trek'. Bikes: none yet."),
        (["--tag", "a,b"], "Tags can't contain commas"),
    ],
    ids=["name-several", "set-and-clear", "nothing", "unknown-bike", "comma-tag"],
)
def test_edit_errors(imported: Path, args: list[str], message: str):
    """Mistakes in ``fitlib edit`` are reported without changing anything.

    Given: two rides (one ride for the last three cases) and the options shown.
    Expect: the message and exit code 2.
    """
    first = ride_prefix(imported, "2025-08-12", "2025-08-13")
    second = ride_prefix(imported, "2025-08-09", "2025-08-10")
    rides = [first, second] if args[:1] == ["--name"] else [first]

    result = run(imported, "edit", *rides, *args)

    assert message in result.output
    assert result.exit_code == EXIT_ERROR


def test_bikes_add_list_rename_retire(config: Path):
    """Bikes can be added (names with spaces quoted), listed, renamed and retired.

    Given: "Giant Contend 1" and "Kickr" added; a second "giant contend 1" attempted; the
    Giant renamed "Contend AR"; the Kickr retired.
    Expect: the duplicate refused; ``bikes list`` shows Contend AR only; ``--all`` also shows
    "Kickr (retired)".
    """
    run(config, "bikes", "add", "Giant Contend 1", "--kind", "road")
    run(config, "bikes", "add", "Kickr", "--kind", "trainer")
    duplicate = run(config, "bikes", "add", "giant contend 1")
    run(config, "bikes", "rename", "giant", "Contend AR")
    run(config, "bikes", "retire", "kickr")

    active = run(config, "bikes", "list")
    everything = run(config, "bikes", "list", "--all")

    assert duplicate.exit_code == EXIT_ERROR
    assert "There is already a bike called 'giant contend 1'." in duplicate.output
    assert "Contend AR" in active.output and "Kickr" not in active.output
    assert "Kickr (retired)" in everything.output


def test_default_bikes_on_import_and_backfill(config: Path):
    """Dated default bikes apply to new imports, and backfill fills in earlier imports.

    Given: the fixtures imported before any bikes exist; then Giant as outdoor default from
    1 Jan, Tarmac from 10 Aug, Kickr for Zwift; ``backfill --dry-run`` then ``backfill``.
    Expect: the dry run reports Giant 2, Kickr 1, Tarmac 4 without changing anything;
    ``bikes list`` then shows those counts; ``bikes defaults`` lists the timeline.
    """
    run(config, "import", str(FIT_DIR), "--workers", "1")
    run(config, "bikes", "add", "Giant Contend 1", "--default-for", "outdoor", "--from",
        "2025-01-01")  # fmt: skip
    run(config, "bikes", "add", "Tarmac SL7")
    run(config, "bikes", "default", "tarmac", "--for", "outdoor", "--from", "2025-08-10")
    run(config, "bikes", "add", "Kickr", "--default-for", "zwift", "--from", "2025-01-01")

    dry = run(config, "bikes", "backfill", "--dry-run")
    before = run(config, "bikes", "list")
    done = run(config, "bikes", "backfill")
    after = run(config, "bikes", "list")
    timeline = run(config, "bikes", "defaults")

    assert "Would set Giant Contend 1 on 2 ride(s)." in dry.output
    assert re.search(r"Tarmac SL7\s+–\s+0\s", before.output), "a dry run changes nothing"
    assert "Set Tarmac SL7 on 4 ride(s)." in done.output
    assert re.search(r"Giant Contend 1\s+–\s+2\s", after.output)
    assert re.search(r"Kickr\s+–\s+1\s", after.output)
    assert re.search(r"outdoor\s+2025-08-10\s+Tarmac SL7", timeline.output)


def test_bikes_default_errors_and_clear(config: Path):
    """``bikes default`` needs exactly one of a bike, ``--clear`` or ``--remove``.

    Given: the Kickr; a default with neither bike nor flag; a ``--clear`` entry; removing an
    entry that doesn't exist; then removing the ``--clear`` entry.
    Expect: an error for the first and third; the clear entry listed as "(none)"; removal
    confirmed.
    """
    run(config, "bikes", "add", "Kickr")

    neither = run(config, "bikes", "default", "--for", "indoor", "--from", "2025-01-01")
    cleared = run(config, "bikes", "default", "--clear", "--for", "indoor", "--from", "2025-01-01")
    listed = run(config, "bikes", "defaults")
    missing = run(config, "bikes", "default", "--remove", "--for", "zwift", "--from", "2025-01-01")
    removed = run(config, "bikes", "default", "--remove", "--for", "indoor", "--from", "2025-01-01")

    assert neither.exit_code == EXIT_ERROR
    assert "No default bike for indoor rides from 2025-01-01." in cleared.output
    assert re.search(r"indoor\s+2025-01-01\s+\(none\)", listed.output)
    assert missing.exit_code == EXIT_ERROR
    assert "Removed the indoor default from 2025-01-01." in removed.output


def test_tags_and_list_filters(imported: Path):
    """``fitlib tags`` counts tags; ``list`` filters by tag, bike, effort and bike name text.

    Given: the Giant on the 12 Aug ride with RPE 8 and tags race and z2; the 9 Aug ride with
    RPE 4 and tag z2.
    Expect: tags race 1, z2 2; ``--tag z2 --tag race`` and ``--min-rpe 6`` find 12 Aug;
    ``--max-rpe 5`` finds 9 Aug; ``--bike giant`` and the text "contend" find 12 Aug.
    """
    run(imported, "bikes", "add", "Giant Contend 1")
    aug12 = ride_prefix(imported, "2025-08-12", "2025-08-13")
    aug9 = ride_prefix(imported, "2025-08-09", "2025-08-10")
    run(imported, "edit", aug12, "--bike", "giant", "--rpe", "8", "--tag", "race", "--tag", "z2")
    run(imported, "edit", aug9, "--rpe", "4", "--tag", "z2")

    counts = run(imported, "tags")

    def found(*args: str) -> list[str]:
        """Id prefixes of the rides ``list`` shows with these options."""
        return [i[:6] for i in ride_ids(run(imported, "list", *args).output)]

    assert re.search(r"race\s+1", counts.output) and re.search(r"z2\s+2", counts.output)
    assert found("--tag", "z2", "--tag", "race") == [aug12]
    assert found("--min-rpe", "6") == [aug12]
    assert found("--max-rpe", "5") == [aug9]
    assert found("--bike", "giant") == [aug12]
    assert found("--text", "contend") == [aug12], "rides are found by their bike's name"
