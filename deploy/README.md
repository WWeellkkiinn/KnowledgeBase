# KnowledgeBase ECS 部署手册

目标：把 KnowledgeBase（Flask + SocketIO + SQLite + Vue 单页）部署到任一台
**Ubuntu 22.04 + Docker 29 + Compose v5** 的服务器。LLM 走 OpenAI 兼容的公网中转 API。

最低硬件：2 vCPU / 1.6 GB RAM（建议同时配 2G swap）。
对外端口：8080（nginx 反代到 app，宿主 80 若空闲可改回）。

> 文档中的 `<YOUR_ECS_HOST>` / `<YOUR_DEPLOY_USER>` 是占位，部署时替换为实际值。

---

## 1. 首次部署

### Wave A — ECS 侧基础

```bash
ssh <YOUR_DEPLOY_USER>@<YOUR_ECS_HOST>

# 加 2G swap（1.6G 内存机型必须）
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# 放行 nginx 对外端口（若宿主 80 空闲可改 80/tcp）
ufw allow 8080/tcp

# 准备部署目录
mkdir -p /opt/kb && cd /opt/kb
git clone <YOUR_REPO_URL> .
mkdir -p data/papers data/logs backup
# .env 放仓库根目录（/opt/kb/.env），不要放进 data/，
# 否则会被 ./data:/app/data 挂载暴露给 app 容器内任何遍历 papers 父目录的代码。
cp .env.example .env
chmod 600 .env
vim .env   # 填入真实 token / key / LLM 中转 API 凭证
```

`.env` 必填项：

- `KB_API_TOKEN` — 用户登录令牌（≥32 字节随机）
- `KB_SECRET_KEY` — Flask session / Socket.IO 签名密钥
- `KB_TRUST_PROXY=1` — nginx 单跳代理时启用 ProxyFix
- `KB_ENABLE_SCHEDULER=1` — 启动后台调度
- `KB_MINERU_API_KEY` — MinerU 云 API（PDF→MD 必需）
- `CHAT_API_BASE` / `CHAT_API_KEY` / `CHAT_MODEL` — OpenAI 兼容 LLM 中转 API
- `UNPAYWALL_EMAIL` / `CORE_API_KEY` / `SS_API_KEY` / `EASYSCHOLAR_SECRET_KEY` — 外部学术 API 凭证

### Wave B — 启动应用

```bash
cd /opt/kb
docker compose build              # 首次构建较慢（前端 npm ci）
docker compose up -d
docker compose logs -f app        # 看 SocketIO 启动日志，确认无堆栈
```

浏览器访问 `http://<YOUR_ECS_HOST>:8080`，输入 `KB_API_TOKEN` 登录。

### Wave C — 开发机：装 pre-commit hook（强烈建议）

```bash
bash deploy/install-hooks.sh   # 仓库根目录运行一次
```

之后每次 `git commit` 会自动扫 staged 改动，命中真 token / 真公网 IP / 真邮箱 /
SSH key 名 / 敏感文件名时拦下提交。规则见 `deploy/git-hooks/pre-commit.py`。
误报豁免：在该行末加 `# noqa: secrets`；紧急绕过：`git commit --no-verify`。

### Wave D — 备份 cron

```bash
chmod +x /opt/kb/deploy/ecs-backup.sh
crontab -e
15 3 * * * /opt/kb/deploy/ecs-backup.sh >> /opt/kb/data/logs/backup.log 2>&1
```

---

## 2. 日常更新（双通道同步）

代码走 GitHub，私密数据走 scp：

```bash
# 公共代码改动
git commit -am "feat: xxx"
ECS_HOST=<YOUR_DEPLOY_USER>@<YOUR_ECS_HOST> deploy/sync.sh

# 改了非代码（nginx.conf / docker-compose.yml）
ECS_HOST=<YOUR_DEPLOY_USER>@<YOUR_ECS_HOST> deploy/sync.sh --no-rebuild

# 顺手把本地 .env 推过去
ECS_HOST=<YOUR_DEPLOY_USER>@<YOUR_ECS_HOST> deploy/sync.sh --env
```

---

## 3. 换 token / 改 .env

```bash
vim .env                                                                # 本地改
ECS_HOST=<YOUR_DEPLOY_USER>@<YOUR_ECS_HOST> deploy/sync.sh --env --no-rebuild
```

`KB_API_TOKEN` 与 `KB_SECRET_KEY` 等同对外密码，泄露立即换。换 `KB_SECRET_KEY`
会让所有现有 session 失效，是预期行为。

---

## 4. 日志

```bash
docker compose logs -f --tail=200 app           # Flask + APScheduler
docker compose logs -f --tail=200 nginx         # 访问日志
ls /opt/kb/data/logs/                           # app 落盘日志（如有）
```

---

## 5. 备份与恢复

备份位置：`/opt/kb/backup/kb-YYYY-MM-DD-HHMM.db`，自动保留 14 天。

恢复：

```bash
docker compose stop app
cp /opt/kb/backup/kb-2026-05-14-0315.db /opt/kb/data/kb.db
rm -f /opt/kb/data/kb.db-wal /opt/kb/data/kb.db-shm   # WAL 已合并入备份
docker compose up -d app
```

---

## 6. 故障排查

| 症状 | 排查 |
| --- | --- |
| AI 标签 / 精炼报错 | 检查 `CHAT_API_BASE` 是否可达：`docker compose exec app curl -sS "$CHAT_API_BASE/models" -H "Authorization: Bearer $CHAT_API_KEY"` |
| 上传 PDF 卡 413 | `nginx.conf` `client_max_body_size 220m`（与 `KB_MINERU_ZIP_MAX_BYTES=209715200` 对齐），再大需同时调两边 |
| app 容器 OOM 重启 | `docker compose stats`；2C/1.6G 机型避免同时跑多个抓取任务，必要时调 `mem_limit` |
| 80 端口被占 | `ss -lntp \| grep :80` 找占用进程；或改 compose 把 nginx 改成 `8080:80` |
| `git pull` 拒绝 | ECS 上有本地改动，先 `git stash` 或回滚 |
