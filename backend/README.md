# RetroSense API

FastAPI backend for the RetroSense dashboard.

## Local setup

Requires Python 3.11+.

### Windows PowerShell
```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### macOS / Linux
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

API health: `http://127.0.0.1:8000/api/health`
Interactive API docs: `http://127.0.0.1:8000/docs`

## Image analysis

- `POST /api/analyze`: one uploaded analog or digital instrument image.
- `POST /api/jobs`: validates and stores one uploaded image as a job.
- `POST /api/jobs/{job_id}/start`: analyses that stored image once.
- `GET /api/jobs/{job_id}/export.csv`: exports the job reading.
- `GET /api/readings`: returns readings saved in the configured SQLite database. Protected by `X-API-Token` when `RETROSENSE_API_TOKEN` is configured.

The `/api/health` endpoint stays public for hosting health checks. When `RETROSENSE_API_TOKEN` is configured, image analysis, job creation, job start, CSV export and reading history require the `X-API-Token` header. Local development leaves this unset by default. The dashboard stores the entered token only in the current browser session.
- `WS /ws/jobs/{job_id}`: simulated demo telemetry only; it is not a live camera or sensor stream.

Supported upload types: JPEG, PNG, WEBP and BMP; maximum size 12 MB. Image bytes are decoded and checked, with a 20-megapixel decoded-image limit.

### Examples from the supplied gauge photos

| Gauge face | Select one scale | Enter its range and unit |
|---|---|---|
| Temperature dial | Single black scale | 0–120 °C |
| Compound pressure dial | Outer black scale | 0–250 (verify the printed unit) |
| Compound pressure dial | Inner red scale | 0–2500 mbar |
| Dual pressure dial | Inner black scale | 0–7 kg/cm² |
| Dual pressure dial | Outer red scale | 0–100 PSI |

These ranges are read from the supplied example faces and are setup guidance, not automatic image recognition. Always verify the selected scale and the min/max angle anchors against the physical dial. Never combine the min value from one ring with the max value from another.

## Digital OCR dependency

Digital mode requires the Tesseract executable in addition to the Python package `pytesseract`.

- Windows: install Tesseract OCR and add its installation folder to PATH.
- Ubuntu/Debian: `sudo apt-get install tesseract-ocr`
- macOS: `brew install tesseract`

Check installation with `tesseract --version`.

## Reading interpretation and calibration

- Analog mode detects the dial circle, then looks for a straight pointer line crossing near the hub. The longer arm from the hub is treated as the reading pointer; pointer thickness is deliberately not used to choose direction because some gauges have a thick, short counterweight. If the line candidate falls outside the configured scale, the radial detector is used as a fallback.
- This is currently an OpenCV rule-based computer-vision prototype plus Tesseract OCR; it does not yet contain a trained neural-network model. Real ML training requires many labelled gauge images with verified pointer directions, dial centres, scale ranges, units and reference readings.
- The analog reader accepts a small 5-degree endpoint tolerance to absorb minor image-detection error. This does not replace correct instrument calibration.
- Set minimum and maximum to the actual printed instrument range, select the unit printed beside the chosen scale, and calibrate the angle at the minimum tick and the angle at the maximum tick for each gauge. Image-coordinate angles are 0° right, 90° down, 180° left and 270° up. The dashboard defaults are examples, not universal calibration values. On a dual-scale dial, choose either the inner or outer numbered ring and do not mix the two.
- Digital mode tries Tesseract page-segmentation modes 6, 7, 8 and 13. If they return different numeric values, the API sets `ambiguous=true`, supplies `candidate_values`, and the dashboard warns the operator. Always verify the displayed digits manually.
- Tesseract confidence is a text-recognition score, not a measurement-accuracy probability.

## Preparing a labelled dataset for ML training

The current analog reader is rule-based OpenCV, not a trained ML model. Do not describe the current code as a trained neural network. To train a learned pointer detector, collect varied images from each gauge family and label the **long measuring arm tip**, never the short counterweight.

Use `samples/needle-annotations-template.csv`. Pixel coordinates are measured from the original uploaded image's top-left corner. For every image, record:
- dial centre `dial_cx_px,dial_cy_px`;
- long pointer tip `needle_tip_x_px,needle_tip_y_px`;
- the selected scale's min/max values and unit;
- min/max pointer angles for that scale;
- an independently verified `expected_value`.

Include different manufacturers, dial sizes, pointer shapes, colours, lighting, reflections, camera angles and reading positions. Keep train/validation/test images separated by physical gauge where possible, so nearly identical photos of one gauge do not leak across splits. Start with a small labelled pilot set to confirm the annotation format, then expand to hundreds of diverse labelled images before expecting robust cross-gauge generalisation. The five examples supplied so far are useful debugging samples, but they do not form a sufficient labelled training dataset.

## Accuracy evaluation

The repository includes two command-line evaluation tools:

- Analog gauge: `python evaluate_samples.py samples/analog-manifest-template.csv --output analog-report.json`
- Digital OCR: `python evaluate_digital_samples.py samples/digital-manifest-template.csv --output digital-report.json`

CSV templates are in `samples/`. Put the corresponding instrument images beside each manifest (or use paths relative to the manifest). Fill `expected_value` only with a reading independently confirmed from the instrument or a trusted reference. Blank reference values are processed but excluded from accuracy metrics. Reports include MAE, RMSE and MAPE; digital OCR also reports exact-match percentage. Metrics are only meaningful with verified references and correctly calibrated instruments.

## Deployment

The repository root contains `render.yaml`. It defines a Free Docker web service in Singapore and uses `backend/Dockerfile`. The Docker image installs the Tesseract executable and OpenCV runtime libraries, then installs the Python dependencies from `requirements.txt`. This avoids deploying the `pytesseract` Python wrapper without its required system executable.

The Blueprint sets `CORS_ORIGINS=https://sasinath18.github.io` and asks you to provide `RETROSENSE_API_TOKEN` as a secret during deployment. Set a long random value and never commit it. The dashboard prompts the operator for that token when the first protected API request is made. Update the CORS value if the dashboard is moved to a different origin.

## Reading and job storage

Analysis jobs and completed readings are stored in SQLite. By default the database is `uploads/retrosense.sqlite3`; change this with the `RETROSENSE_DB_PATH` environment variable. Uploaded images are stored in the `uploads/` folder. The browser dashboard also caches its recent history in that browser's local storage.

**Important for hosting:** Render Free uses an ephemeral filesystem. SQLite and uploaded image files on that filesystem can be lost when the instance is replaced or restarted. Do not rely on this as durable cloud storage. For persistent hosted history, provision a persistent disk or managed database and configure the storage path accordingly before using it operationally.

## Camera capture

The dashboard can request browser camera permission, capture a manual still image, or automatically analyze one still frame every five seconds. Camera access requires HTTPS (GitHub Pages) or localhost. This is repeated snapshot analysis, not continuous video streaming. Use the Stop auto control to stop periodic capture.

## Prototype limitations

Analog pointer detection and digital OCR are experimental and are not certified measurement systems. Validate results against independently verified reference readings before operational use. Jobs are stored in process memory and uploaded files on local disk; this is not durable multi-user production storage.
