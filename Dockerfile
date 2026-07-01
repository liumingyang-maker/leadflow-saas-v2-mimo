FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=app:create_app

RUN groupadd -r leadflow && useradd -r -g leadflow -d /app -s /sbin/nologin leadflow

WORKDIR /app

COPY requirements.txt requirements.lock* ./
RUN if [ -f requirements.lock ]; then \
      pip install --no-cache-dir -r requirements.lock; \
    else \
      pip install --no-cache-dir -r requirements.txt; \
    fi

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini .
COPY run_worker.py .

RUN mkdir -p /data && chown -R leadflow:leadflow /app /data

USER leadflow

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health/live', timeout=3).read()"

# Replaces the old "flask" "run" command with Gunicorn for container runtime.
CMD ["sh", "-c", "exec gunicorn \"app:create_app()\" --bind 0.0.0.0:5000 --workers ${WEB_CONCURRENCY:-2} --threads ${GUNICORN_THREADS:-4} --timeout ${GUNICORN_TIMEOUT:-60} --access-logfile - --error-logfile -"]
