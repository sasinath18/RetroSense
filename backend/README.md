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
- `WS /ws/jobs/{job_id}`: simulated demo telemetry only; it is not a live camera or sensor stream.

Supported upload types: JPEG, PNG, WEBP and BMP; maximum size 12 MB.

## Digital OCR dependency

Digital mode requires the Tesseract executable in addition to the Python package `pytesseract`.

- Windows: install Tesseract OCR and add its installation folder to PATH.
- Ubuntu/Debian: `sudo apt-get install tesseract-ocr`
- macOS: `brew install tesseract`

Check installation with `tesseract --version`.

## Deployment

The repository root contains `render.yaml` for the Render web service. Configure `CORS_ORIGINS` to the exact deployed dashboard origin once GitHub Pages is enabled.

## Prototype limitations

Analog pointer detection and digital OCR are experimental and are not certified measurement systems. Validate results against independently verified reference readings before operational use. Jobs are stored in process memory and uploaded files on local disk; this is not durable multi-user production storage.
