"""Self-contained HTML report: a single file, no external resources.

It opens offline, from GitLab artifacts or locally.
"""

from __future__ import annotations

from functools import cache
from html import escape
from importlib.resources import files

from . import __version__
from .analysis import (
    ALWAYS_FAILING,
    BROKEN,
    CATEGORY_LABELS,
    FAILURE,
    FLAKY,
    INACTIVE,
    RETRY,
    STABLE,
    SUCCESS,
    WATCH,
    Report,
    TestStats,
)
from .formatting import (
    fmt_datetime,
    fmt_day,
    fmt_percent,
    fmt_score,
    fmt_seconds,
    plural,
    run_label,
    summary_sentence,
)

STRIP_MAX = 30
CELL_LABELS = {SUCCESS: "passed", FAILURE: "failed", RETRY: "passed on retry"}

_ASSETS = files("flakehunter") / "assets"


@cache
def _asset(name: str) -> str:
    """Read a bundled asset (CSS or JS) shipped inside the package."""
    return (_ASSETS / name).read_text(encoding="utf-8")


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def _strip(test: TestStats) -> str:
    cells = test.cells[-STRIP_MAX:]
    counts = {symbol: sum(1 for c in cells if c.symbol == symbol) for symbol in (SUCCESS, FAILURE, RETRY)}
    label = (
        f"last {len(cells)} runs: {counts[SUCCESS]} passed, {counts[FAILURE]} failed, {counts[RETRY]} passed on retry"
    )
    spans = "".join(
        f'<span class="cell cell-{c.symbol}" title="{_e(CELL_LABELS[c.symbol])}, '
        f'{_e(run_label(c.pipeline_id, c.run_name))}, {_e(fmt_day(c.day))}"></span>'
        for c in cells
    )
    return f'<span class="strip" role="img" aria-label="{_e(label)}">{spans}</span>'


def _test_cell(test: TestStats, extra: str = "") -> str:
    full = f'<span class="full-name">{_e(test.full_name)}</span>' if test.full_name else ""
    return f'<td class="test">{_e(test.name)}{full}{extra}</td>'


def _legend() -> str:
    return (
        '<p class="legend"><span class="l-P">Passed</span><span class="l-F">Failed</span>'
        '<span class="l-R">Passed on retry</span><span>Oldest to newest</span></p>'
    )


def _section(title: str, count: int, lead: str, body: str, empty: str, anchor: str) -> str:
    content = body if count else f'<p class="empty">{_e(empty)}</p>'
    lead_html = f'<p class="lead">{_e(lead)}</p>' if count and lead else ""
    return (
        f'<section id="{anchor}" aria-labelledby="{anchor}-title">'
        f'<h2 id="{anchor}-title">{_e(title)}<span class="count">{count}</span></h2>'
        f"{lead_html}{content}</section>"
    )


def _priority_rows(report: Report) -> str:
    rows = []
    always_failing = report.always_failing
    for t in report.broken + always_failing:
        since = t.since
        where = f"{run_label(since.pipeline_id, since.run_name)}, {fmt_day(since.day)}"
        if t in always_failing:
            detail = f"Failing on every run since it was added ({where})."
        else:
            detail = f"Failing on the last {t.failing_streak} runs, since {where}."
            if t.was_flaky:
                detail += " It was already flaky before."
        error = f'<span class="error">{_e(t.last_error)}</span>' if t.last_error else ""
        extra = f'<span class="detail">{_e(detail)}</span>{error}'
        rows.append(f"<tr>{_test_cell(t, extra)}<td>{_strip(t)}</td></tr>")
    if not rows:
        return ""
    return (
        _legend() + '<div class="scroll"><table><thead><tr><th scope="col">Test</th>'
        '<th scope="col">History</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>"
    )


def _flaky_rows(report: Report) -> str:
    if not report.flaky:
        return ""
    rows = "".join(
        f"<tr>{_test_cell(t)}"
        f'<td class="num">{fmt_score(t.flakiness)}</td>'
        f'<td class="num">{t.flips}</td>'
        f'<td class="num">{t.passed_on_retry}</td>'
        f'<td class="num">{fmt_percent(t.failure_rate, decimals=1)}</td>'
        f"<td>{_strip(t)}</td></tr>"
        for t in report.flaky
    )
    return (
        _legend() + '<div class="scroll"><table><thead><tr><th scope="col">Test</th>'
        '<th scope="col" class="num">Flakiness</th><th scope="col" class="num">Flips</th>'
        '<th scope="col" class="num">Passed on retry</th><th scope="col" class="num">Failure rate</th>'
        '<th scope="col">History</th></tr></thead><tbody>' + rows + "</tbody></table></div>"
    )


def _slowdown_rows(report: Report) -> str:
    if not report.slowdowns:
        return ""
    rows = "".join(
        f"<tr>{_test_cell(sd.test)}"
        f'<td class="num up">{fmt_percent(sd.ratio, signed=True)}</td>'
        f'<td class="num">{fmt_seconds(sd.recent_median)}</td>'
        f'<td class="num">{fmt_seconds(sd.previous_median)}</td></tr>'
        for sd in report.slowdowns
    )
    return (
        '<div class="scroll"><table><thead><tr><th scope="col">Test</th>'
        '<th scope="col" class="num">Change</th>'
        f'<th scope="col" class="num">Median, last {report.settings.recent_days} days</th>'
        '<th scope="col" class="num">Median before</th></tr></thead><tbody>' + rows + "</tbody></table></div>"
    )


def _watch_rows(report: Report) -> str:
    if not report.watch:
        return ""
    rows = "".join(
        f"<tr>{_test_cell(t)}"
        f'<td class="num">{t.failures}</td><td class="num">{t.passed_on_retry}</td>'
        f'<td class="num">{t.runs}</td><td>{_strip(t)}</td></tr>'
        for t in report.watch
    )
    return (
        '<div class="scroll"><table><thead><tr><th scope="col">Test</th>'
        '<th scope="col" class="num">Failures</th><th scope="col" class="num">Passed on retry</th>'
        '<th scope="col" class="num">Runs</th><th scope="col">History</th></tr></thead><tbody>'
        + rows
        + "</tbody></table></div>"
    )


def _suite_chart(report: Report) -> str:
    runs = report.runs
    if len(runs) < 2:
        return '<p class="empty">At least two runs are needed to track the suite duration.</p>'
    peak = max(run.wall_time for run in runs) or 1
    bar_w, gap, height = 8, 4, 100
    width = len(runs) * (bar_w + gap) - gap
    bars = []
    for i, run in enumerate(runs):
        h = max(run.wall_time / peak * height, 1.5)
        css = "bar bar-last" if i == len(runs) - 1 else "bar"
        tip = f"{run_label(run.pipeline_id, run.name)}, {fmt_day(run.day)} : {fmt_seconds(run.wall_time)}"
        bars.append(
            f'<rect class="{css}" x="{i * (bar_w + gap)}" y="{height - h:.1f}" width="{bar_w}" '
            f'height="{h:.1f}" rx="1.5"><title>{_e(tip)}</title></rect>'
        )
    change = report.suite_change
    note = ""
    if change:
        last, previous, ratio = change
        note = (
            f'<p class="lead" style="margin-top:12px">Last run: {fmt_seconds(last)}. '
            f"Median of previous runs: {fmt_seconds(previous)} ({fmt_percent(ratio, signed=True)}).</p>"
        )
    start, end = report.period
    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" preserveAspectRatio="none" role="img" '
        f'aria-label="Duration of each run, newest on the right">{"".join(bars)}</svg>'
        f'<div class="chart-scale"><span>{_e(fmt_day(start))}</span>'
        f"<span>Highest: {fmt_seconds(peak)}</span><span>{_e(fmt_day(end))}</span></div>{note}"
    )


def _sortable_header(columns: list[tuple[str, bool]]) -> str:
    num_class = ' class="num"'
    cells = "".join(
        f'<th scope="col"{num_class if numeric else ""}><button type="button">{_e(label)}</button></th>'
        for label, numeric in columns
    )
    return f"<thead><tr>{cells}</tr></thead>"


CATEGORY_ORDER = {BROKEN: 0, ALWAYS_FAILING: 1, FLAKY: 2, WATCH: 3, STABLE: 4, INACTIVE: 5}


def _all_tests(report: Report) -> str:
    # Problems first, then stable tests, then tests that are no longer run.
    tests = sorted(report.tests, key=lambda t: (CATEGORY_ORDER[t.category], -t.flakiness, t.name.lower()))
    reliability_rows = "".join(
        f'<tr data-name="{_e(t.name.lower())}">{_test_cell(t)}'
        f'<td data-v="{_e(CATEGORY_LABELS[t.category])}"><span class="cat cat-{t.category}">'
        f"{_e(CATEGORY_LABELS[t.category])}</span></td>"
        f'<td class="num" data-v="{t.runs}">{t.runs}</td>'
        f'<td class="num" data-v="{t.failures}">{t.failures}</td>'
        f'<td class="num" data-v="{t.failure_rate:.6f}">{fmt_percent(t.failure_rate, decimals=1)}</td>'
        f'<td class="num" data-v="{t.passed_on_retry}">{t.passed_on_retry}</td>'
        f'<td class="num" data-v="{t.flips}">{t.flips}</td>'
        f'<td class="num" data-v="{t.flakiness:.6f}">{fmt_score(t.flakiness)}</td></tr>'
        for t in tests
    )

    def duration_cells(t: TestStats) -> str:
        d = t.durations
        if d is None:
            missing = '<td class="num" data-v="-1">&ndash;</td>'
            return '<td class="num" data-v="0">0</td>' + missing * 8
        values = [d.min, d.q1, d.median, d.avg, d.q3, d.max]
        cells = "".join(f'<td class="num" data-v="{v:.4f}">{fmt_seconds(v)}</td>' for v in values)
        spread = f'<td class="num" data-v="{d.spread:.6f}">{fmt_percent(d.spread, decimals=1)}</td>'
        trend = t.slowdown
        trend_cell = (
            f'<td class="num" data-v="{trend:.6f}">{fmt_percent(trend, signed=True)}</td>'
            if trend is not None
            else '<td class="num" data-v="-99">&ndash;</td>'
        )
        return f'<td class="num" data-v="{d.count}">{d.count}</td>{cells}{spread}{trend_cell}'

    with_durations = sorted(tests, key=lambda t: (-(t.durations.median if t.durations else -1), t.name))
    duration_rows = "".join(
        f'<tr data-name="{_e(t.name.lower())}">{_test_cell(t)}{duration_cells(t)}</tr>' for t in with_durations
    )
    band = report.settings.band
    reliability_header = _sortable_header(
        [
            ("Test", False),
            ("Category", False),
            ("Runs", True),
            ("Failures", True),
            ("Failure rate", True),
            ("Passed on retry", True),
            ("Flips", True),
            ("Flakiness", True),
        ]
    )
    duration_header = _sortable_header(
        [
            ("Test", False),
            ("Passes", True),
            ("Min", True),
            ("Q1", True),
            ("Median", True),
            ("Avg", True),
            ("Q3", True),
            ("Max", True),
            (f"Spread P{band}-{100 - band}", True),
            (f"Change {report.settings.recent_days}d", True),
        ]
    )
    return (
        '<section id="all" aria-labelledby="all-title">'
        f'<h2 id="all-title">All tests<span class="count">{len(tests)}</span></h2>'
        '<p class="lead">Click a column header to sort.</p>'
        '<div class="filter"><label for="filter">Filter by name</label>'
        '<input id="filter" type="search" autocomplete="off" placeholder="e.g. login"></div>'
        "<h3>Reliability</h3>"
        f'<div class="scroll"><table class="sortable">{reliability_header}'
        f"<tbody>{reliability_rows}</tbody></table></div>"
        "<h3>Durations of passing runs</h3>"
        f'<div class="scroll"><table class="sortable">{duration_header}<tbody>{duration_rows}</tbody></table></div>'
        "</section>"
    )


def _method(report: Report) -> str:
    s = report.settings
    return (
        "<details><summary>How scores are computed</summary>"
        "<p>Every attempt of a test is put in a row, retries included. Flakiness is the number of flips "
        "(passed to failed, or the other way round) divided by the number of attempts minus one. "
        "A flaky test flips often; a broken test flips once, then keeps failing.</p>"
        f"<p>A test is broken when it fails on at least {s.broken_streak} consecutive runs, up to the latest one. "
        f"It is flaky with at least {s.min_flips} flips, or at least two passes obtained only on retry. "
        "It goes on the watch list if it failed without matching those rules.</p>"
        f"<p>A slowdown compares the median of the last {s.recent_days} days with the median before, on passing "
        f"executions only. It is reported from {fmt_percent(s.slowdown_threshold, signed=True)} and "
        f"{fmt_seconds(s.min_slowdown_seconds)} more. A test missing from the last {s.active_runs} runs is "
        "considered inactive and is left out of the lists.</p>"
        "</details>"
    )


def render_html(report: Report) -> str:
    counts = report.counts()
    sentence = summary_sentence(
        counts["broken"], counts["always_failing"], counts["flaky"], counts["slowdowns"], counts["watch"]
    )
    start, end = report.period
    env = report.env or "not set"
    title = f"FlakeHunter, {report.env}" if report.env else "FlakeHunter"
    period = (
        f"{plural(len(report.runs), 'run', 'runs')} analyzed from {fmt_day(start)} to {fmt_day(end)}, "
        f"{plural(counts['tests'], 'test', 'tests')}. Generated on {fmt_datetime(report.generated_at)}."
    )
    priority_count = counts["broken"] + counts["always_failing"]
    sections = [
        _section(
            "Fix first",
            priority_count,
            "These tests have failed on every run for a while: they are most likely real bugs, not flakiness.",
            _priority_rows(report),
            "No broken tests in this period.",
            "fix-first",
        ),
        _section(
            "Flaky tests",
            counts["flaky"],
            "These tests change result for no apparent reason. Sorted from most to least flaky.",
            _flaky_rows(report),
            "No flaky tests in this period.",
            "flaky",
        ),
        _section(
            "Slowdowns",
            counts["slowdowns"],
            "",
            _slowdown_rows(report),
            "No notable slowdown.",
            "slowdowns",
        ),
        _section(
            "Watch list",
            counts["watch"],
            "A few failures or passes on retry, not enough to draw a conclusion.",
            _watch_rows(report),
            "Nothing to watch.",
            "watch",
        ),
    ]
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(title)}</title><style>{_asset('report.css')}</style></head><body><main>"
        f'<header><p class="context">FlakeHunter, {_e(env)} environment</p>'
        f'<h1>{_e(sentence)}.</h1><p class="period">{_e(period)}</p></header>'
        '<section aria-labelledby="duration-title"><h2 id="duration-title">Suite duration, run by run</h2>'
        f"{_suite_chart(report)}</section>"
        + "".join(sections)
        + _all_tests(report)
        + _method(report)
        + f"<footer>FlakeHunter {__version__}</footer></main><script>{_asset('report.js')}</script></body></html>"
    )
