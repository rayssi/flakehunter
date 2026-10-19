"""Readable summary printed in the GitLab job log."""

from __future__ import annotations

from . import __version__
from .analysis import FAILURE, RETRY, SUCCESS, Report, TestStats
from .formatting import (
    fmt_day,
    fmt_percent,
    fmt_score,
    fmt_seconds,
    plural,
    run_label,
    summary_sentence,
)

SYMBOLS = {SUCCESS: "✓", FAILURE: "✗", RETRY: "↻"}
STRIP_LENGTH = 20
NAME_WIDTH = 60

BOLD, RED, YELLOW, BLUE, DIM = "1", "31", "33", "34", "2"


class Style:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def __call__(self, text: str, code: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text


def _strip(test: TestStats) -> str:
    return "".join(SYMBOLS[cell.symbol] for cell in test.cells[-STRIP_LENGTH:])


def _name(test: TestStats, width: int) -> str:
    name = test.name
    if len(name) > width:
        name = name[: width - 3] + "..."
    return name.ljust(width)


def _more(lines: list[str], total: int, shown: int) -> None:
    if total > shown:
        lines.append(f"  ... and {total - shown} more, see the full report")


def render_console(report: Report, top: int = 10, color: bool = False, report_path: str | None = None) -> str:
    st = Style(color)
    counts = report.counts()
    start, end = report.period
    lines: list[str] = []

    lines.append(st(f"FlakeHunter {__version__}", BOLD))
    env = f"Environment {report.env}, " if report.env else ""
    lines.append(
        f"{env}{plural(len(report.runs), 'run', 'runs')} from {fmt_day(start)} to {fmt_day(end)}, "
        f"{plural(counts['tests'], 'test', 'tests')}"
    )
    lines.append("")
    sentence = summary_sentence(
        counts["broken"], counts["always_failing"], counts["flaky"], counts["slowdowns"], counts["watch"]
    )
    lines.append(st(f"Summary: {sentence}.", BOLD))

    if report.broken:
        lines += ["", st(f"Broken tests ({len(report.broken)})", RED)]
        for t in report.broken[:top]:
            since = t.since
            detail = (
                f"failing on the last {t.failing_streak} runs, "
                f"since {run_label(since.pipeline_id, since.run_name)} ({fmt_day(since.day)})"
            )
            if t.was_flaky:
                detail += ", it was already flaky before"
            lines.append(f"  {t.name}")
            lines.append(st(f"      {detail}", DIM))
            if t.last_error:
                lines.append(st(f"      error: {t.last_error}", DIM))
        _more(lines, len(report.broken), top)

    if report.always_failing:
        lines += ["", st(f"Always failing ({len(report.always_failing)})", RED)]
        for t in report.always_failing[:top]:
            since = t.since
            lines.append(f"  {t.name}")
            lines.append(
                st(
                    f"      failing on every run ({plural(t.runs, 'run', 'runs')}), "
                    f"since {run_label(since.pipeline_id, since.run_name)} ({fmt_day(since.day)})",
                    DIM,
                )
            )
            if t.last_error:
                lines.append(st(f"      error: {t.last_error}", DIM))
        _more(lines, len(report.always_failing), top)

    if report.flaky:
        width = min(max(len(t.name) for t in report.flaky[:top]), NAME_WIDTH)
        lines += ["", st(f"Flaky tests ({len(report.flaky)})", YELLOW)]
        lines.append(st(f"  {'score':>5}  {'flips':>5}  {'retries':>7}  {'test'.ljust(width)}  history", DIM))
        for t in report.flaky[:top]:
            lines.append(
                f"  {fmt_score(t.flakiness):>5}  {t.flips:>5}  {t.passed_on_retry:>7}  {_name(t, width)}  {_strip(t)}"
            )
        _more(lines, len(report.flaky), top)

    if report.slowdowns:
        width = min(max(len(sd.test.name) for sd in report.slowdowns[:top]), NAME_WIDTH)
        days = report.settings.recent_days
        lines += ["", st(f"Slowdowns over the last {days} days ({len(report.slowdowns)})", BLUE)]
        for sd in report.slowdowns[:top]:
            lines.append(
                f"  {fmt_percent(sd.ratio, signed=True):>6}  {_name(sd.test, width)}  "
                f"median {fmt_seconds(sd.recent_median)} (was {fmt_seconds(sd.previous_median)})"
            )
        _more(lines, len(report.slowdowns), top)

    if report.watch:
        width = min(max(len(t.name) for t in report.watch[:5]), NAME_WIDTH)
        lines += ["", st(f"Watch list ({len(report.watch)})", DIM)]
        for t in report.watch[:5]:
            problems = []
            if t.failures:
                problems.append(plural(t.failures, "failure", "failures"))
            if t.passed_on_retry:
                problems.append(f"{t.passed_on_retry} passed on retry")
            lines.append(f"  {_name(t, width)}  {', '.join(problems)} in {plural(t.runs, 'run', 'runs')}")
        _more(lines, len(report.watch), 5)

    change = report.suite_change
    if change:
        last, previous, ratio = change
        lines += ["", st("Suite duration", BOLD)]
        lines.append(
            f"  last run: {fmt_seconds(last)}, median of previous runs: {fmt_seconds(previous)} "
            f"({fmt_percent(ratio, signed=True)})"
        )

    lines.append("")
    if report.flaky:
        lines.append(st("History: ✓ passed, ✗ failed, ↻ passed on retry (oldest to newest)", DIM))
    if report_path:
        lines.append(f"Full report: {report_path}")
    return "\n".join(lines)
