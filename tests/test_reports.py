from flakehunter.analysis import analyze
from flakehunter.console import render_console
from flakehunter.formatting import fmt_day, fmt_percent, fmt_seconds, summary_sentence
from flakehunter.html_report import render_html
from flakehunter.loader import Attempt
from helpers import make_runs


def test_html_report_escapes_test_names_and_errors():
    runs = make_runs({"t": "PPPFFF"})
    for run in runs:
        for attempt in run.attempts:
            attempt.name = "<script>alert('name')</script>"
            attempt.message = "<img src=x onerror=alert(1)>"
    html = render_html(analyze(runs))
    assert "<script>alert(" not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;" in html


def test_html_report_is_self_contained():
    html = render_html(analyze(make_runs({"a": "PPPFFF", "b": "PFPFPF"})))
    assert html.startswith("<!doctype html>")
    assert "http://" not in html
    assert "https://" not in html
    assert "prefers-color-scheme: dark" in html  # styles are embedded
    assert "Fix first" in html


def test_console_lists_each_section():
    text = render_console(analyze(make_runs({"a": "PPPFFF", "b": "PFPFPF", "c": "PPPPFP"})))
    assert "Broken tests (1)" in text
    assert "Flaky tests (1)" in text
    assert "Watch list (1)" in text
    assert "\x1b[" not in text  # no colors unless asked


def test_console_colors_when_asked():
    text = render_console(analyze(make_runs({"a": "PPPFFF"})), color=True)
    assert "\x1b[" in text


def test_console_all_clear():
    text = render_console(analyze(make_runs({"a": "PPPP"})))
    assert "All clear" in text


def test_formatting_helpers():
    assert fmt_seconds(12.34) == "12.3s"
    assert fmt_seconds(245) == "4m 05s"
    assert fmt_seconds(3725) == "1h 02m"
    assert fmt_percent(0.354, signed=True) == "+35%"
    assert fmt_day("2026-10-13") == "13 Oct 2026"
    assert fmt_day("not a date") == "not a date"


def test_summary_sentence():
    assert summary_sentence(1, 0, 3, 0, 0) == "1 broken test and 3 flaky tests"
    assert summary_sentence(0, 0, 0, 0, 2) == "No major issue, 2 tests to watch"
    assert summary_sentence(2, 1, 1, 1, 0) == "2 broken tests, 1 test always failing, 1 flaky test and 1 slowdown"


def test_attempt_duration_is_never_negative():
    assert Attempt("i", "n", "f", "passed", start=2_000, stop=1_000).duration == 0


def test_console_and_html_show_always_failing_and_slowdowns():
    from flakehunter.analysis import Settings

    runs = make_runs({"new": "-------FFF", "slow": "PPPPPPPPPP"})
    for run in runs[-3:]:
        for attempt in run.attempts:
            if attempt.name == "slow":
                attempt.stop = attempt.start + 12_000
    report = analyze(runs, Settings(recent_days=3))
    text = render_console(report)
    assert "Always failing (1)" in text
    assert "Slowdowns over the last 3 days (1)" in text
    assert "(was 5.0s)" in text
    html = render_html(report)
    assert "Failing on every run since it was added" in html
    assert "Median before" in html
