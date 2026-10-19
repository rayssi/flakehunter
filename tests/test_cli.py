import json

import pytest

from flakehunter.cli import EXIT_ERROR, EXIT_FOUND, EXIT_OK, main
from helpers import write_history


def run(*args: str) -> int:
    return main(["analyze", "--no-color", *args])


def test_writes_html_and_json_reports(tmp_path, capsys):
    history = write_history(tmp_path / "results-history", {"a": "PPPFFF", "b": "PFPFPF"})
    out = tmp_path / "report"
    assert run("--history", str(history), "--out", str(out), "--env", "UAT") == EXIT_OK
    assert (out / "index.html").exists()
    summary = json.loads((out / "summary.json").read_text())
    assert summary["summary"]["broken"] == 1
    assert summary["summary"]["flaky"] == 1
    printed = capsys.readouterr().out
    assert "Summary: 1 broken test and 1 flaky test." in printed
    assert "Environment UAT" in printed


def test_fail_on_controls_the_exit_code(tmp_path):
    history = write_history(tmp_path / "h", {"flaky": "PFPFPF"})
    out = str(tmp_path / "r")
    assert run("--history", str(history), "--out", out) == EXIT_OK
    assert run("--history", str(history), "--out", out, "--fail-on", "broken") == EXIT_OK
    assert run("--history", str(history), "--out", out, "--fail-on", "flaky") == EXIT_FOUND


def test_missing_history_never_fails_the_pipeline(tmp_path, capsys):
    assert run("--history", str(tmp_path / "missing")) == EXIT_OK
    assert "does not exist" in capsys.readouterr().err


def test_empty_history_never_fails_the_pipeline(tmp_path, capsys):
    (tmp_path / "empty").mkdir()
    assert run("--history", str(tmp_path / "empty"), "--out", str(tmp_path / "r")) == EXIT_OK
    assert "Nothing to analyze" in capsys.readouterr().err


def test_invalid_band_is_rejected(tmp_path):
    history = write_history(tmp_path / "h", {"a": "PP"})
    assert run("--history", str(history), "--band", "60") == EXIT_ERROR


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "flakehunter" in capsys.readouterr().out
