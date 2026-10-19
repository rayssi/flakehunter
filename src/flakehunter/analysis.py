"""Metrics computed from the run history.

For each test (identified by its Allure historyId) we build the chronological
sequence of its results, run by run, and derive:

- flakiness: every attempt is put in a row (retries included) and we count the
  flips (passed to failed, or the other way round). A flaky test flips often;
  a broken test flips once, then keeps failing;
- the failure rate;
- duration statistics of passing executions;
- a possible slowdown: median of the last days compared with the median before.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from itertools import pairwise
from typing import Any

from . import __version__
from .loader import Attempt, Run

SUCCESS = "P"
FAILURE = "F"
RETRY = "R"  # failed, then passed on retry, within the same run

PASS_STATUSES = {"passed"}
# Allure: "failed" = failed assertion, "broken" = any other exception (timeout...).
FAILURE_STATUSES = {"failed", "broken"}

BROKEN = "broken"
ALWAYS_FAILING = "always_failing"
FLAKY = "flaky"
WATCH = "watch"
STABLE = "stable"
INACTIVE = "inactive"

CATEGORY_LABELS = {
    BROKEN: "Broken",
    ALWAYS_FAILING: "Always failing",
    FLAKY: "Flaky",
    WATCH: "Watch",
    STABLE: "Stable",
    INACTIVE: "Inactive",
}

DAY_MS = 86_400_000
SCHEMA_VERSION = 1  # bump when summary.json changes in a breaking way


@dataclass
class Settings:
    """Analysis thresholds. All of them can be set from the command line."""

    min_flips: int = 3  # flips needed to be considered flaky
    broken_streak: int = 3  # consecutive failures (latest runs) to be considered broken
    recent_days: int = 7  # "recent" window for slowdowns
    slowdown_threshold: float = 0.20  # +20% median
    min_slowdown_seconds: float = 1.0  # and at least +1s, to ignore noise
    min_passes: int = 2  # minimum passing executions for duration statistics
    band: int = 25  # spread = (P[100-band] - P[band]) / median
    active_runs: int = 3  # a test missing from the last N runs is "inactive"


def percentile(sorted_data: list[float], p: float) -> float:
    """p-th percentile of pre-sorted data, using linear interpolation."""
    n = len(sorted_data)
    if n == 1:
        return sorted_data[0]
    idx = (p / 100) * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    return sorted_data[lo] + (idx - lo) * (sorted_data[hi] - sorted_data[lo])


def count_flips(symbols: list[str]) -> int:
    return sum(1 for a, b in pairwise(symbols) if a != b)


@dataclass
class DurationStats:
    count: int
    min: float
    q1: float
    median: float
    avg: float
    q3: float
    max: float
    spread: float

    @classmethod
    def from_durations(cls, durations: list[float], band: int) -> DurationStats:
        data = sorted(durations)
        med = percentile(data, 50)
        spread = (percentile(data, 100 - band) - percentile(data, band)) / med if med > 0 else 0.0
        return cls(
            count=len(data),
            min=data[0],
            q1=percentile(data, 25),
            median=med,
            avg=statistics.mean(data),
            q3=percentile(data, 75),
            max=data[-1],
            spread=spread,
        )


@dataclass
class Cell:
    """The result of one test in one run."""

    symbol: str  # SUCCESS, FAILURE ou RETRY
    run_index: int
    run_name: str
    pipeline_id: int | None
    day: str


def _expand(cells: list[Cell]) -> list[str]:
    """Attempt-by-attempt results, rebuilt from the cells."""
    symbols: list[str] = []
    for cell in cells:
        symbols.extend([FAILURE, SUCCESS] if cell.symbol == RETRY else [cell.symbol])
    return symbols


@dataclass
class TestStats:
    """Everything FlakeHunter knows about one test across the history."""

    __test__ = False  # not a pytest test class, despite its name

    history_id: str
    name: str
    full_name: str
    cells: list[Cell] = field(default_factory=list)
    attempt_symbols: list[str] = field(default_factory=list)
    passed_attempts: list[Attempt] = field(default_factory=list, repr=False)
    last_error: str = ""
    last_error_start: int = -1
    latest_start: int = -1
    flips: int = 0
    durations: DurationStats | None = None
    recent_median: float | None = None
    previous_median: float | None = None
    category: str = STABLE
    broken_since: Cell | None = None
    failing_streak: int = 0
    was_flaky: bool = False

    @property
    def runs(self) -> int:
        return len(self.cells)

    @property
    def failures(self) -> int:
        return sum(1 for cell in self.cells if cell.symbol == FAILURE)

    @property
    def passed_on_retry(self) -> int:
        return sum(1 for cell in self.cells if cell.symbol == RETRY)

    @property
    def failure_rate(self) -> float:
        return self.failures / self.runs if self.runs else 0.0

    @property
    def flakiness(self) -> float:
        attempts = len(self.attempt_symbols)
        return self.flips / (attempts - 1) if attempts > 1 else 0.0

    @property
    def slowdown(self) -> float | None:
        if self.recent_median is None or not self.previous_median:
            return None
        return self.recent_median / self.previous_median - 1

    @property
    def since(self) -> Cell:
        """The run where the current failing streak started (the first run if unknown)."""
        return self.broken_since if self.broken_since is not None else self.cells[0]

    @property
    def history(self) -> str:
        return "".join(cell.symbol for cell in self.cells)

    def to_dict(self) -> dict[str, Any]:
        since = self.broken_since
        return {
            "name": self.name,
            "full_name": self.full_name,
            "history_id": self.history_id,
            "category": self.category,
            "runs": self.runs,
            "failures": self.failures,
            "failure_rate": round(self.failure_rate, 4),
            "passed_on_retry": self.passed_on_retry,
            "flips": self.flips,
            "flakiness": round(self.flakiness, 4),
            "failing_streak": self.failing_streak,
            "broken_since": (
                {"run": since.run_name, "pipeline_id": since.pipeline_id, "day": since.day} if since else None
            ),
            "was_flaky": self.was_flaky,
            "last_error": self.last_error,
            "durations": asdict(self.durations) if self.durations else None,
            "recent_median": self.recent_median,
            "previous_median": self.previous_median,
            "slowdown": round(self.slowdown, 4) if self.slowdown is not None else None,
            "history": self.history,
        }


@dataclass(frozen=True)
class Slowdown:
    """A test whose recent median duration went up noticeably."""

    test: TestStats
    ratio: float  # +0.35 means 35% slower
    recent_median: float
    previous_median: float


@dataclass
class SuiteRun:
    name: str
    pipeline_id: int | None
    day: str
    wall_time: float
    tests_run: int
    failures: int
    passed_on_retry: int


@dataclass
class Report:
    env: str
    settings: Settings
    generated_at: datetime
    runs: list[SuiteRun]
    tests: list[TestStats]

    def _category(self, category: str) -> list[TestStats]:
        return [t for t in self.tests if t.category == category]

    @property
    def active_tests(self) -> list[TestStats]:
        return [t for t in self.tests if t.category != INACTIVE]

    @property
    def broken(self) -> list[TestStats]:
        return sorted(self._category(BROKEN), key=lambda t: (-t.failing_streak, t.name))

    @property
    def always_failing(self) -> list[TestStats]:
        return sorted(self._category(ALWAYS_FAILING), key=lambda t: (-t.runs, t.name))

    @property
    def flaky(self) -> list[TestStats]:
        return sorted(self._category(FLAKY), key=lambda t: (-t.flakiness, -t.passed_on_retry, t.name))

    @property
    def watch(self) -> list[TestStats]:
        return sorted(self._category(WATCH), key=lambda t: (-t.failures, -t.passed_on_retry, t.name))

    @property
    def slowdowns(self) -> list[Slowdown]:
        s = self.settings
        items = []
        for t in self.active_tests:
            if t.recent_median is None or not t.previous_median:
                continue
            ratio = t.recent_median / t.previous_median - 1
            if ratio >= s.slowdown_threshold and t.recent_median - t.previous_median >= s.min_slowdown_seconds:
                items.append(Slowdown(t, ratio, t.recent_median, t.previous_median))
        return sorted(items, key=lambda item: (-item.ratio, item.test.name))

    @property
    def period(self) -> tuple[str, str]:
        if not self.runs:
            return "", ""
        return self.runs[0].day, self.runs[-1].day

    @property
    def suite_change(self) -> tuple[float, float, float] | None:
        """(last run, median of previous runs, relative change)."""
        if len(self.runs) < 2:
            return None
        last = self.runs[-1].wall_time
        previous = statistics.median(run.wall_time for run in self.runs[:-1])
        if previous <= 0:
            return None
        return last, previous, last / previous - 1

    def counts(self) -> dict[str, int]:
        return {
            "broken": len(self.broken),
            "always_failing": len(self.always_failing),
            "flaky": len(self.flaky),
            "slowdowns": len(self.slowdowns),
            "watch": len(self.watch),
            "tests": len(self.active_tests),
        }

    def to_dict(self) -> dict[str, Any]:
        start, end = self.period
        change = self.suite_change
        return {
            "schema_version": SCHEMA_VERSION,
            "tool": "flakehunter",
            "version": __version__,
            "env": self.env,
            "generated_at": self.generated_at.isoformat(),
            "period": {"start": start, "end": end, "runs": len(self.runs)},
            "summary": self.counts(),
            "settings": asdict(self.settings),
            "suite": {
                "last_wall_time": change[0] if change else None,
                "previous_median": change[1] if change else None,
                "change": round(change[2], 4) if change else None,
                "runs": [asdict(run) for run in self.runs],
            },
            "tests": [t.to_dict() for t in self.tests],
        }


def _symbol(status: str) -> str | None:
    if status in PASS_STATUSES:
        return SUCCESS
    if status in FAILURE_STATUSES:
        return FAILURE
    return None  # skipped, unknown: the test did not really run


def _categorize(t: TestStats, s: Settings, total_runs: int) -> None:
    finals = [FAILURE if cell.symbol == FAILURE else SUCCESS for cell in t.cells]
    streak = 0
    for symbol in reversed(finals):
        if symbol != FAILURE:
            break
        streak += 1
    t.failing_streak = streak

    if t.cells[-1].run_index < total_runs - s.active_runs:
        t.category = INACTIVE  # renamed, deleted or no longer run in this environment
    elif FAILURE not in finals and t.passed_on_retry == 0:
        t.category = STABLE
    elif streak == len(finals):
        t.category = ALWAYS_FAILING
        t.broken_since = t.cells[0]
    elif streak >= s.broken_streak:
        t.category = BROKEN
        t.broken_since = t.cells[-streak]
        t.was_flaky = count_flips(_expand(t.cells[:-streak])) >= s.min_flips
    elif t.flips >= s.min_flips or t.passed_on_retry >= 2:
        t.category = FLAKY
    else:
        t.category = WATCH


def _finalize(t: TestStats, s: Settings, cutoff: int, total_runs: int) -> None:
    t.flips = count_flips(t.attempt_symbols)
    durations = [a.duration for a in t.passed_attempts]
    if len(durations) >= s.min_passes:
        t.durations = DurationStats.from_durations(durations, s.band)
    recent = [a.duration for a in t.passed_attempts if a.start >= cutoff]
    previous = [a.duration for a in t.passed_attempts if a.start < cutoff]
    if len(recent) >= s.min_passes and len(previous) >= s.min_passes:
        t.recent_median = statistics.median(recent)
        t.previous_median = statistics.median(previous)
    _categorize(t, s, total_runs)


def analyze(runs: list[Run], settings: Settings | None = None, env: str = "") -> Report:
    """Analyze runs sorted oldest first."""
    settings = settings or Settings()
    tests: dict[str, TestStats] = {}
    suite: list[SuiteRun] = []

    latest = max((a.start for run in runs for a in run.attempts), default=0)
    cutoff = latest - settings.recent_days * DAY_MS

    for index, run in enumerate(runs):
        grouped: dict[str, list[Attempt]] = {}
        for attempt in run.attempts:
            grouped.setdefault(attempt.history_id, []).append(attempt)

        executed = failures = passed_on_retry = 0
        for history_id, attempts in grouped.items():
            attempts.sort(key=lambda a: a.start)
            symbols = [sym for sym in (_symbol(a.status) for a in attempts) if sym]
            if not symbols:
                continue
            executed += 1
            if symbols[-1] == FAILURE:
                symbol = FAILURE
                failures += 1
            elif FAILURE in symbols:
                symbol = RETRY
                passed_on_retry += 1
            else:
                symbol = SUCCESS

            stats = tests.get(history_id)
            if stats is None:
                stats = TestStats(history_id=history_id, name=attempts[-1].name, full_name=attempts[-1].full_name)
                tests[history_id] = stats
            stats.cells.append(Cell(symbol, index, run.name, run.pipeline_id, run.day))
            stats.attempt_symbols.extend(symbols)

            for attempt in attempts:
                if attempt.status in PASS_STATUSES and attempt.stop > attempt.start:
                    stats.passed_attempts.append(attempt)
                if attempt.status in FAILURE_STATUSES and attempt.start >= stats.last_error_start:
                    stats.last_error = attempt.message
                    stats.last_error_start = attempt.start
                if attempt.start >= stats.latest_start:
                    # Keep the most recent name, in case the test was renamed.
                    stats.latest_start = attempt.start
                    stats.name = attempt.name
                    stats.full_name = attempt.full_name

        suite.append(SuiteRun(run.name, run.pipeline_id, run.day, run.wall_time, executed, failures, passed_on_retry))

    for stats in tests.values():
        _finalize(stats, settings, cutoff, len(runs))

    ordered = sorted(tests.values(), key=lambda t: t.name.lower())
    return Report(
        env=env,
        settings=settings,
        generated_at=datetime.now(timezone.utc),
        runs=suite,
        tests=ordered,
    )
