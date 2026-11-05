import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
import main


client = TestClient(main.app)


def setup_function():
    main.JOBS.clear()


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_analyze_rejects_unsupported_content_type():
    response = client.post(
        "/api/analyze",
        files={"file": ("notes.txt", b"not an image", "text/plain")},
    )
    assert response.status_code == 415


def test_analyze_rejects_invalid_mode():
    response = client.post(
        "/api/analyze",
        data={"mode": "video"},
        files={"file": ("gauge.png", b"fake image", "image/png")},
    )
    assert response.status_code == 400


def test_analyze_rejects_invalid_analog_range():
    response = client.post(
        "/api/analyze",
        data={"mode": "analog", "min_value": "10", "max_value": "10"},
        files={"file": ("gauge.png", b"fake image", "image/png")},
    )
    assert response.status_code == 400


def test_create_job_and_start_uses_uploaded_image(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "STORE", tmp_path)
    monkeypatch.setattr(main, "_analyse_job", lambda job: {
        "value": 42.5, "confidence": "experimental"
    })
    created = client.post(
        "/api/jobs",
        data={"machine_name": "Boiler pressure", "mode": "analog",
              "min_value": "0", "max_value": "100",
              "warning_limit": "70", "danger_limit": "90"},
        files={"file": ("gauge.png", b"image-bytes", "image/png")},
    )
    assert created.status_code == 200
    job_id = created.json()["job_id"]
    assert (tmp_path / f"{job_id}_gauge.png").read_bytes() == b"image-bytes"

    started = client.post(f"/api/jobs/{job_id}/start")
    assert started.status_code == 200
    body = started.json()
    assert body["status"] == "completed"
    assert body["reading"]["value"] == 42.5
    assert body["reading"]["status"] == "NORMAL"
    assert body["reading"]["analysis"]["confidence"] == "experimental"


def test_start_unknown_job_returns_404():
    response = client.post("/api/jobs/not-a-real-job/start")
    assert response.status_code == 404


def test_csv_export_contains_actual_job_reading(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "STORE", tmp_path)
    monkeypatch.setattr(main, "_analyse_job", lambda job: {"value": 95.0})
    created = client.post(
        "/api/jobs",
        data={"mode": "digital", "warning_limit": "75", "danger_limit": "90"},
        files={"file": ("display.png", b"image-bytes", "image/png")},
    )
    job_id = created.json()["job_id"]
    assert client.post(f"/api/jobs/{job_id}/start").status_code == 200
    exported = client.get(f"/api/jobs/{job_id}/export.csv")
    assert exported.status_code == 200
    assert "95.0" in exported.text
    assert "DANGER" in exported.text


def test_job_rejects_danger_threshold_below_warning():
    response = client.post(
        "/api/jobs",
        data={"warning_limit": "90", "danger_limit": "80"},
        files={"file": ("gauge.png", b"image-bytes", "image/png")},
    )
    assert response.status_code == 400



def test_analyze_rejects_non_finite_measurement_range():
    response = client.post(
        "/api/analyze",
        data={"mode": "analog", "min_value": "0", "max_value": "nan"},
        files={"file": ("gauge.png", b"fake image", "image/png")},
    )
    assert response.status_code == 400
    assert "finite number" in response.json()["detail"]


def test_analyze_rejects_out_of_range_calibration_angle():
    response = client.post(
        "/api/analyze",
        data={"mode": "analog", "start_angle": "360", "end_angle": "45"},
        files={"file": ("gauge.png", b"fake image", "image/png")},
    )
    assert response.status_code == 400
    assert "between 0 and 359" in response.json()["detail"]


def test_create_job_rejects_non_finite_threshold():
    response = client.post(
        "/api/jobs",
        data={"warning_limit": "75", "danger_limit": "inf"},
        files={"file": ("gauge.png", b"image-bytes", "image/png")},
    )
    assert response.status_code == 400
    assert "finite number" in response.json()["detail"]


def test_create_job_rejects_oversized_metadata():
    response = client.post(
        "/api/jobs",
        data={"machine_name": "x" * 81},
        files={"file": ("gauge.png", b"image-bytes", "image/png")},
    )
    assert response.status_code == 400
    assert "80 characters" in response.json()["detail"]



def test_configured_api_token_protects_reading_history(monkeypatch):
    monkeypatch.setenv("RETROSENSE_API_TOKEN", "test-access-token")

    unauthorized = client.get("/api/readings")
    assert unauthorized.status_code == 401

    authorized = client.get(
        "/api/readings",
        headers={"X-API-Token": "test-access-token"},
    )
    assert authorized.status_code == 200
    assert "readings" in authorized.json()


def test_health_endpoint_remains_public_when_api_token_is_enabled(monkeypatch):
    monkeypatch.setenv("RETROSENSE_API_TOKEN", "test-access-token")

    response = client.get("/api/health")

    assert response.status_code == 200
