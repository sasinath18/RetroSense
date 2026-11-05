# RetroSense

AI-assisted digitization and monitoring for legacy industrial instruments.

## Current prototype
- Responsive dashboard with telemetry chart, alerts, history and CSV export
- FastAPI backend
- Experimental OpenCV analog-gauge baseline: circle detection + pointer-line estimation
- Threshold-based NORMAL / WARNING / DANGER classification
- Ground-truth evaluation utility for repeatable gauge-image testing

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

## Ground-truth evaluation
Use `backend/evaluate_samples.py` to compare algorithm outputs with independently verified readings. Create a CSV manifest with these required columns:
`image,min_value,max_value,expected_value`
Optional columns: `unit,start_angle,end_angle`. Relative image paths are resolved from the CSV file's directory. Leave `expected_value` blank when no reference reading is available; that sample is analysed but excluded from accuracy metrics.

Example manifest:
```csv
image,min_value,max_value,expected_value,unit,start_angle,end_angle
gauge_a.jpg,0,200,0,kg/cm2,135,45
gauge_b.jpg,0,7,0,kg/cm2,135,45
gauge_c.jpg,0,250,,mbar,135,45
```
Run from the backend directory:
```bash
python evaluate_samples.py samples.csv --output evaluation.json
```
The report includes per-image estimates and MAE, RMSE and MAPE. MAPE excludes zero reference values because percentage error is undefined at zero. Do not use guessed readings as ground truth.

Three user-supplied gauge photos were previously used for an initial smoke check. Those outputs were not independently verified; therefore no real-world MAE, MAPE or success rate is claimed. The sample photos are not stored in this repository.

Digital-display OCR and video processing are not implemented yet.

## Tests
Run from the `backend` directory:
```bash
pytest -q
```
Tests cover angle-to-value mapping, invalid calibration, central dial-circle selection and evaluation metric calculations. They do not establish real-world reading accuracy.

## API
- `GET /api/health`
- `POST /api/analyze`
- `POST /api/jobs`
- `POST /api/jobs/{job_id}/start`
- `GET /api/jobs/{job_id}/export.csv`
- `WS /ws/jobs/{job_id}`

## Safety
Academic prototype only. Not certified for safety-critical monitoring or control. Never use its output as the sole basis for industrial decisions.
