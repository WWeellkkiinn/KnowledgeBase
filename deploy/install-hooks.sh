#!/usr/bin/env bash
# 把 deploy/git-hooks/pre-commit 链接到 .git/hooks/pre-commit
# 用法：从仓库根目录运行 `bash deploy/install-hooks.sh`
set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"

SRC="$ROOT/deploy/git-hooks/pre-commit"
DST="$ROOT/.git/hooks/pre-commit"

if [[ ! -f "$SRC" ]]; then
  echo "ERROR: 找不到 $SRC" >&2
  exit 1
fi

# 备份既有 hook
if [[ -e "$DST" && ! -L "$DST" ]]; then
  mv "$DST" "${DST}.bak.$(date +%s)"
  echo "已备份既有 hook 到 ${DST}.bak.*"
fi

# 直接 copy（Windows Git Bash 软链兼容性差）
cp "$SRC" "$DST"
chmod +x "$DST"
# pre-commit.py 也要可执行（虽然由 bash 包装调用，但便于直接调试）
chmod +x "$ROOT/deploy/git-hooks/pre-commit.py" 2>/dev/null || true

echo "✅ pre-commit hook 已安装到 $DST"
echo "   验证：随便改一行 + git add + git commit，应触发扫描"
echo "   绕过：git commit --no-verify（仅在确认是误报时用）"
