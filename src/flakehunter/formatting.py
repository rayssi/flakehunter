"""Formatting of numbers, durations and dates."""

from __future__ import annotations

from datetime import date, datetime

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fmt_seconds(seconds: float) -> str:
    """12.3s, 4m 05s or 1h 02m."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(round(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def fmt_percent(ratio: float, signed: bool = False, decimals: int = 0) -> str:
    value = ratio * 100
    return (f"{value:+.{decimals}f}" if signed else f"{value:.{decimals}f}") + "%"


def fmt_score(value: float) -> str:
    return f"{value:.2f}"


def fmt_day(iso_day: str) -> str:
    """2026-10-13 becomes 13 Oct 2026 (unambiguous in every locale)."""
    try:
        day = date.fromisoformat(iso_day)
    except ValueError:
        return iso_day
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"


def fmt_datetime(moment: datetime) -> str:
    return f"{fmt_day(moment.date().isoformat())} at {moment:%H:%M} UTC"


def plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def run_label(pipeline_id: int | None, run_name: str) -> str:
    return f"pipeline #{pipeline_id}" if pipeline_id is not None else f"run {run_name}"


def join_en(parts: list[str]) -> str:
    """["a", "b", "c"] becomes "a, b and c"."""
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def summary_sentence(broken: int, always_failing: int, flaky: int, slowdowns: int, watch: int) -> str:
    parts = []
    if broken:
        parts.append(plural(broken, "broken test", "broken tests"))
    if always_failing:
        parts.append(plural(always_failing, "test always failing", "tests always failing"))
    if flaky:
        parts.append(plural(flaky, "flaky test", "flaky tests"))
    if slowdowns:
        parts.append(plural(slowdowns, "slowdown", "slowdowns"))
    if not parts:
        if watch:
            return f"No major issue, {plural(watch, 'test', 'tests')} to watch"
        return "All clear: no broken, flaky or slower tests"
    sentence = join_en(parts)
    return sentence[0].upper() + sentence[1:]
