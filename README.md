# CEIPAL Analytics Dashboard

A production-ready analytics dashboard for CEIPAL ATS with caching, scheduled cache warming, and configurable deployment.

## Project Structure

```
ceipal/
├── backend/                # FastAPI backend
│   ├── app/               # Application source
│   │   ├── main.py        # Entry point
│   │   ├── config/        # Settings (pydantic)
│   │   ├── routes/        # API endpoints
│   │   ├── services/      # CEIPAL API client
│   │   └── core/          # Shared utilities (cache, logging)
│   ├── requirements.txt   # Python dependencies
│   ├── .env.example       # Environment variable template
│   └── .env               # Your local secrets (not committed)
├── frontend/              # React frontend
│   ├── src/
│   │   ├── pages/         # Route pages
│   │   ├── services/      # API client (uses /api via Vite proxy in dev)
│   │   └── components/    # UI components
│   ├── public/            # Static assets
│   ├── package.json
│   ├── .env.example       # Frontend environment template
│   └── vite.config.js    # Vite config with /api proxy
└── README.md
```

## Quick Start

### Backend

```bash
cd backend
python -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env
# Edit .env with your CEIPAL credentials
./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

## Environment Variables

### Backend (`.env`)

| Variable | Description | Default |
|----------|-------------|---------|
| `CEIPAL_BASE_URL` | CEIPAL API base URL | `https://api.ceipal.com` |
| `CEIPAL_WEB_BASE_URL` | CEIPAL web UI base URL | `https://talenthirecls2.ceipal.com` |
| `CEIPAL_USERNAME` | CEIPAL username | (required) |
| `CEIPAL_PASSWORD` | CEIPAL password | (required) |
| `CEIPAL_API_KEY` | CEIPAL API key | (required) |
| `JOB_DETAIL_CACHE_DIR` | Cache persistence directory | `./cache` |
| `REDIS_URL` | Optional Redis for response cache | (empty) |
| `APP_ENV` | Application environment | `production` |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated) | (see .env.example) |
| `APP_PORT` | Server port | `8000` |

### Frontend (`.env`)

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_API_BASE_URL` | API base URL (build-time) | (uses `/api` via Vite proxy) |

## Deployment

### Option A: Reverse Proxy (Recommended)

Run backend and frontend as separate services behind nginx:

```nginx
# nginx.conf
server {
    listen 80;
    server_name yourdomain.com;

    # Frontend (built static files)
    location / {
        root /var/www/ceipal-dashboard/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # Backend API
    location /api/ {
        proxy_pass http://localhost:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Build and deploy:

```bash
cd frontend && npm run build
# Copy dist/ to web server root
```

### Option B: Backend-Served SPA

The backend can serve the frontend build as static files.

```bash
cd frontend && npm run build
# Copy dist/ to backend/static/
cd backend
./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Add to `backend/app/main.py`:

```python
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

## API Endpoints

- `GET /` - Health check
- `GET /health` - Health check endpoint
- `GET /docs` - Swagger UI
- `GET /dashboard/stats` - Dashboard statistics
- `GET /dashboard/status` - Recruiting status
- `GET /dashboard/high-priority` - High priority requirements
- `GET /dashboard/bdm-performance` - BDM performance metrics
- `GET /dashboard/today-submissions` - Today's submissions