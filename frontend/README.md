# CEIPAL Analytics Dashboard Frontend

React + Vite dashboard for CEIPAL ATS analytics.

## Setup

```bash
npm ci
cp .env.example .env
# Edit .env if needed
```

## Development

```bash
npm run dev
# Opens at http://localhost:5173
# API calls proxy to http://localhost:8000 via vite.config.js
```

## Production Build

```bash
npm run build
# Output: dist/
# Serve via nginx, CDN, or configure backend to serve static files.
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_API_BASE_URL` | API base URL (empty uses `/api` proxy) | (empty - dev proxy) |

## Project Structure

```
src/
├── pages/           # Route components
├── lib/
│   └── api/         # API client (dashboardApi.js, cache utilities)
└── components/      # Shared UI components
```