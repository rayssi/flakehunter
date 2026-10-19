"""Reading the run history.

FlakeHunter reads the ``results-history/`` folder produced by the GitLab
``.archive_raw_results`` template: one ``YYYY-MM-DD_<pipeline>.tar.gz`` archive
per run, containing the Allure ``*-result.json`` files.

Two other layouts are accepted, handy when working locally:
- one sub-folder per run (archives already extracted);
- a single ``allure-results/`` folder, treated as one run.
"""

from __future__ import annotations

import json
import re
import tarfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RESULT_SUFFIX = "-result.json"
ARCHIVE_SUFFIXES = (".tar.gz", ".tgz")
RUN_NAME_RE = re.compile(r"^(?P<day>\d{4}-\d{2}-\d{2})_(?P<pipeline>\d+)$")
MAX_MESSAGE_LENGTH = 300


@dataclass
class Attempt:
    """One execution of a test, i.e. one *-result.json file.

    When a test is retried, each attempt gets its own file with the same historyId.
    """

    history_id: str
    name: str
    full_name: str
    status: str
    start: int  # milliseconds
    stop: int
    message: str = ""

    @property
    def duration(self) -> float:
        """Duration in seconds."""
        return max(self.stop - self.start, 0) / 1000


@dataclass
class Run:
    """One run of the test suite, usually one GitLab pipeline."""

    name: str
    pipeline_id: int | None = None
    day: str = ""
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def start(self) -> int:
        starts = [a.start for a in self.attempts if a.start]
        return min(starts) if starts else 0

    @property
    def wall_time(self) -> float:
        """Real duration of the run in seconds, from the first test started to the last one finished."""
        starts = [a.start for a in self.attempts if a.start]
        stops = [a.stop for a in self.attempts if a.stop]
        if not starts or not stops:
            return 0.0
        return max(max(stops) - min(starts), 0) / 1000

    def sort_key(self) -> tuple[int, int, str]:
        return (self.start, self.pipeline_id or 0, self.name)


def parse_attempt(record: dict[str, Any]) -> Attempt | None:
    """Turn an Allure *-result.json record into an Attempt. Returns None if unusable."""
    history_id = record.get("historyId")
    status = record.get("status")
    if not history_id or not status:
        return None
    details = record.get("statusDetails") or {}
    lines = str(details.get("message") or "").strip().splitlines()
    message = lines[0][:MAX_MESSAGE_LENGTH] if lines else ""
    try:
        start = int(record.get("start") or 0)
        stop = int(record.get("stop") or 0)
    except (TypeError, ValueError):
        start = stop = 0
    return Attempt(
        history_id=str(history_id),
        name=str(record.get("name") or record.get("fullName") or history_id),
        full_name=str(record.get("fullName") or ""),
        status=str(status),
        start=start,
        stop=stop,
        message=message,
    )


def _parse_bytes(raw: bytes, source: str, warnings: list[str]) -> Attempt | None:
    try:
        record = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        warnings.append(f"skipped unreadable file: {source}")
        return None
    return parse_attempt(record) if isinstance(record, dict) else None


def _read_archive(path: Path, warnings: list[str]) -> list[Attempt]:
    attempts: list[Attempt] = []
    try:
        with tarfile.open(path, "r:*") as tar:
            for member in tar:
                if not member.isfile() or not member.name.endswith(RESULT_SUFFIX):
                    continue
                handle = tar.extractfile(member)
                if handle is None:
                    continue
                attempt = _parse_bytes(handle.read(), f"{path.name}:{member.name}", warnings)
                if attempt:
                    attempts.append(attempt)
    except (tarfile.TarError, OSError, EOFError) as exc:
        warnings.append(f"skipped unreadable archive: {path.name} ({exc})")
    return attempts


def _read_directory(path: Path, warnings: list[str]) -> list[Attempt]:
    attempts: list[Attempt] = []
    for file in sorted(path.rglob(f"*{RESULT_SUFFIX}")):
        try:
            raw = file.read_bytes()
        except OSError:
            warnings.append(f"skipped unreadable file: {file}")
            continue
        attempt = _parse_bytes(raw, str(file), warnings)
        if attempt:
            attempts.append(attempt)
    return attempts


def _run_name(path: Path) -> str:
    for suffix in ARCHIVE_SUFFIXES:
        if path.name.endswith(suffix):
            return path.name[: -len(suffix)]
    return path.name


def _make_run(name: str, attempts: list[Attempt]) -> Run:
    run = Run(name=name, attempts=attempts)
    match = RUN_NAME_RE.match(name)
    if match:
        run.pipeline_id = int(match["pipeline"])
        run.day = match["day"]
    elif run.start:
        run.day = datetime.fromtimestamp(run.start / 1000, tz=timezone.utc).date().isoformat()
    return run


def load_history(path: Path) -> tuple[list[Run], list[str]]:
    """Load every run found in ``path``, oldest first.

    Returns the runs and a list of warnings (skipped files).
    """
    if not path.exists():
        raise FileNotFoundError(path)

    warnings: list[str] = []
    runs: list[Run] = []

    if path.is_file():
        entries = [path]
    elif any(path.glob(f"*{RESULT_SUFFIX}")):
        # A plain allure-results folder: a single run.
        runs.append(_make_run(path.name, _read_directory(path, warnings)))
        entries = []
    else:
        entries = sorted(path.iterdir())

    for entry in entries:
        if entry.is_file() and entry.name.endswith(ARCHIVE_SUFFIXES):
            attempts = _read_archive(entry, warnings)
        elif entry.is_dir():
            attempts = _read_directory(entry, warnings)
        else:
            continue
        if attempts:
            runs.append(_make_run(_run_name(entry), attempts))
        else:
            warnings.append(f"skipped run with no results: {entry.name}")

    runs = [run for run in runs if run.attempts]
    runs.sort(key=Run.sort_key)
    return runs, warnings
