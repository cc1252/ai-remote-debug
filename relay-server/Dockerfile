FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ARD_ARTIFACT_DIR=/data/artifacts

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 ard \
    && mkdir -p /data/artifacts \
    && chown -R ard:ard /data/artifacts

COPY --chown=ard:ard main.py ./

USER ard
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
