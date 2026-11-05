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

## Digital OCR dependency

Digital mode requires the Tesseract executable in addition to the Python package `pytesseract`.

- Windows: install Tesseract OCR and add its installation folder to PATH.
- Ubuntu/Debian: `sudo apt-get install tesseract-ocr`
- macOS: `brew install tesseract`

Check installation with `tesseract --version`.

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
