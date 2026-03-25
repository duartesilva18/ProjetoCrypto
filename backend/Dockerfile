FROM python:3.13-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

RUN groupadd -r trader && useradd -r -g trader trader

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || pip install --no-cache-dir .

COPY . .

RUN chown -R trader:trader /app
USER trader

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "uvloop", "--log-level", "warning"]
