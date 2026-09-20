# Single-service deployment.
#
# Stage 1 builds the React frontend. Stage 2 runs FastAPI, which serves both
# the API and the built frontend from the same origin - so the browser calls
# /api/... on whatever host it was loaded from, and no backend URL is ever
# hardcoded into the frontend bundle.
#
# Build and run locally exactly as it runs in production:
#   docker build -t it-service-agent .
#   docker run --rm -p 7860:7860 it-service-agent

# ---------------------------------------------------------------- frontend
FROM node:20-alpine AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ----------------------------------------------------------------- runtime
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY data/ data/
COPY --from=frontend /build/dist frontend/dist

# Prototype-generated tickets and the audit log are written here. Hosting
# platforms often run the container as a non-root user, so make it writable.
# If the filesystem is read-only anyway, the app degrades to in-memory records
# instead of failing.
RUN mkdir -p data/runtime && chmod -R 777 data/runtime

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/api/health').read()"

CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
