"""Create a fake results-history/ folder to try FlakeHunter without a real project.

The layout matches the GitLab `.archive_raw_results` template:
one YYYY-MM-DD_<pipeline>.tar.gz archive per run, containing *-result.json files.

Usage:
  python examples/make_demo_history.py --out demo/results-history
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import random
import tarfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

STABLE = [
    "test_home_page",
    "test_product_search",
    "test_product_page",
    "test_sign_up",
    "test_forgot_password",
    "test_edit_profile",
    "test_add_address",
    "test_order_history",
    "test_logout",
    "test_newsletter_signup",
    "test_price_filter",
    "test_sort_results",
    "test_add_to_favorites",
    "test_customer_review",
    "test_contact_form",
]

# name: (failure probability, probability of passing on retry, status, message)
FLAKY = {
    "test_login_wrong_password": (0.30, 0.80, "broken", "TimeoutError: Locator.click: Timeout 30000ms exceeded."),
    "test_add_to_cart": (0.15, 0.70, "failed", "AssertionError: Locator expected to have text '1', actual value: '0'"),
    "test_avatar_upload": (0.20, 0.60, "broken", "playwright._impl._errors.Error: net::ERR_CONNECTION_RESET"),
}

PAYMENT_ERROR = "AssertionError: Locator expected to be visible: get_by_text('Card declined')"
RETRIES = 1


def make_result(name: str, status: str, start: int, duration_ms: int, message: str = "") -> dict:
    full_name = f"tests/e2e/{name}.py::{name}"
    record = {
        "uuid": str(uuid.uuid4()),
        "historyId": hashlib.md5(full_name.encode()).hexdigest(),
        "name": name,
        "fullName": full_name,
        "status": status,
        "start": start,
        "stop": start + duration_ms,
        "labels": [{"name": "suite", "value": "e2e"}, {"name": "framework", "value": "pytest"}],
    }
    if message:
        record["statusDetails"] = {"message": message, "trace": "Traceback (most recent call last): ..."}
    return record


class RunBuilder:
    """Simulates one pipeline: tests run one after the other, with retries."""

    def __init__(self, rng: random.Random, start: datetime, base_durations: dict[str, float]) -> None:
        self.rng = rng
        self.clock = int(start.timestamp() * 1000)
        self.base_durations = base_durations
        self.results: list[dict] = []

    def _record(self, name: str, status: str, duration_ms: int, message: str = "") -> None:
        self.results.append(make_result(name, status, self.clock, duration_ms, message))
        self.clock += duration_ms + 200

    def run(
        self,
        name: str,
        fail_probability: float = 0.0,
        retry_pass_probability: float = 0.0,
        status: str = "failed",
        message: str = "",
        always_fail: bool = False,
        slowdown: float = 1.0,
    ) -> None:
        for attempt in range(RETRIES + 1):
            duration = int(self.base_durations[name] * slowdown * self.rng.uniform(0.9, 1.1) * 1000)
            if always_fail:
                failed = True
            elif attempt == 0:
                failed = self.rng.random() < fail_probability
            else:
                failed = self.rng.random() > retry_pass_probability
            if not failed:
                self._record(name, "passed", duration)
                return
            self._record(name, status, duration // 2, message)


def build_runs(days: int, end: datetime, seed: int) -> list[tuple[str, list[dict]]]:
    rng = random.Random(seed)
    base_durations = {name: rng.uniform(4, 25) for name in [*STABLE, *FLAKY]}
    base_durations.update(
        {
            "test_export_pdf": 35.0,
            "test_payment_card_declined": 12.0,
            "test_promo_code": 9.0,
            "test_express_delivery": 14.0,
            "test_export_csv": 6.0,
        }
    )

    schedule = []
    for offset in range(days - 1, -1, -1):
        day = end - timedelta(days=offset)
        if day.weekday() >= 5:
            continue  # no runs at the weekend
        schedule.append(day.replace(hour=6, minute=30))
        if rng.random() < 0.4:
            schedule.append(day.replace(hour=14, minute=10))

    runs = []
    pipeline = 184_200
    total = len(schedule)
    for index, moment in enumerate(schedule):
        pipeline += rng.randint(3, 15)
        recent = (end - moment).days < 7
        builder = RunBuilder(rng, moment, base_durations)

        for name in STABLE:
            builder.run(name)
        for name, (fail_p, retry_p, status, message) in FLAKY.items():
            builder.run(name, fail_p, retry_p, status, message)
        # Real regression: broken on the last 4 runs.
        builder.run("test_payment_card_declined", message=PAYMENT_ERROR, always_fail=index >= total - 4)
        # New test, failing since it was added 3 runs ago.
        if index >= total - 3:
            builder.run("test_export_csv", message="AssertionError: assert 500 == 200", always_fail=True)
        # Slowdown over the last 7 days.
        builder.run("test_export_pdf", slowdown=1.4 if recent else 1.0)
        # A single isolated failure.
        builder.run(
            "test_promo_code",
            message="AssertionError: Locator expected to have text '-10%'",
            always_fail=index == total // 3,
        )
        # Fixed bug: failing from run 8 to run 11, then repaired.
        builder.run(
            "test_express_delivery",
            message="AssertionError: expected 'Delivery tomorrow', got 'Unavailable'",
            always_fail=8 <= index <= 11,
        )
        runs.append((f"{moment:%Y-%m-%d}_{pipeline}", builder.results))
    return runs


def write_archives(runs: list[tuple[str, list[dict]]], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for run_name, results in runs:
        with tarfile.open(out / f"{run_name}.tar.gz", "w:gz") as tar:
            folder = tarfile.TarInfo(run_name)
            folder.type = tarfile.DIRTYPE
            tar.addfile(folder)
            for record in results:
                data = json.dumps(record).encode()
                info = tarfile.TarInfo(f"{run_name}/{record['uuid']}-result.json")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="demo/results-history")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--end", default="2026-10-16", help="last day of the history (YYYY-MM-DD)")
    args = parser.parse_args()
    end = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
    runs = build_runs(args.days, end, args.seed)
    write_archives(runs, Path(args.out))
    print(f"{len(runs)} runs written to {args.out}")


if __name__ == "__main__":
    main()
