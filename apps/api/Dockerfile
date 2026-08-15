FROM python:3.13.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --system --gid 10001 fieldledger \
    && useradd --system --uid 10001 --gid fieldledger --home-dir /nonexistent fieldledger

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app
COPY tests ./tests

USER fieldledger

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
