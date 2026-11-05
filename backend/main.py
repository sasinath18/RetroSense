from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from vision import read_analog_gauge, GaugeReadError
from digital_ocr import read_digital_display, DigitalReadError
from storage import init_storage, load_jobs, save_job, list_readings
import asyncio, csv, io, json, random, os, math, secrets
import cv2
import numpy as np

app = FastAPI(title="RetroSense API", version="0.4.0")
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in os.getenv("CORS_ORIGINS", "*").split(",") if x.strip()], allow_credentials=False,
                   allow_methods=["GET", "POST"], allow_headers=["*"])
STORE = Path("uploads")
STORE.mkdir(exist_ok=True)
JOBS = {}
init_storage()
JOBS.update(load_jobs())
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp"}


def require_api_token(x_api_token: str | None = Header(default=None)):
    """Require a shared API token when RETROSENSE_API_TOKEN is configured."""
    expected = os.getenv("RETROSENSE_API_TOKEN", "").strip()
    if expected and not secrets.compare_digest(x_api_token or "", expected):
        raise HTTPException(401, "Invalid or missing API access token.")
    return True




def _validate_numeric_settings(mode, min_value, max_value, start_angle, end_angle,
                               warning_limit=None, danger_limit=None):
    values = {
        "min_value": min_value, "max_value": max_value,
        "start_angle": start_angle, "end_angle": end_angle,
    }
    if warning_limit is not None:
        values["warning_limit"] = warning_limit
    if danger_limit is not None:
        values["danger_limit"] = danger_limit
    for name, value in values.items():
        if not math.isfinite(float(value)):
            raise HTTPException(400, f"{name} must be a finite number")
    if mode == "analog":
        if max_value <= min_value:
            raise HTTPException(400, "max_value must be greater than min_value")
        if not (0 <= start_angle < 360 and 0 <= end_angle < 360):
            raise HTTPException(400, "Calibration angles must be between 0 and 359 degrees")
        sweep = (end_angle - start_angle) % 360
        if sweep < 1 or sweep > 359:
            raise HTTPException(400, "Calibration angle sweep is invalid")
    if warning_limit is not None and danger_limit is not None:
        if danger_limit < warning_limit:
            raise HTTPException(400, "danger_limit must be >= warning_limit")

def _validate_upload(file: UploadFile, mode: str):
    if mode not in ("analog", "digital"):
        raise HTTPException(400, "mode must be analog or digital")
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Upload JPG, PNG, WEBP or BMP.")
    filename = Path(file.filename or "capture").name
    if filename in ("", ".", ".."):
        raise HTTPException(400, "Invalid filename.")
    return filename


async def _read_upload(file: UploadFile):
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(400, "Uploaded image is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image exceeds the 12 MB limit.")
    return data



MAX_IMAGE_PIXELS = 20_000_000


def _validate_image_bytes(data: bytes):
    """Reject spoofed image MIME types and excessive decoded image dimensions."""
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(415, "The uploaded file is not a valid supported image.")
    height, width = image.shape[:2]
    if height * width > MAX_IMAGE_PIXELS:
        raise HTTPException(413, "Image dimensions exceed the 20 megapixel limit.")

def _analyse_job(job):
    data = Path(job["path"]).read_bytes()
    if job["mode"] == "digital":
        return read_digital_display(data)
    return read_analog_gauge(data, job["min_value"], job["max_value"],
                             job["start_angle"], job["end_angle"])


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "retrosense-api", "version": "0.4.0"}


@app.post("/api/analyze", dependencies=[Depends(require_api_token)])
async def analyze_image(file: UploadFile = File(...), mode: str = Form("analog"),
                        min_value: float = Form(0), max_value: float = Form(100),
                        start_angle: float = Form(135), end_angle: float = Form(45)):
    _validate_upload(file, mode)
    _validate_numeric_settings(mode, min_value, max_value, start_angle, end_angle)
    data = await _read_upload(file)
    _validate_image_bytes(data)
    try:
        if mode == "digital":
            return {**read_digital_display(data), "mode": "digital"}
        return {**read_analog_gauge(data, min_value, max_value, start_angle, end_angle),
                "mode": "analog"}
    except (GaugeReadError, DigitalReadError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/jobs", dependencies=[Depends(require_api_token)])
async def create_job(file: UploadFile = File(...), machine_name: str = Form("Instrument"),
                     mode: str = Form("analog"), unit: str = Form("PSI"),
                     min_value: float = Form(0), max_value: float = Form(100),
                     warning_limit: float = Form(75), danger_limit: float = Form(90),
                     start_angle: float = Form(135), end_angle: float = Form(45)):
    safe_name = _validate_upload(file, mode)
    _validate_numeric_settings(mode, min_value, max_value, start_angle, end_angle,
                               warning_limit, danger_limit)
    machine_name = (machine_name or "").strip()
    if not machine_name:
        raise HTTPException(400, "machine_name cannot be empty")
    if len(machine_name) > 80:
        raise HTTPException(400, "machine_name must be 80 characters or fewer")
    if len(unit) > 16:
        raise HTTPException(400, "unit must be 16 characters or fewer")
    data = await _read_upload(file)
    _validate_image_bytes(data)
    job_id = str(uuid4())
    destination = STORE / f"{job_id}_{safe_name}"
    destination.write_bytes(data)
    JOBS[job_id] = {
        "job_id": job_id, "filename": safe_name, "path": str(destination),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "machine_name": machine_name, "mode": mode, "unit": unit,
        "min_value": min_value, "max_value": max_value,
        "warning_limit": warning_limit, "danger_limit": danger_limit,
        "start_angle": start_angle, "end_angle": end_angle,
        "readings": [], "status": "uploaded",
    }
    save_job(JOBS[job_id])
    return {"job_id": job_id, "status": "uploaded", "filename": safe_name}


@app.post("/api/jobs/{job_id}/start", dependencies=[Depends(require_api_token)])
def start_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job["status"] == "completed":
        return {"job_id": job_id, "status": "completed",
                "latest_reading": job["readings"][-1] if job["readings"] else None}
    try:
        result = _analyse_job(job)
    except (GaugeReadError, DigitalReadError) as exc:
        job["status"] = "failed"
        job["error"] = str(exc)
        save_job(job)
        raise HTTPException(422, str(exc)) from exc
    except OSError as exc:
        job["status"] = "failed"
        job["error"] = "Uploaded image file is missing or unreadable; upload the image again."
        save_job(job)
        raise HTTPException(410, job["error"]) from exc
    value = float(result["value"])
    status = ("DANGER" if value >= job["danger_limit"] else
              "WARNING" if value >= job["warning_limit"] else "NORMAL")
    stamp = datetime.now(timezone.utc).isoformat()
    reading = [stamp, job["machine_name"], value, job["unit"], status]
    job["readings"].append(reading)
    job["latest_result"] = result
    job["status"] = "completed"
    save_job(job)
    return {"job_id": job_id, "status": "completed", "reading": {
        "timestamp": stamp, "instrument": job["machine_name"], "value": value,
        "unit": job["unit"], "status": status, "mode": job["mode"],
        "analysis": result,
        "min_value": job["min_value"], "max_value": job["max_value"],
        "warning_limit": job["warning_limit"], "danger_limit": job["danger_limit"],
        "start_angle": job["start_angle"], "end_angle": job["end_angle"],
    }}


@app.get("/api/jobs/{job_id}/export.csv", dependencies=[Depends(require_api_token)])
def export_csv(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "instrument", "value", "unit", "status"])
    writer.writerows(job["readings"])
    output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="retrosense-{job_id}.csv"'})


@app.get("/api/readings", dependencies=[Depends(require_api_token)])
def get_readings():
    """Return readings persisted by this API instance's configured storage."""
    items = list_readings()
    return {"count": len(items), "readings": items}


@app.websocket("/ws/jobs/{job_id}")
async def stream_job(websocket: WebSocket, job_id: str):
    await websocket.accept()
    job = JOBS.get(job_id)
    if not job:
        await websocket.send_json({"error": "Job not found"})
        await websocket.close()
        return
    # Demo stream only: this endpoint does not read a live camera or physical sensor.
    try:
        while True:
            low, high = job["min_value"], job["max_value"]
            value = round(max(low, min(high, low + (high-low) *
                         (0.55 + random.uniform(-0.06, 0.06)))), 2)
            status = ("DANGER" if value >= job["danger_limit"] else
                      "WARNING" if value >= job["warning_limit"] else "NORMAL")
            stamp = datetime.now(timezone.utc).isoformat()
            await websocket.send_text(json.dumps({
                "job_id": job_id, "value": value, "unit": job["unit"],
                "status": status, "timestamp": stamp, "source": "simulated_demo",
            }))
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return
