FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN useradd --create-home --shell /bin/bash appuser
WORKDIR /app

COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

# Defaults for the compose network; the service names resolve inside it.
ENV COLLECTOR_METRICS_URL=http://collector:9090/metrics \
    CLICKHOUSE_URL=http://clickhouse:8123 \
    CLICKHOUSE_DATABASE=bronze

USER appuser
EXPOSE 8080

CMD ["uvicorn", "flow_ui.main:app", "--host", "0.0.0.0", "--port", "8080"]
