# One container: the API serves the built UI. NOT built or run in the development environment (Docker was not
# available there), so treat the first `docker build` as the test. See docs/SECURITY.md before exposing it.

FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /srv/terrasentinel

# Pinned, tested versions (backend/requirements.lock).
COPY backend/requirements.lock backend/requirements.lock
RUN pip install -r backend/requirements.lock

COPY backend/app backend/app
COPY data/demo data/demo
COPY --from=ui /ui/dist frontend/dist

# Runs unprivileged. Mount a volume on /srv/terrasentinel/data/state to keep accounts, sessions and the audit log
# across restarts; data/workspace and data/public are rebuildable caches.
RUN useradd --system --uid 10001 terrasentinel \
 && mkdir -p data/state data/workspace data/cache data/public \
 && chown -R terrasentinel data
USER terrasentinel
WORKDIR /srv/terrasentinel/backend

# Behind Cloud Run / a load balancer the client address comes from X-Forwarded-For.
ENV TS_TRUST_PROXY=true TS_PROXY_HOPS=1
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:%s/healthz'%os.environ.get('PORT','8080'),timeout=4)"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
