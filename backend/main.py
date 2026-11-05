from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from vision import read_analog_gauge, GaugeReadError
from digital_ocr import read_digital_display, DigitalReadError
import asyncio, csv, io, json, random, shutil

app = FastAPI(title="RetroSense API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
STORE = Path("uploads"); STORE.mkdir(exist_ok=True)
JOBS = {}

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "retrosense-api", "version": "0.2.0"}

@app.post("/api/analyze")
async def analyze_image(file: UploadFile = File(...), mode: str = Form("analog"),
                        min_value: float = Form(0), max_value: float = Form(100),
                        start_angle: float = Form(135), end_angle: float = Form(45)):
    if mode not in ("analog", "digital"):
        raise HTTPException(400, "mode must be analog or digital")
    if mode == "analog" and max_value <= min_value:
        raise HTTPException(400, "max_value must be greater than min_value")
    if file.content_type not in ("image/jpeg", "image/png", "image/webp", "image/bmp"):
        raise HTTPException(415, "Upload JPG, PNG, WEBP or BMP. Video analysis is not enabled yet.")
    data = await file.read()
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(413, "Image exceeds the 12 MB limit.")
    try:
        if mode == "digital":
            result = read_digital_display(data)
            return {**result, "mode": "digital"}
        result = read_analog_gauge(data, min_value, max_value, start_angle, end_angle)
        return {**result, "mode": "analog"}
    except (GaugeReadError, DigitalReadError) as exc:
        raise HTTPException(422, str(exc))

@app.post("/api/jobs")
async def create_job(file: UploadFile = File(...), machine_name: str = Form("Instrument"),
                     mode: str = Form("analog"), unit: str = Form("PSI"),
                     min_value: float = Form(0), max_value: float = Form(100),
                     warning_limit: float = Form(75), danger_limit: float = Form(90)):
    if max_value <= min_value: raise HTTPException(400, "max_value must be greater than minimum value")
    if danger_limit < warning_limit: raise HTTPException(400, "danger_limit must be >= warning_limit")
    job_id = str(uuid4()); safe_name = Path(file.filename or "capture.bin").name
    destination = STORE / f"{job_id}_{safe_name}"
    with destination.open("wb") as out: shutil.copyfileobj(file.file, out)
    JOBS[job_id] = {"job_id": job_id, "filename": safe_name, "path": str(destination),
        "machine_name": machine_name, "mode": mode, "unit": unit, "min_value": min_value,
        "max_value": max_value, "warning_limit": warning_limit, "danger_limit": danger_limit,
        "readings": [], "status": "uploaded"}
    return {"job_id": job_id, "status": "uploaded", "filename": safe_name}

@app.post("/api/jobs/{job_id}/start")
def start_job(job_id: str):
    if job_id not in JOBS: raise HTTPException(404, "Job not found")
    JOBS[job_id]["status"] = "running"
    return {"job_id": job_id, "status": "running"}

@app.get("/api/jobs/{job_id}/export.csv")
def export_csv(job_id: str):
    job = JOBS.get(job_id)
    if not job: raise HTTPException(404, "Job not found")
    output = io.StringIO(); writer = csv.writer(output)
    writer.writerow(["timestamp", "instrument", "value", "unit", "status"]); writer.writerows(job["readings"]); output.seek(0)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="retrosense-{job_id}.csv"'})

@app.websocket("/ws/jobs/{job_id}")
async def stream_job(websocket: WebSocket, job_id: str):
    await websocket.accept(); job = JOBS.get(job_id)
    if not job:
        await websocket.send_json({"error": "Job not found"}); await websocket.close(); return
    try:
        while True:
            low, high = job["min_value"], job["max_value"]
            value = round(max(low, min(high, low + (high-low) * (0.55 + random.uniform(-0.06, 0.06)))), 2)
            status = "DANGER" if value >= job["danger_limit"] else "WARNING" if value >= job["warning_limit"] else "NORMAL"
            stamp = datetime.now(timezone.utc).isoformat()
            job["readings"].append([stamp, job["machine_name"], value, job["unit"], status])
            await websocket.send_text(json.dumps({"job_id": job_id, "value": value, "unit": job["unit"], "status": status, "timestamp": stamp}))
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return
