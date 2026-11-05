# RetroSense

AI-assisted digitization of legacy industrial instruments from uploaded images.

## Prototype capabilities

- Responsive dashboard with reading trend, threshold alerts, browser-persisted history and CSV export
- Optional browser camera preview and one-frame capture for instrument image analysis
- FastAPI backend with upload validation, finite-value checks and health endpoint
- SQLite-backed analysis job and reading history, with a browser-local history cache
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

### Frontend — GitHub Pages
- The Pages workflow publishes the static dashboard from the repository root.
- Expected project URL: `https://sasinath18.github.io/RetroSense/`.

### Backend — Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/sasinath18/RetroSense)

1. Open the button above (or choose **New + → Blueprint** in the Render Dashboard) and connect this repository.
2. Review the Blueprint. It creates one **Free** Docker web service in the **Singapore** region; no paid add-ons are defined. Render will ask you to provide `RETROSENSE_API_TOKEN`—use a long random secret and keep it private.
3. Click **Deploy Blueprint**. The Docker image installs Tesseract OCR and the OpenCV runtime libraries as well as the Python requirements.
4. When the service status is **Live**, copy its public `onrender.com` URL (for example, `https://retrosense-api.onrender.com`).
5. In `index.html`, find the inline configuration immediately before `app.js` and set the URL:
   ```html
   <script>window.RETROSENSE_API_URL = "https://YOUR-RENDER-SERVICE.onrender.com";</script>
   ```
6. Commit and push that change. Keep the Render URL without a trailing slash.
7. Verify `https://YOUR-RENDER-SERVICE.onrender.com/api/health` returns JSON with `"status": "ok"`. The health route is public; image analysis and saved reading-history routes require the API token.

The Free instance can spin down when idle, so its first request after inactivity may take longer. The dashboard uses `http://127.0.0.1:8000` automatically during local development. On a deployed dashboard, it will not send API requests to the GitHub Pages host when the Render URL is missing; it shows an explicit configuration message instead.

The Render blueprint restricts browser API access to the GitHub Pages origin. If you use a custom frontend domain, update `CORS_ORIGINS` in `render.yaml` to that domain's origin (scheme + host only). When you first analyze an image on the deployed dashboard, it will prompt for the API token and keep it in the current browser session. Do not put the token in `index.html` or commit it to GitHub.

## API and validation

See [backend/README.md](backend/README.md) for endpoints and deployment notes. The backend CI workflow runs pytest on pushes and pull requests.

## Known limitations — not production-ready

- Analysis supports uploaded images and optional browser camera frame capture. It captures one still frame per click; continuous live-video analysis is not implemented.
- Physical sensor integration is not implemented.
- WebSocket output is simulated demo telemetry, not real sensor data.
- Analog gauge detection and digital OCR are experimental; successful processing does not guarantee a correct measurement.
- Digital OCR currently selects one numeric token and may misread seven-segment displays, decimal points or multi-field screens.
- Dashboard history is stored in the current browser's local storage; it does not sync across browsers or devices. Backend jobs remain in process memory and uploaded files are on local disk. Shared durable storage, authentication, multi-user isolation, monitoring and production security hardening remain future work.
- Use `backend/evaluate_samples.py` for analog gauge accuracy metrics and `backend/evaluate_digital_samples.py` for digital OCR metrics. Both require independently verified reference values.
- Calibrate each instrument and compare outputs against independently verified ground-truth readings before any operational use.
