# RetroSense

AI-assisted digitization and monitoring for legacy industrial instruments.

## Current prototype
- Responsive dashboard with telemetry chart, alerts, history and CSV export
- FastAPI backend
- Experimental OpenCV analog-gauge baseline: circle detection + pointer-line estimation
- Threshold-based NORMAL / WARNING / DANGER classification

## Run locally
```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```
Open `http://127.0.0.1:8000/docs` to test the API. Open `index.html` using a local static server (for example `python -m http.server 5500` from the repository root).

## Analog image analysis
`POST /api/analyze` accepts multipart fields:
- `file`: JPG, PNG, WEBP or BMP (max 12 MB)
- `mode=analog`
- `min_value`, `max_value`
- `start_angle`, `end_angle` in image coordinates (degrees; defaults 135° to 45°)

The current baseline applies CLAHE local-contrast enhancement, Hough circle detection, edge/line detection, calibrated-arc filtering and a centre-proximity/length heuristic to rank pointer candidates. It reports candidate-line diagnostics and a heuristic confidence label (not a probability). It may still fail on glare, perspective distortion, thick or curved pointers, occlusion, unusual dial geometry, tick marks that resemble the pointer, or cluttered backgrounds. It does not yet implement digital-display OCR or video processing. Validate readings against known gauge values and calibrate angles for each instrument.

## API
- `GET /api/health`
- `POST /api/analyze`
- `POST /api/jobs`
- `POST /api/jobs/{job_id}/start`
- `GET /api/jobs/{job_id}/export.csv`
- `WS /ws/jobs/{job_id}`

## Safety
Academic prototype only. Not certified for safety-critical monitoring or control. Never use its output as the sole basis for industrial decisions.
