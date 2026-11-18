FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.9.17 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY nutrition ./nutrition
COPY migrations ./migrations
COPY alembic.ini ./
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
USER app
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"]
CMD ["uvicorn", "nutrition.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-config", "logging.json"]

FROM base AS test
USER root
RUN uv sync --frozen --no-install-project
COPY tests ./tests
CMD ["pytest", "-q"]

FROM base AS runtime
COPY logging.json ./
