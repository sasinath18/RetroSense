import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import storage


def test_job_round_trips_through_sqlite(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "retrosense.sqlite3")
    storage.init_storage()
    job = {
        "job_id": "job-1",
        "path": str(tmp_path / "gauge.png"),
        "mode": "analog",
        "status": "completed",
        "min_value": 0,
        "max_value": 100,
        "warning_limit": 75,
        "danger_limit": 90,
        "start_angle": 135,
        "end_angle": 45,
        "latest_result": {"confidence": "experimental", "note": "test"},
        "readings": [["2026-11-05T10:00:00+00:00", "Boiler", 42.5, "PSI", "NORMAL"]],
    }
    storage.save_job(job)

    restored = storage.load_jobs()

    assert restored["job-1"] == job
    readings = storage.list_readings()
    assert readings[0]["value"] == 42.5
    assert readings[0]["instrument"] == "Boiler"
    assert readings[0]["min_value"] == 0
    assert readings[0]["max_value"] == 100
    assert readings[0]["start_angle"] == 135
    assert readings[0]["end_angle"] == 45
    assert readings[0]["confidence"] == "experimental"


def test_missing_upload_marks_incomplete_job_failed(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "retrosense.sqlite3")
    storage.init_storage()
    job = {
        "job_id": "job-missing",
        "path": str(tmp_path / "does-not-exist.png"),
        "mode": "analog",
        "status": "uploaded",
        "readings": [],
    }
    storage.save_job(job)

    restored = storage.load_jobs()

    assert restored["job-missing"]["status"] == "failed"
    assert "missing" in restored["job-missing"]["error"]
