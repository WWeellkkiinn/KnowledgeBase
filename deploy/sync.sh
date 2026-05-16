#!/usr/bin/env bash
# 同步本地改动到 ECS 并重启 app 服务。
#
# 用法：
#   ECS_HOST=user@your-ecs-host deploy/sync.sh
#   ECS_HOST=user@your-ecs-host deploy/sync.sh --env            # 顺手把 .env 推过去
#   ECS_HOST=user@your-ecs-host deploy/sync.sh --no-rebuild     # 不重建镜像
#
# 前置：本机 ssh 已配好对应 host 免密 / Deploy Key。
set -euo pipefail

if [[ -z "${ECS_HOST:-}" ]]; then
  echo "ERROR: 请通过环境变量提供 ECS_HOST=user@host（例如 root@1.2.3.4）。"
  exit 1
fi
ECS_PATH="${ECS_PATH:-/opt/kb}"
PUSH_ENV=0
REBUILD=1

for arg in "$@"; do
  case "$arg" in
    --env)         PUSH_ENV=1 ;;
    --no-rebuild)  REBUILD=0 ;;
    --no-env)      PUSH_ENV=0 ;;
    -h|--help)
      sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown flag: $arg"; exit 2 ;;
  esac
done

# 1. 本地 git 必须 clean，避免遗漏未提交改动
if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: 本地有未提交改动，请先 commit。"
  git status --short
  exit 1
fi

# 校验当前在主分支（避免误推 feature 分支后远端 pull 拉到不期望状态）
CUR_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$CUR_BRANCH" != "master" && "$CUR_BRANCH" != "main" ]]; then
  echo "WARN: 当前分支 $CUR_BRANCH（非 master/main）。继续？[y/N]"
  read -r answer
  [[ "$answer" == "y" || "$answer" == "Y" ]] || exit 1
fi

echo "==> git push"
git push

if [[ "$PUSH_ENV" == "1" ]]; then
  if [[ ! -f .env ]]; then
    echo "ERROR: 本地无 .env，无法 --env 推送。"; exit 1
  fi
  # .env 推到仓库根（与 docker-compose.yml 的 env_file: ./.env 对齐），
  # 不要落到 data/ 内——data/ 整个挂进容器，明文 token 会被遍历到。
  echo "==> scp .env -> ${ECS_HOST}:${ECS_PATH}/.env"
  scp -p .env "${ECS_HOST}:${ECS_PATH}/.env"
  ssh "$ECS_HOST" "chmod 600 ${ECS_PATH}/.env"
fi

if [[ "$REBUILD" == "1" ]]; then
  echo "==> ssh: git pull + compose up -d --build app"
  ssh "$ECS_HOST" "cd ${ECS_PATH} && git pull && docker compose up -d --build app && docker compose restart nginx"
else
  echo "==> ssh: git pull + restart app (no rebuild)"
  ssh "$ECS_HOST" "cd ${ECS_PATH} && git pull && docker compose restart app"
fi

echo "==> done. 查看日志: ssh ${ECS_HOST} 'docker compose -f ${ECS_PATH}/docker-compose.yml logs -f --tail=100 app'"
