FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create non-root user and working directory
RUN useradd --create-home --shell /bin/bash appuser
WORKDIR /app

# Install the package from source
COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

# Bake the generator input config (scenarios/topology/provider_profiles) into the
# image at /app/contract; can be overridden by mounting a host directory at runtime.
COPY config/ ./contract/

# The canonical OTLP output contract (contracts/generator/v1) is the cross-service SSOT and is
# mounted read-only at runtime (see root docker-compose.yml). CONTRACTS_DIR points at it.
ENV CONTRACTS_DIR=/contracts/generator/v1

# Drop privileges
USER appuser

ENTRYPOINT ["otelgen"]
CMD ["--help"]
