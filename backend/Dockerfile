# syntax=docker/dockerfile:1.6
# ── Stage 1: build Vue frontend ───────────────────────────────────────
FROM node:20-alpine AS frontend
WORKDIR /build
RUN npm config set registry https://registry.npmmirror.com
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Django runtime ───────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

# psycopg[binary] ships precompiled wheels — no compiler needed.
# Keep only curl for healthcheck. Use Tsinghua Debian mirror for 大陆 ECS speed.
RUN sed -i 's|http://deb.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g; s|http://security.debian.org|https://mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY backend /app
# SPA static assets — served by the Django catch-all view in core.views.spa.
# Placed outside /app so a bind mount of ./backend:/app in dev doesn't mask them.
COPY --from=frontend /build/dist /srv/kb_frontend_dist

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-"]
