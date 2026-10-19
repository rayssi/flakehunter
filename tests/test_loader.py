import json

from flakehunter.loader import load_history, parse_attempt
from helpers import DAY_MS, record, write_archive


def test_reads_gitlab_archives_oldest_first(tmp_path):
    write_archive(tmp_path, "2026-10-02_200", [record("a", "failed", 2 * DAY_MS)])
    write_archive(tmp_path, "2026-10-01_100", [record("a", "passed", DAY_MS)])
    (tmp_path / "notes.txt").write_text("ignored")
    runs, warnings = load_history(tmp_path)
    assert [r.pipeline_id for r in runs] == [100, 200]
    assert runs[0].day == "2026-10-01"
    assert runs[1].attempts[0].message == "error"
    assert warnings == []


def test_reads_one_folder_per_run(tmp_path):
    run = tmp_path / "2026-10-01_100"
    run.mkdir()
    (run / "x-result.json").write_text(json.dumps(record("a", "passed", DAY_MS)))
    runs, _ = load_history(tmp_path)
    assert len(runs) == 1
    assert runs[0].pipeline_id == 100


def test_reads_a_plain_allure_results_folder_as_one_run(tmp_path):
    (tmp_path / "1-result.json").write_text(json.dumps(record("a", "passed", DAY_MS)))
    (tmp_path / "2-result.json").write_text(json.dumps(record("b", "failed", DAY_MS)))
    runs, _ = load_history(tmp_path)
    assert len(runs) == 1
    assert len(runs[0].attempts) == 2
    assert runs[0].day  # derived from the timestamps


def test_skips_broken_files_with_a_warning(tmp_path):
    write_archive(tmp_path, "2026-10-01_100", [record("a", "passed", DAY_MS)])
    (tmp_path / "2026-10-02_200.tar.gz").write_bytes(b"not a tar archive")
    bad_run = tmp_path / "2026-10-03_300"
    bad_run.mkdir()
    (bad_run / "x-result.json").write_text("{not json")
    runs, warnings = load_history(tmp_path)
    assert len(runs) == 1
    assert any("unreadable archive" in w for w in warnings)
    assert any("unreadable file" in w for w in warnings)


def test_never_extracts_archives_to_disk(tmp_path):
    # A malicious archive with a path traversal member must not write anything outside.
    write_archive(tmp_path, "2026-10-01_100", [record("a", "passed", DAY_MS)])
    import io
    import tarfile

    evil = tmp_path / "2026-10-02_200.tar.gz"
    with tarfile.open(evil, "w:gz") as tar:
        data = json.dumps(record("b", "passed", 2 * DAY_MS)).encode()
        info = tarfile.TarInfo("../../escaped-result.json")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    runs, _ = load_history(tmp_path)
    assert len(runs) == 2
    assert not (tmp_path.parent.parent / "escaped-result.json").exists()


def test_parse_attempt_rejects_incomplete_records():
    assert parse_attempt({"status": "passed"}) is None
    assert parse_attempt({"historyId": "x"}) is None
    attempt = parse_attempt({"historyId": "x", "status": "passed", "start": "oops", "stop": None})
    assert attempt is not None
    assert attempt.start == 0
    assert attempt.name == "x"


def test_long_error_messages_are_cut(tmp_path):
    rec = record("a", "failed", DAY_MS, message="x" * 1000 + "\nsecond line")
    write_archive(tmp_path, "2026-10-01_100", [rec])
    runs, _ = load_history(tmp_path)
    assert len(runs[0].attempts[0].message) == 300
