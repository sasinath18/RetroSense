"""SQLite persistence for RetroSense analysis jobs.

SQLite uses the configured RETROSENSE_DB_PATH, defaulting to uploads/retrosense.sqlite3.
For durable hosted storage, point this path at a persistent mounted volume or replace
this adapter with a managed database before production use.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(os.getenv("RETROSENSE_DB_PATH", "uploads/retrosense.sqlite3"))


@contextmanager
def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_storage():
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                data_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def save_job(job):
    payload = json.dumps(job, ensure_ascii=False, allow_nan=False)
    updated_at = datetime.now(timezone.utc).isoformat()
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO jobs (job_id, data_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(job_id) DO UPDATE SET
                data_json = excluded.data_json,
                updated_at = excluded.updated_at
            """,
            (job["job_id"], payload, updated_at),
        )


def load_jobs():
    with _connect() as connection:
        rows = connection.execute(
            "SELECT data_json FROM jobs ORDER BY updated_at DESC"
        ).fetchall()

    jobs = {}
    for row in rows:
        try:
            job = json.loads(row["data_json"])
            if not isinstance(job, dict) or not job.get("job_id"):
                continue
            file_path = Path(job.get("path", ""))
            if job.get("status") not in ("completed", "failed") and not file_path.is_file():
                job["status"] = "failed"
                job["error"] = "Uploaded image file is missing; upload the image again."
            jobs[job["job_id"]] = job
        except (TypeError, ValueError, OSError):
            continue
    return jobs


def list_readings():
    jobs = load_jobs()
    readings = []
    for job in jobs.values():
        for reading in job.get("readings", []):
            if len(reading) < 5:
                continue
            readings.append({
                "timestamp": reading[0],
                "instrument": reading[1],
                "value": reading[2],
                "unit": reading[3],
                "status": reading[4],
                "mode": job.get("mode"),
                "job_id": job["job_id"],
            })
    readings.sort(key=lambda row: row["timestamp"], reverse=True)
    return readings
