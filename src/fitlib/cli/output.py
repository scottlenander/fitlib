"""Printing rides and import reports for the command line."""

from __future__ import annotations

from collections.abc import Iterable

from rich.table import Table

from fitlib import display
from fitlib.analysis.training import Training
from fitlib.cli.common import SHOWN_EFFORTS, out
from fitlib.importer import ImportReport
from fitlib.metrics import zones
from fitlib.metrics.curves import best_at
from fitlib.metrics.load import TssSource
from fitlib.metrics.zwift import zwift_world
from fitlib.models import (
    Bike,
    Ride,
    Units,
)


def print_report(report: ImportReport) -> None:
    """Print the counts from an import, then the skipped and failed files with reasons.

    Args:
        report: The import's outcome.
    """
    out.print(
        f"Imported {len(report.imported)}, already in library {len(report.duplicates)}, "
        f"skipped {len(report.skipped)}, failed {len(report.failed)}."
    )
    for title, rows in (("Skipped", report.skipped), ("Failed", report.failed)):
        if rows:
            table = Table(title=title, title_justify="left", show_header=False, box=None)
            for name, reason in rows:
                table.add_row(name, reason)
            out.print(table)


def print_ride(
    ride: Ride,
    figures: Training,
    units: Units,
    bike: Bike | None = None,
    default_zone: str | None = None,
) -> None:
    """Print a ride: name, when and where, main figures, training, zones, efforts and laps.

    Args:
        ride: The ride to print.
        figures: Its training figures.
        units: Units for distance, speed and height.
        bike: The ride's bike, if it has one.
        default_zone: The library's default time zone, for saying where the time came from.
    """
    r = ride.summary
    out.print(f"[bold]{ride.display_name}[/bold]  ({ride.short_id})")
    where = "indoor" if r.indoor else "outdoor"
    world = zwift_world(r)
    world_part = f" · {world.name}" if world else ""
    out.print(f"{display.start_time(r)} · {r.device or r.source.label}{world_part} · {where}")
    out.print(f"[dim]{display.time_zone_note(r, default_zone)}[/dim]")
    extras = []
    if bike is not None:
        extras.append(f"Bike: {bike.name}" + (" (default)" if ride.meta.bike_from_default else ""))
    if ride.meta.rpe is not None:
        extras.append(f"Effort: {ride.meta.rpe}/10")
    if extras:
        out.print(" · ".join(extras))
    out.print()

    avg_speed, max_speed = (
        display.speed(r.avg_speed_mps, units),
        display.speed(r.max_speed_mps, units),
    )
    facts = Table(show_header=False, box=None)
    facts.add_row("Riding time", display.duration(r.moving_s))
    facts.add_row("Elapsed time", display.duration(r.elapsed_s))
    facts.add_row("Distance", display.distance(r.distance_m, units))
    facts.add_row("Climbing", display.elevation(r.ascent_m, units))
    facts.add_row("Speed", f"{avg_speed} avg, {max_speed} max")
    facts.add_row("Power", f"{display.watts(r.avg_power)} avg, {display.watts(r.max_power)} max")
    facts.add_row("Heart rate", f"{display.bpm(r.avg_hr)} avg, {display.bpm(r.max_hr)} max")
    facts.add_row("Cadence", display.rpm(r.avg_cadence))
    out.print(facts)

    if r.has_power:
        print_training(ride, figures)
    elif figures.tss is not None:
        print_hr_training(figures)
    print_zones(figures)
    print_efforts(ride)
    print_laps(ride, units)

    if ride.meta.notes:
        out.print(f"\nNotes: {ride.meta.notes}")
    if ride.meta.tags:
        out.print(f"Tags: {', '.join(ride.meta.tags)}")
    out.print(f"\n[dim]Imported from {ride.source_name}[/dim]")


def section(title: str) -> None:
    """Print a blank line and a section title, on its own line so it never wraps into a table.

    Args:
        title: The section's title.
    """
    out.print()
    out.print(f"[bold]{title}[/bold]")


def tss_text(figures: Training) -> str:
    """Show a ride's TSS, marked " HR" when from heart rate and "*" when estimated.

    Args:
        figures: The ride's training figures.

    Returns:
        E.g. "112*" (estimated FTP), "48 HR", "52 HR*" (threshold from your rides or age).
    """
    if figures.tss is None:
        return display.tss(None)
    from_hr = figures.tss_source is TssSource.HEART_RATE
    estimated = figures.threshold_hr_estimated if from_hr else figures.ftp_estimated
    return display.tss(figures.tss) + (" HR" if from_hr else "") + ("*" if estimated else "")


def print_tss_notes(figures: Iterable[Training]) -> None:
    """Explain the marks ``tss_text`` used, if any were.

    Args:
        figures: The training figures of the rides shown.
    """
    shown = [f for f in figures if f.tss is not None]
    by_hr = [f for f in shown if f.tss_source is TssSource.HEART_RATE]
    if any(f.ftp_estimated for f in shown if f not in by_hr):
        out.print("* TSS from an estimated FTP (no FTP set for that date).")
    if by_hr:
        estimated = (
            " (* threshold heart rate not set: from your rides or your age)"
            if any(f.threshold_hr_estimated for f in by_hr)
            else ""
        )
        out.print(f"HR: TSS from heart rate, as the ride has no power{estimated}.")


def print_training(ride: Ride, figures: Training) -> None:
    """Print the Training block: NP, IF, TSS, VI, work, W/kg and decoupling.

    Args:
        ride: The ride.
        figures: Its FTP-based figures.
    """
    r = ride.summary
    if figures.ftp is None:
        ftp_note = "no FTP set or estimable"
    elif figures.ftp_estimated:
        ftp_note = f"estimated FTP {display.watts(figures.ftp)}"
    else:
        ftp_note = f"FTP {display.watts(figures.ftp)}"
    table = Table(show_header=False, box=None)
    table.add_row("Normalized Power", display.watts(r.np))
    table.add_row("Intensity Factor", display.ratio(figures.intensity_factor))
    table.add_row("TSS", display.tss(figures.tss))
    if figures.tss_source is TssSource.HEART_RATE:
        source = display.threshold_source(figures.threshold_hr_source)
        table.add_row("", f"from heart rate: threshold {display.bpm(figures.threshold_hr)}{source}")
    table.add_row("Variability Index", display.ratio(r.vi))
    table.add_row("Work", display.kilojoules(r.kj))
    if figures.weight_kg is not None:
        table.add_row(
            "W/kg",
            f"{display.watts_per_kg(figures.watts_per_kg)} avg, "
            f"{display.watts_per_kg(figures.np_per_kg)} NP",
        )
    table.add_row("Decoupling", display.signed_percent(r.decoupling_pct))
    section(f"Training ({ftp_note})")
    out.print(table)


def print_hr_training(figures: Training) -> None:
    """Print the Training block of a ride without power: its TSS from heart rate.

    Args:
        figures: Its training figures (with a heart-rate TSS).
    """
    source = display.threshold_source(figures.threshold_hr_source)
    table = Table(show_header=False, box=None)
    table.add_row("TSS", display.tss(figures.tss))
    table.add_row("Threshold heart rate", f"{display.bpm(figures.threshold_hr)}{source}")
    section("Training (from heart rate, no power)")
    out.print(table)


def print_zones(figures: Training) -> None:
    """Print time in each power and heart-rate zone, when they can be worked out.

    Args:
        figures: The ride's FTP-based figures.
    """
    for title, seconds, names in (
        ("Power zones", figures.power_zones, zones.POWER_ZONE_NAMES),
        ("Heart-rate zones", figures.hr_zones, zones.HR_ZONE_NAMES),
    ):
        if seconds is None:
            continue
        total = sum(seconds) or 1
        table = Table("Zone", "", "Time", "Share", box=None)
        for index, (name, secs) in enumerate(zip(names, seconds, strict=True), start=1):
            table.add_row(f"Z{index}", name, display.duration(secs), f"{secs / total:.0%}")
        section(title)
        out.print(table)


def print_efforts(ride: Ride) -> None:
    """Print the best power and heart rate over a few key durations.

    Args:
        ride: The ride.
    """
    r = ride.summary
    if not r.power_curve and not r.hr_curve:
        return
    table = Table("Best", "Power", "HR", box=None)
    for label, seconds in SHOWN_EFFORTS:
        power, hr = best_at(r.power_curve, seconds), best_at(r.hr_curve, seconds)
        if power is not None or hr is not None:
            table.add_row(label, display.watts(power), display.bpm(hr))
    section("Best efforts")
    out.print(table)


def print_laps(ride: Ride, units: Units) -> None:
    """Print the laps table for rides with more than one lap.

    Args:
        ride: The ride.
        units: Units for distance.
    """
    if len(ride.summary.laps) <= 1:
        return
    laps = Table("Lap", "Time", "Distance", "Power", "HR")
    for lap in ride.summary.laps:
        laps.add_row(
            str(lap.index + 1),
            display.duration(lap.elapsed_s),
            display.distance(lap.distance_m, units),
            display.watts(lap.avg_power),
            display.bpm(lap.avg_hr),
        )
    section("Laps")
    out.print(laps)
