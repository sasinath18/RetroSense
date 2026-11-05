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

The current baseline applies CLAHE local-contrast enhancement, Hough circle detection, centre-biased dial-circle selection, edge/line detection, calibrated-arc filtering and a centre-proximity/length heuristic to rank pointer candidates. The centre-biased circle selector rejects large off-centre background arcs that previously caused incorrect dial-centre selection.

The returned confidence label is heuristic, not a probability. The current line-based method does not reliably distinguish a pointer's reading tip from its counterweight/tail, and can confuse long tick marks or dial graphics with the pointer. It may also fail on glare, perspective distortion, thick or curved pointers, occlusion, unusual dial geometry, dual-scale faces or cluttered backgrounds. A successful API response is not proof of a correct reading. Validate against known reference readings and calibrate angles for each instrument before relying on the result.

Three user-supplied gauge photos were used for an initial local smoke check. The updated detector selected a central dial circle in all three. The first two produced candidate values, while the third returned a low-confidence estimate. These are not accuracy results: the photos do not have independently confirmed ground-truth readings, and the current pointer-tip ambiguity means no MAE, MAPE or success rate is claimed. The sample photos are not stored in this repository.

Digital-display OCR and video processing are not implemented yet.

## Tests
Run from the `backend` directory:
```bash
pytest -q
```
The vision tests cover angle-to-value mapping, invalid calibration, and central dial-circle selection. They do not establish real-world reading accuracy.

## API
- `GET /api/health`
- `POST /api/analyze`
- `POST /api/jobs`
- `POST /api/jobs/{job_id}/start`
- `GET /api/jobs/{job_id}/export.csv`
- `WS /ws/jobs/{job_id}`

## Safety
Academic prototype only. Not certified for safety-critical monitoring or control. Never use its output as the sole basis for industrial decisions.
