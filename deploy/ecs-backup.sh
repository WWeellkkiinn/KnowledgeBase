#!/usr/bin/env bash
# 每日 PostgreSQL 备份（在线，无需停服）。保留最新 7 个，每天一个。
# 部署：chmod +x 后挂 cron：  15 3 * * * /opt/kb/deploy/ecs-backup.sh >> /opt/kb/data/logs/backup.log 2>&1
set -euo pipefail

KB_ROOT="${KB_ROOT:-/opt/kb}"
CONTAINER="${KB_DB_CONTAINER:-kb-db-1}"
DEST="${KB_ROOT}/backup"
KEEP=7
LOCK="${DEST}/.ecs-backup.lock"

mkdir -p "$DEST"

# 并发锁：防止重叠执行
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[$(date -Iseconds)] ERROR: backup already running" >&2
  exit 1
fi

# 容器必须在运行
if ! docker ps --format "{{.Names}}" | grep -qx "$CONTAINER"; then
  echo "[$(date -Iseconds)] ERROR: container $CONTAINER not running" >&2
  exit 1
fi

OUT="${DEST}/kb-$(date +%F-%H%M%S).dump"
TMP="${OUT}.tmp.$$"
cleanup() { rm -f -- "$TMP"; }
trap cleanup EXIT

# 原子写入：先写临时文件，显式捕获 pg_dump 失败
if ! docker exec "$CONTAINER" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$TMP"; then
  echo "[$(date -Iseconds)] ERROR: pg_dump failed" >&2
  exit 1
fi

# 校验：非空 且 pg_restore 能解析目录
if [[ ! -s "$TMP" ]] || ! docker exec -i "$CONTAINER" pg_restore -l >/dev/null 2>&1 < "$TMP"; then
  echo "[$(date -Iseconds)] ERROR: invalid backup" >&2
  exit 1
fi

mv -f -- "$TMP" "$OUT"
trap - EXIT
echo "[$(date -Iseconds)] backup -> ${OUT} ($(du -h "$OUT" | cut -f1))"

# 7 天滚动：按文件名(=时间)字典序，仅保留最新 KEEP 个
shopt -s nullglob
backups=("${DEST}"/kb-*.dump)
if (( ${#backups[@]} > KEEP )); then
  for (( i = 0; i < ${#backups[@]} - KEEP; i++ )); do
    rm -f -- "${backups[$i]}"
  done
fi
