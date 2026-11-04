# RetroSense

AI-assisted digitization and monitoring for legacy industrial instruments.

RetroSense turns images or video frames of analog gauges and digital displays into structured readings, plots trends, and raises threshold-based alerts. This repository currently includes a responsive web dashboard and a FastAPI starter backend.

## Features
- Upload a gauge/display image or video
- Configure instrument type, units, calibration range and alert thresholds
- Live telemetry dashboard with trend chart and event log
- CSV export of readings
- REST API health check and WebSocket-ready job updates
- Synthetic demo mode for testing the interface without hardware

## Run the dashboard
Open `index.html` in a modern browser. For local API integration, start the backend below and serve the frontend from a local web server.

## Run the API
```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

API runs at http://127.0.0.1:8000. Interactive docs: http://127.0.0.1:8000/docs.

## API contract
- `GET /api/health`
- `POST /api/jobs` — multipart upload: `file`, `machine_name`, `mode`, `unit`, `min_value`, `max_value`, `warning_limit`, `danger_limit`
- `POST /api/jobs/{job_id}/start`
- `GET /api/jobs/{job_id}/export.csv`
- `WS /ws/jobs/{job_id}`

The starter backend stores uploaded files locally and returns a simulated reading stream. Replace the demo extraction function in `backend/main.py` with a calibrated computer-vision model before using real instruments.

## Project status
Prototype / academic portfolio project. Not certified for safety-critical industrial control. Always verify readings with a calibrated instrument and keep human supervision for alarms.

## License
MIT
