# RetroSense

AI-assisted digitization of legacy industrial instruments from uploaded images.

## Prototype capabilities

- Responsive dashboard with reading trend, threshold alerts, history and CSV export
- FastAPI backend with upload validation and health endpoint
- Experimental OpenCV analog-gauge pointer estimation
- Experimental digital-display OCR using OpenCV preprocessing and Tesseract
- NORMAL / WARNING / DANGER threshold classification
- Automated backend tests with GitHub Actions

## Run locally

Requires Python 3.11+.

### 1. Start the API (Windows PowerShell)

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### 2. Start the dashboard in a second terminal

From the repository root:

```powershell
py -m http.server 5500
```

Open `http://localhost:5500`. The local dashboard automatically targets the API at `http://127.0.0.1:8000`.

API health: `http://127.0.0.1:8000/api/health`
API docs: `http://127.0.0.1:8000/docs`

For macOS/Linux, create the virtual environment with `python3 -m venv .venv` and activate it with `source .venv/bin/activate`.

## Digital OCR setup

Digital mode also requires the Tesseract system executable:
- Windows: install Tesseract OCR and add its installation directory to PATH.
- Ubuntu/Debian: `sudo apt-get install tesseract-ocr`
- macOS: `brew install tesseract`

Verify with `tesseract --version`.

## Deployment

- GitHub Pages hosts the static dashboard only.
- Render hosts the FastAPI backend using the root `render.yaml` blueprint.
- After deploying the backend, set `window.RETROSENSE_API_URL` in the dashboard to the Render service URL before publishing the frontend. The Pages workflow deploys the repository root.

## API and validation

See [backend/README.md](backend/README.md) for endpoints and deployment notes. The backend CI workflow runs pytest on pushes and pull requests.

## Known limitations — not production-ready

- Analysis is single-image upload based; live camera streaming and physical sensor integration are not implemented.
- WebSocket output is simulated demo telemetry, not real sensor data.
- Analog gauge detection and digital OCR are experimental; successful processing does not guarantee a correct measurement.
- Digital OCR currently selects one numeric token and may misread seven-segment displays, decimal points or multi-field screens.
- Jobs are held in process memory and uploaded files are on local disk. Durable storage, authentication, multi-user isolation, monitoring and production security hardening remain future work.
- Calibrate each instrument and compare outputs against independently verified ground-truth readings before any operational use.
