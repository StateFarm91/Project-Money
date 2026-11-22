# python:3.11-slim (Debian trixie) multi-arch index, pinned by digest 2026-10-07 (F-416). Bump deliberately.
FROM python:3.11-slim@sha256:0dd364ba7e10242f07755449e3a3d0e35f9efd987952737b90def6709ab0c5ce

# F-12: daily keys, caps and windows use date.today(); the process zone is UTC by contract.
ENV TZ=UTC \
    PYTHONUNBUFFERED=1 \
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

# ENG-VIS-IDENTITY: the identity floor's two ONNX models (YuNet MIT + SFace Apache-2.0, ~39 MB),
# fetched at build and verified against the sha256 pins in face_embedder.py. Only the pin file
# and the fetch script are copied first, so this layer is rebuilt only when the pins change.
# --best-effort: an unreachable mirror never breaks the deploy. Missing or mismatched weights
# are refused again at every load (SFaceEmbedder.load), so the floor reads UNMEASURED and Laura
# identity HOLDs; it can never PASS on weights that are not the pinned bytes.
ENV BRAMBLELOOP_FACE_MODEL_DIR=/app/models/face
COPY scripts/fetch_face_models.py ./scripts/fetch_face_models.py
COPY src/brambleloop/visual/face_embedder.py ./src/brambleloop/visual/face_embedder.py
RUN python scripts/fetch_face_models.py --best-effort "$BRAMBLELOOP_FACE_MODEL_DIR"

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
