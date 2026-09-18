FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY requirements.txt ./
# Fonts. Pillow silently falls back to a tiny bitmap face when it cannot find a TrueType
# file, so every listing image rendered in this container had near-illegible text while the
# same code looked correct on a developer machine that happens to have DejaVu installed.
# Nothing local could catch that, which is why it is pinned here rather than assumed.
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY tests ./tests
COPY run_tests.sh ./

# Default is the web/admin service; the worker and scheduler override the command.
# Shell form on purpose: the platform injects PORT and a hardcoded port means the health
# check probes somewhere nothing is listening. The default keeps `docker run` working locally.
EXPOSE 8000
CMD uvicorn brambleloop.app.main:app --host 0.0.0.0 --port ${PORT:-8000}
