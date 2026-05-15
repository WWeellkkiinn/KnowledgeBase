#!/usr/bin/env bash
# 每日 SQLite 备份（在线，无需停服）。
# 部署：
#   chmod +x /opt/kb/deploy/ecs-backup.sh
#   crontab -e
#     15 3 * * * /opt/kb/deploy/ecs-backup.sh >> /opt/kb/data/logs/backup.log 2>&1
set -euo pipefail

KB_ROOT="${KB_ROOT:-/opt/kb}"
DB="${KB_ROOT}/data/kb.db"
DEST="${KB_ROOT}/backup"
KEEP_DAYS=14

mkdir -p "$DEST"

if [[ ! -f "$DB" ]]; then
  echo "[$(date -Iseconds)] ERROR: $DB not found"; exit 1
fi

OUT="${DEST}/kb-$(date +%F-%H%M).db"
sqlite3 "$DB" ".backup '${OUT}'"
# 校验产出非空
if [[ ! -s "$OUT" ]]; then
  echo "[$(date -Iseconds)] ERROR: backup produced empty file $OUT" >&2
  rm -f "$OUT"
  exit 1
fi
echo "[$(date -Iseconds)] backup -> ${OUT} ($(du -h "$OUT" | cut -f1))"

# 清理超过 KEEP_DAYS 天的旧备份
find "$DEST" -maxdepth 1 -name 'kb-*.db' -type f -mtime "+${KEEP_DAYS}" -print -delete
