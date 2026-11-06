# LabFlow backend runtime image (Doc 01 §15). One image, three roles:
#   api    -> gunicorn (default command in docker-compose.yml)
#   worker -> celery -A config worker
#   beat   -> celery -A config beat
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# WeasyPrint (report PDFs) needs pango/cairo; psycopg needs libpq.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        shared-mime-info \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

RUN pip install --upgrade pip \
    && pip install /app \
    && useradd --create-home --uid 10001 labflow \
    && chmod +x /app/docker-entrypoint.sh \
    && chown -R labflow:labflow /app

USER labflow

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
