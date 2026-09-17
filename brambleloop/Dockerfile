FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY tests ./tests
COPY run_tests.sh ./

# Default is the web/admin service; the worker and scheduler override the command.
EXPOSE 8000
CMD ["uvicorn", "brambleloop.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
