"""Command line: ``flakehunter analyze``."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .analysis import Settings, analyze
from .console import render_console
from .html_report import render_html
from .loader import load_history

EXIT_OK = 0
EXIT_FOUND = 1  # problems found with --fail-on
EXIT_ERROR = 2


def _use_color(disabled: bool) -> bool:
    if disabled or os.environ.get("NO_COLOR"):
        return False
    # GitLab job logs render ANSI colors.
    return sys.stdout.isatty() or bool(os.environ.get("GITLAB_CI") or os.environ.get("CI"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flakehunter",
        description="Find flaky tests, real regressions and slowdowns from your Allure results history.",
    )
    parser.add_argument("--version", action="version", version=f"flakehunter {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    a = commands.add_parser(
        "analyze",
        help="analyze the history and report the metrics",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    a.add_argument(
        "--history",
        default="results-history",
        metavar="DIR",
        help="history folder: one .tar.gz archive per run, one sub-folder per run, or a single allure-results folder",
    )
    a.add_argument("--env", default=os.environ.get("TEST_ENV", ""), help="environment name shown in the report")
    a.add_argument(
        "--out", default="flakehunter-report", metavar="DIR", help="output folder for the HTML and JSON report"
    )
    a.add_argument("--min-flips", type=int, default=3, metavar="N", help="flips needed to be flaky")
    a.add_argument("--broken-streak", type=int, default=3, metavar="N", help="consecutive failures needed to be broken")
    a.add_argument("--recent-days", type=int, default=7, metavar="N", help="recent window for slowdowns, in days")
    a.add_argument(
        "--slowdown", type=int, default=20, metavar="PCT", help="median increase reported as a slowdown, in %%"
    )
    a.add_argument(
        "--min-passes", type=int, default=2, metavar="N", help="minimum passing runs for duration statistics"
    )
    a.add_argument(
        "--band", type=int, default=25, metavar="P", help="spread = (P[100-P] - P[P]) / median, P between 1 and 49"
    )
    a.add_argument(
        "--active-runs", type=int, default=3, metavar="N", help="a test missing from the last N runs is ignored"
    )
    a.add_argument("--top", type=int, default=10, metavar="N", help="tests shown per section in the log")
    a.add_argument(
        "--fail-on",
        choices=["never", "broken", "flaky"],
        default="never",
        help="fail the job if there are broken tests (broken), or broken or flaky tests (flaky)",
    )
    a.add_argument("--no-color", action="store_true", help="disable colors in the log")
    return parser


def run_analyze(args: argparse.Namespace) -> int:
    if not 1 <= args.band <= 49:
        print(f"Error: --band must be between 1 and 49, got {args.band}.", file=sys.stderr)
        return EXIT_ERROR

    history = Path(args.history)
    try:
        runs, warnings = load_history(history)
    except FileNotFoundError:
        print(
            f"FlakeHunter: {history} does not exist. Check that the previous job passes it on as an "
            "artifact or through the cache. Nothing to analyze for this run.",
            file=sys.stderr,
        )
        return EXIT_OK  # never block the pipeline because the history is missing

    for warning in warnings[:20]:
        print(f"Warning: {warning}", file=sys.stderr)
    if len(warnings) > 20:
        print(f"Warning: {len(warnings) - 20} more file(s) skipped.", file=sys.stderr)

    if not runs:
        print(f"FlakeHunter: no *-result.json found in {history}. Nothing to analyze.", file=sys.stderr)
        return EXIT_OK

    settings = Settings(
        min_flips=args.min_flips,
        broken_streak=args.broken_streak,
        recent_days=args.recent_days,
        slowdown_threshold=args.slowdown / 100,
        min_passes=args.min_passes,
        band=args.band,
        active_runs=args.active_runs,
    )
    report = analyze(runs, settings, env=args.env)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    html_path = out / "index.html"
    html_path.write_text(render_html(report), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    print(render_console(report, top=args.top, color=_use_color(args.no_color), report_path=str(html_path)))

    counts = report.counts()
    problems = counts["broken"] + counts["always_failing"]
    if args.fail_on == "flaky":
        problems += counts["flaky"]
    if args.fail_on != "never" and problems:
        return EXIT_FOUND
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "analyze":
        return run_analyze(args)
    return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
