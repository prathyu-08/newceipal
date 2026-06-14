FROM python:3.13-slim

# Prevents .pyc files and enables unbuffered stdout for Docker logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install deps first (layer-cached unless requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Runtime cache directory — mount a volume here to persist across restarts
RUN mkdir -p /var/cache/ceipal-dashboard
ENV JOB_DETAIL_CACHE_DIR=/var/cache/ceipal-dashboard

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
