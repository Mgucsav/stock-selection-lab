# Backend (FastAPI) konteyneri — Render / Railway / Fly.io gibi bir konteyner barındırıcısında çalışır.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY api ./api
COPY src ./src
COPY config ./config
RUN mkdir -p data/cache data/demo state

# Bulutta fiyatlar ve durum PostgreSQL'de tutulur (SSL_DATABASE_URL); yerel disk yalnızca demo cache için.
ENV SSL_PRICE_STORE=auto SSL_AUTO_REFRESH_HOURS=20 PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=60s --timeout=10s --start-period=90s CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health')" || exit 1

CMD ["sh", "-c", "python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --no-access-log"]
