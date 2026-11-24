# jlr-server. Build from the repository root: docker compose -f server/compose.yml up -d --build
FROM python:3.12-slim-bookworm
COPY server/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && useradd --uid 1000 --create-home app && mkdir /data && chown app /data
WORKDIR /app
# The same JLR client the Home Assistant integration uses.
COPY custom_components/jlr_data_hub/jlr_datahub ./jlr_datahub
COPY server/app.py server/store.py server/alerts.py ./
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data
USER app
EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')"
# One worker: the stream and poller threads live in the process.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log", "--workers", "1"]
