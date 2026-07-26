# Backend Vercel Deployment Guide

## Overview

This guide explains how to deploy the Project Minore backend as a standalone Vercel project.

## Configuration

The backend is configured for Vercel Python runtime with:

| Setting | Value |
|---------|-------|
| Root Directory | `backend` |
| Framework | `None` (Python runtime) |
| Install Command | Default (`pip install -r requirements.txt`) |
| Build Command | None (Python is interpreted) |
| Handler | `api/index.py` |

## Required Files

- `backend/api/index.py` - Vercel serverless function entry point
- `backend/vercel.json` - Vercel configuration
- `backend/requirements.txt` - Python dependencies
- `backend/runtime.txt` - Python version (`python-3.12.0`)
- `backend/VERSION` - Application version
- `backend/src/` - Application source code

## Environment Variables

Configure these in Vercel project settings:

### Required
| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Neon PostgreSQL connection string |
| `JWT_SECRET_KEY` | Secret key for JWT tokens (min 32 chars) |

### Optional
| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `production` | Environment name |
| `DOCS_ENABLED` | `false` | Enable API documentation |
| `RATE_LIMIT_PER_MINUTE` | `60` | API rate limit |

## Deployment Steps

### Option 1: Vercel Dashboard

1. Go to [vercel.com](https://vercel.com)
2. Create a new project
3. Import the repository
4. Set **Root Directory** to `backend`
5. Configure environment variables
6. Click **Deploy**

### Option 2: Vercel CLI

```bash
npm i -g vercel
cd backend
vercel --prod
```

### Option 3: Git Integration

1. Go to Vercel Dashboard → Project Settings → Git
2. Connect the repository
3. Set Root Directory to `backend`
4. Add environment variables
5. Push to main branch

## API Endpoints

The backend exposes the following endpoints:

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | No | Health check |
| `/readiness` | GET | No | Readiness check (requires DB) |
| `/liveness` | GET | No | Liveness check |
| `/version` | GET | No | Version info |
| `/metrics` | GET | No | Prometheus metrics |
| `/` | GET | No | Root info |
| `/api/v1/auth/*` | varies | No | Authentication endpoints |
| `/api/v1/*` | varies | Yes | API endpoints |

## Connecting Frontend to Backend

Update the frontend's `src/services/api.ts`:

```typescript
const api = axios.create({
  baseURL: process.env.VITE_API_URL || 'https://your-backend.vercel.app/api/v1',
  timeout: 30_000,
});
```

Set `VITE_API_URL` in the frontend's Vercel project environment variables.

## Troubleshooting

### Import Errors

If you see import errors, ensure:
- `backend/api/index.py` sets up the Python path correctly
- `backend/src/` is in the Python path

### Database Connection Issues

1. Verify `DATABASE_URL` is set correctly
2. Check Neon PostgreSQL dashboard for connection issues
3. Ensure IP whitelist includes Vercel IPs

### JWT Secret Warning

On first deploy, you may see a warning about `JWT_SECRET_KEY`. Set this environment variable to a secure random value:

```bash
openssl rand -hex 32
```

## Local Development

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn src.main:app --reload
```

The API will be available at `http://localhost:8000`.
