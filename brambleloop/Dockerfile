# python:3.11-slim (Debian trixie) multi-arch index, pinned by digest 2026-10-07 (F-416). Bump deliberately.
FROM python:3.11-slim@sha256:0dd364ba7e10242f07755449e3a3d0e35f9efd987952737b90def6709ab0c5ce

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# The lock, not requirements.txt, is what is installed (F-158, F-416). requirements.txt holds only
# lower bounds, so installing from it let any rebuild pull a major version the suite had never
# run on. requirements.lock pins every distribution in the closure to the version installed in
# the venv the acceptance suite ran on, with sha256 hashes; --require-hashes makes pip refuse a
# package that is unpinned, unhashed or whose bytes differ from what was locked. --no-deps is
# belt-and-braces: the lock is the whole closure, so nothing may be resolved at build time.
COPY requirements.txt requirements.lock ./
# Fonts. Pillow silently falls back to a tiny bitmap face when it cannot find a TrueType
# file, so every listing image rendered in this container had near-illegible text while the
# same code looked correct on a developer machine that happens to have DejaVu installed.
# Nothing local could catch that, which is why it is pinned here rather than assumed.
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core=2.37-8 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.lock

COPY src ./src
# A3-05: the tracked release records the runtime boot guard verifies (brambleloop.ops.release_record).
COPY release ./release
COPY tests ./tests
COPY run_tests.sh ./

# Default is the web/admin service; the worker and scheduler override the command.
# Shell form on purpose: the platform injects PORT and a hardcoded port means the health
# check probes somewhere nothing is listening. The default keeps `docker run` working locally.
EXPOSE 8000
CMD uvicorn brambleloop.app.main:app --host 0.0.0.0 --port ${PORT:-8000}
