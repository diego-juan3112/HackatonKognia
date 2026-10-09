# Plan B de Reto 01 (docs/11 §5): el mismo app de voz que va a Vercel, en un
# contenedor. Solo el runtime minimo (requirements.txt): sin E5, torch ni Postgres.
#   docker build -t kognia-api .
#   docker run --rm -p 8000:8000 --env-file .env kognia-api
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# config.py resuelve config/ y data/ relativo a la raiz del repo (/app).
COPY src ./src
COPY config ./config
COPY data ./data

RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

ENV PORT=8000
EXPOSE 8000

# Forma shell para que ${PORT} lo fije el host (Container Apps, Render, Railway).
CMD exec uvicorn api.app_voice:app --app-dir src --host 0.0.0.0 --port ${PORT:-8000}
