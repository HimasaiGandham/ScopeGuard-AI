# syntax=docker/dockerfile:1
FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OCR_TESSDATA=/opt/tessdata

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --no-create-home scopeguard \
    && install -d -o scopeguard /var/lib/scopeguard

ADD --chmod=0644 --checksum=sha256:7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2 https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd/eng.traineddata /opt/tessdata/eng.traineddata
COPY docforensics/ ./docforensics/

USER scopeguard
EXPOSE 10000
CMD ["python", "-m", "docforensics.hosted"]
