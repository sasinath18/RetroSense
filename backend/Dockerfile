FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Tesseract is required by the digital-display OCR feature.
# These packages provide the OpenCV runtime libraries for headless operation.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       tesseract-ocr \
       libglib2.0-0 \
       libgl1 \
       libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY . .

# Run the API as a non-root user; uploads must be writable by that user.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/uploads \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 10000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
