"""The demo in examples/ must keep working: it is the first thing new users try."""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

from flakehunter.cli import EXIT_OK, main

DEMO_SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "make_demo_history.py"


def load_demo() -> ModuleType:
    spec = importlib.util.spec_from_file_location("make_demo_history", DEMO_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_history_can_be_analyzed(tmp_path, capsys):
    demo = load_demo()
    runs = demo.build_runs(30, datetime(2026, 10, 16, tzinfo=timezone.utc), seed=7)
    demo.write_archives(runs, tmp_path / "results-history")
    out = tmp_path / "report"
    code = main(["analyze", "--history", str(tmp_path / "results-history"), "--out", str(out), "--no-color"])
    assert code == EXIT_OK
    printed = capsys.readouterr().out
    assert "Broken tests (1)" in printed
    assert "Always failing (1)" in printed
    assert "Flaky tests (3)" in printed
    assert (out / "index.html").exists()
