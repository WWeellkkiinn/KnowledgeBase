# syntax=docker/dockerfile:1.6
# ──────────────── Stage 1: 前端构建 ────────────────
FROM node:20-alpine AS frontend
WORKDIR /build/frontend
# 国内 mirror（海外部署改回 https://registry.npmjs.org 即可）
RUN npm config set registry https://registry.npmmirror.com
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ──────────────── Stage 2: 运行时 ────────────────
FROM python:3.12-slim AS runtime

# Debian apt 换阿里源（国内拉 deb.debian.org 极慢；海外部署可注释掉）
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' \
        /etc/apt/sources.list.d/debian.sources 2>/dev/null \
    || sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' \
        /etc/apt/sources.list 2>/dev/null \
    || true

# 系统依赖：libssl/libffi 给 pip 编译用；sqlite3 给 ecs-backup.sh 用；
# tini 让 PID 1 正确收信号（compose stop 不会 kill -9）
RUN apt-get update && apt-get install -y --no-install-recommends \
        libssl-dev libffi-dev sqlite3 ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# pip 走清华源（国内提速；海外部署改回默认即可）
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

# 先装依赖（利用 docker layer cache）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 拷代码
COPY app/         /app/app/
COPY database/    /app/database/
COPY services/    /app/services/
COPY scripts/     /app/scripts/
COPY alembic.ini  /app/alembic.ini
# 注：迁移脚本位于 database/migrations/，由 alembic.ini 的 script_location 指向

# 拷前端产物
COPY --from=frontend /build/frontend/dist /app/frontend/dist

# 注意：不预装 Playwright/Patchright 的浏览器（chromium ≈ 300MB）；
# 若需启用 SSRN 抓取，在运行容器内执行：
#   docker compose exec app python -m patchright install chromium

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    KB_BIND_HOST=0.0.0.0

EXPOSE 5000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "scripts/serve.py"]
