# syntax=docker/dockerfile:1.7
# One recipe for every Python service. Build context: the repository root, copied to /app with its layout kept
# (services read the root .env, contracts/fixtures/, ifc/out/ and path dependencies such as ../registry).
#   docker build -f docker/python.Dockerfile --build-arg SERVICE=seraph .
#   BROWSER=1 adds Playwright's Chromium and its system libraries (rosetta, silex).
FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /usr/local/bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON=python3.12 \
    UV_PYTHON_DOWNLOADS=never \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

ARG SERVICE
ARG BROWSER=0

RUN useradd --create-home --uid 10001 app

WORKDIR /app
COPY . /app

RUN test -n "$SERVICE" && cd "/app/$SERVICE" && uv sync --frozen --no-dev
RUN if [ "$BROWSER" = "1" ]; then \
      cd "/app/$SERVICE" && .venv/bin/playwright install --with-deps chromium && rm -rf /var/lib/apt/lists/*; \
    fi
# Mount points for the named volumes, created here so the volumes start owned by the app user.
RUN mkdir -p /data /app/rosetta/shots /app/rosetta/cache /app/rosetta/profiles /app/silex/runtime \
    && chown -R app:app /app /data

USER app
WORKDIR /app/$SERVICE
