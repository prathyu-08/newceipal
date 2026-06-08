# CEIPAL Analytics Dashboard Backend

FastAPI server that proxies CEIPAL ATS APIs with caching and enriched analytics.

## Setup

```bash
# Create virtual environment
python -m venv venv

# Install dependencies
./venv/bin/pip install -r requirements.txt

# Copy environment template
cp .env.example .env
# Edit .env with your CEIPAL credentials
```

## Run

### Development

```bash
./venv/bin/uvicorn app.main:app --reload --port 8000
```

### Production

```bash
./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Environment Variables

See `.env.example` for all configuration options.

| Variable | Description |
|----------|-------------|
| `CEIPAL_USERNAME`, `CEIPAL_PASSWORD`, `CEIPAL_API_KEY` | CEIPAL credentials (required) |
| `JOB_DETAIL_CACHE_DIR` | Cache persistence directory (default: `./cache`) |
| `REDIS_URL` | Optional Redis URL for distributed caching |
| `CORS_ORIGINS` | Comma-separated allowed origins for CORS |
| `APP_ENV` | `development` or `production` |

## Endpoints

- `GET /` - Health check
- `GET /health` - Health check endpoint  
- `GET /docs` - Swagger UI documentation
- `GET /redoc` - ReDoc documentation
- `GET /dashboard/stats` - Dashboard statistics
- `GET /dashboard/status` - Recruiting status
- `GET /dashboard/high-priority` - High priority requirements
- `GET /dashboard/bdm-performance` - BDM performance metrics
- `GET /dashboard/today-submissions` - Today's submissions

## Cache

Job details are cached to `JOB_DETAIL_CACHE_DIR/job_details.json` with a 6-hour TTL.
The cache is warmed on startup for the last 7 days of jobs.