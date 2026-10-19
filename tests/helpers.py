"""Small builders shared by the tests."""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path
from typing import Any

from flakehunter.loader import Attempt, Run

DAY_MS = 86_400_000
BASE_MS = 1_760_000_000_000

STATUSES = {"P": ["passed"], "F": ["failed"], "R": ["broken", "passed"]}


def make_runs(histories: dict[str, str], duration_ms: int = 5_000) -> list[Run]:
    """Build runs from compact histories, one character per run.

    P = passed, F = failed, R = failed then passed on retry, - = not run.
    """
    length = max(len(h) for h in histories.values())
    runs = []
    for i in range(length):
        start = BASE_MS + i * DAY_MS
        attempts = []
        for name, history in histories.items():
            if i >= len(history) or history[i] == "-":
                continue
            for offset, status in enumerate(STATUSES[history[i]]):
                t = start + offset * 10_000
                attempts.append(Attempt(name, name, f"tests/{name}.py::{name}", status, t, t + duration_ms, "boom"))
        runs.append(
            Run(name=f"2026-10-{i + 1:02d}_{1000 + i}", pipeline_id=1000 + i, day="2026-10-01", attempts=attempts)
        )
    return runs


def record(
    name: str, status: str, start: int, duration_ms: int = 3_000, message: str = "error\ndetails"
) -> dict[str, Any]:
    """An Allure *-result.json record."""
    return {
        "historyId": f"id-{name}",
        "name": name,
        "fullName": f"tests/{name}.py::{name}",
        "status": status,
        "start": start,
        "stop": start + duration_ms,
        "statusDetails": {"message": message},
    }


def write_archive(folder: Path, run_name: str, records: list[dict[str, Any]]) -> Path:
    """Write a run archive exactly like the GitLab `.archive_raw_results` template."""
    path = folder / f"{run_name}.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        for i, rec in enumerate(records):
            data = json.dumps(rec).encode()
            info = tarfile.TarInfo(f"{run_name}/{i}-result.json")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def write_history(folder: Path, histories: dict[str, str]) -> Path:
    """Write a results-history folder from compact histories (see make_runs)."""
    folder.mkdir(parents=True, exist_ok=True)
    length = max(len(h) for h in histories.values())
    for i in range(length):
        start = BASE_MS + i * DAY_MS
        records = []
        for name, history in histories.items():
            if i < len(history) and history[i] != "-":
                records += [record(name, status, start + k * 10_000) for k, status in enumerate(STATUSES[history[i]])]
        write_archive(folder, f"2026-10-{i + 1:02d}_{100 + i}", records)
    return folder
