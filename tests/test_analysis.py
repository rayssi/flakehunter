from flakehunter.analysis import (
    ALWAYS_FAILING,
    BROKEN,
    FLAKY,
    INACTIVE,
    STABLE,
    WATCH,
    Settings,
    analyze,
    count_flips,
    percentile,
)
from helpers import DAY_MS, make_runs


def categories(histories: dict[str, str], **settings: int) -> dict[str, str]:
    report = analyze(make_runs(histories), Settings(**settings))
    return {t.name: t.category for t in report.tests}


def test_regression_is_not_flaky():
    # Same number of failures, but the order changes everything.
    result = categories({"regression": "PPPPPPFFFF", "flaky": "PFPFPPFPFP"})
    assert result["regression"] == BROKEN
    assert result["flaky"] == FLAKY


def test_always_failing_and_stable():
    result = categories({"new_broken": "-------FFF", "ok": "PPPPPPPPPP"})
    assert result["new_broken"] == ALWAYS_FAILING
    assert result["ok"] == STABLE


def test_passes_on_retry_are_flaky():
    test = analyze(make_runs({"retry": "PPRPPRPPPP"})).tests[0]
    assert test.passed_on_retry == 2
    assert test.failures == 0
    assert test.category == FLAKY


def test_isolated_failure_goes_on_the_watch_list():
    assert categories({"once": "PPPPFPPPPP"})["once"] == WATCH


def test_fixed_bug_is_watched_not_flaky():
    assert categories({"fixed": "PPFFFFPPPP"})["fixed"] == WATCH


def test_tests_missing_from_recent_runs_are_inactive():
    result = categories({"deleted": "PFPFPF----", "ok": "PPPPPPPPPP"})
    assert result["deleted"] == INACTIVE


def test_thresholds_are_configurable():
    assert categories({"t": "PPPPPPPFF"})["t"] == WATCH
    assert categories({"t": "PPPPPPPFF"}, broken_streak=2)["t"] == BROKEN


def test_broken_since_points_to_the_first_failing_run():
    test = analyze(make_runs({"regression": "PPPPPPFFFF"})).tests[0]
    assert test.since.pipeline_id == 1006
    assert test.failing_streak == 4


def test_broken_test_remembers_it_was_flaky_before():
    test = analyze(make_runs({"t": "PFPFPFPFFF"})).tests[0]
    assert test.category == BROKEN
    assert test.was_flaky


def test_flakiness_score():
    test = analyze(make_runs({"t": "PFPF"})).tests[0]
    assert test.flips == 3
    assert test.flakiness == 1.0


def test_count_flips():
    assert count_flips([]) == 0
    assert count_flips(["P", "P", "F", "F", "P"]) == 2


def test_percentile_uses_linear_interpolation():
    data = [1.0, 2.0, 3.0, 4.0]
    assert percentile(data, 50) == 2.5
    assert percentile(data, 25) == 1.75
    assert percentile([7.0], 90) == 7.0


def test_slowdown_is_detected_on_recent_runs_only():
    runs = make_runs({"slow": "P" * 10, "steady": "P" * 10})
    for run in runs[-3:]:  # the last 3 days: "slow" takes twice as long
        for attempt in run.attempts:
            if attempt.name == "slow":
                attempt.stop = attempt.start + 10_000
    report = analyze(runs, Settings(recent_days=3))
    assert [sd.test.name for sd in report.slowdowns] == ["slow"]
    assert report.slowdowns[0].ratio > 0.9


def test_small_slowdowns_are_ignored():
    runs = make_runs({"fast": "P" * 10}, duration_ms=500)
    for run in runs[-3:]:
        run.attempts[0].stop = run.attempts[0].start + 900  # +80%, but only +0.4s
    assert analyze(runs, Settings(recent_days=3)).slowdowns == []


def test_durations_only_use_passing_runs():
    test = analyze(make_runs({"t": "PPFPP"}, duration_ms=2_000)).tests[0]
    assert test.durations is not None
    assert test.durations.count == 4
    assert test.durations.median == 2.0


def test_summary_json_shape():
    data = analyze(make_runs({"t": "PPPFFF"}), env="UAT").to_dict()
    assert data["schema_version"] == 1
    assert data["env"] == "UAT"
    assert data["summary"]["broken"] == 1
    test = data["tests"][0]
    assert test["category"] == "broken"
    assert test["history"] == "PPPFFF"
    assert test["broken_since"]["pipeline_id"] == 1003


def test_suite_duration_change():
    runs = make_runs({"t": "PPP"})
    report = analyze(runs)
    change = report.suite_change
    assert change is not None
    assert change[2] == 0.0
    assert report.period == ("2026-10-01", "2026-10-01")


def test_attempts_without_status_are_ignored():
    runs = make_runs({"t": "PPP"})
    runs[1].attempts[0].status = "skipped"
    test = analyze(runs).tests[0]
    assert test.runs == 2


def test_day_window_constant_matches():
    assert DAY_MS == 86_400_000
