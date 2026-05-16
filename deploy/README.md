# KnowledgeBase ECS 部署手册

目标：把 KnowledgeBase（Flask + SocketIO + SQLite + Vue 单页）部署到任一台
**Ubuntu 22.04 + Docker 29 + Compose v5** 的服务器，并通过 frp 反向隧道连接
一台**仅出网、不公开服务端口**的 Ollama 推理主机。

最低硬件：2 vCPU / 1.6 GB RAM（建议同时配 2G swap）。
对外端口：8080（nginx 反代到 app，宿主 80 若空闲可改回）、7000（frps 控制面）。
本机回环：13813（或你 Ollama 的实际端口，frp 隧道映射点）。

> 文档中的 `<YOUR_ECS_HOST>` / `<YOUR_OLLAMA_HOST>` / `<YOUR_DEPLOY_USER>` 是占位，
> 部署时替换为你的实际值。

---

## 1. 首次部署

### Wave A — ECS 侧基础

```bash
ssh <YOUR_DEPLOY_USER>@<YOUR_ECS_HOST>

# 加 2G swap（1.6G 内存机型必须）
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# 放行 frp 控制端口（公网入口）
# 强烈建议限制来源 IP：仅放行 Ollama 主机的出口公网 IP，避免 7000 暴露给全网扫描。
# 如果 Ollama 主机出口 IP 固定（已知 <YOUR_OLLAMA_EGRESS_IP>）：
#   ufw allow from <YOUR_OLLAMA_EGRESS_IP> to any port 7000 proto tcp comment 'frps from ollama host'
# 否则（运营商动态 IP）退化为全网放开，依赖 frps token + 后续 TLS 鉴权：
ufw allow 7000/tcp

# 放行 docker bridge → 宿主机的隧道端口（容器走 host.docker.internal 访问 frps 转出来的 Ollama）
# 注意：必须用 source = 172.16.0.0/12（docker 默认私网池），不能省略 source，否则等于公网开放。
# 端口随 frpc.toml 里 remotePort 调整（默认 13813，按你 Ollama 端口）。
ufw allow from 172.16.0.0/12 to any port 13813 proto tcp comment 'kb-app -> frps tunnel'

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
vim .env   # 填入真实 token / key / 你的 OLLAMA_URL
```

`.env` 必填项：

- `KB_API_TOKEN` — 用户登录令牌（≥32 字节随机）
- `KB_SECRET_KEY` — Flask session / Socket.IO 签名密钥
- `KB_TRUST_PROXY=1` — nginx 单跳代理时启用 ProxyFix
- `KB_ENABLE_SCHEDULER=1` — 启动后台调度
- `KB_MINERU_API_KEY` — MinerU 云 API（PDF→MD 必需）
- `KB_OLLAMA_URL=http://host.docker.internal:11434` — 通过宿主 host-gateway 走 frp 隧道
- `UNPAYWALL_EMAIL` / `CORE_API_KEY` / `SS_API_KEY` — 外部学术 API 凭证

### Wave B — frp 隧道

生成强随机 token：

```bash
python3 -c "import secrets;print(secrets.token_urlsafe(32))"
```

把这个值同时写入：
- ECS 上 `/opt/kb/frps.toml` 的 `auth.token`
- Ollama 主机上 `frpc.toml`（由 `frpc.toml.example` 复制）的 `auth.token`

在 Ollama 主机：

```bash
mkdir -p ~/frp && cd ~/frp
# 下载与 frps 同版本的 frpc 二进制
# https://github.com/fatedier/frp/releases （Linux amd64）
cp /path/to/repo/frpc.toml.example frpc.toml
vim frpc.toml   # 填入 serverAddr / token / localPort
./frpc -c frpc.toml   # 前台测试一次
```

确认 ECS 上 `curl http://127.0.0.1:<REMOTE_PORT>/api/tags` 能返回 Ollama 模型列表后，
配置开机自启：

```bash
crontab -e
@reboot sleep 30 && $HOME/frp/frpc -c $HOME/frp/frpc.toml >> $HOME/frp/frpc.log 2>&1
```

> 如果 Ollama 主机有 sudo + `loginctl enable-linger`，可改用 `deploy/frpc.service`
> 走 systemd `--user`，稳定性更好。

### Wave C — 启动应用

```bash
cd /opt/kb
docker compose build              # 首次构建较慢（前端 npm ci）
docker compose up -d
docker compose logs -f app        # 看 SocketIO 启动日志，确认无堆栈
```

浏览器访问 `http://<YOUR_ECS_HOST>:8080`，输入 `KB_API_TOKEN` 登录。

### Wave D — 开发机：装 pre-commit hook（强烈建议）

```bash
bash deploy/install-hooks.sh   # 仓库根目录运行一次
```

之后每次 `git commit` 会自动扫 staged 改动，命中真 token / 真公网 IP / 真邮箱 /
SSH key 名 / 敏感文件名时拦下提交。规则见 `deploy/git-hooks/pre-commit.py`。
误报豁免：在该行末加 `# noqa: secrets`；紧急绕过：`git commit --no-verify`。

### Wave E — 备份 cron

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
docker compose logs -f --tail=200 frps          # 隧道事件
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
| AI 标签 / 精炼报错 502 / connect | ECS 上 `curl http://127.0.0.1:<REMOTE_PORT>/api/tags`；不通查 frpc 日志（Ollama 主机），重启 frpc |
| 容器内调 Ollama 失败 | 验证 `docker compose exec app curl http://host.docker.internal:<REMOTE_PORT>/api/tags`；不通检查 compose `extra_hosts` 是否生效 |
| 上传 PDF 卡 413 | `nginx.conf` `client_max_body_size 220m`（与 `KB_MINERU_ZIP_MAX_BYTES=209715200` 对齐），再大需同时调两边 |
| app 容器 OOM 重启 | `docker compose stats`；2C/1.6G 机型避免同时跑多个抓取任务，必要时调 `mem_limit` |
| 80 端口被占 | `ss -lntp \| grep :80` 找占用进程；或改 compose 把 nginx 改成 `8080:80` |
| frps 拒连 | token 不匹配；`docker compose logs frps` 看 `auth failed` |
| frpc 反复重连，frps 日志报 `tls handshake` | 客户端 `frpc.toml` 的 `transport.tls.enable` 必须为 `true`（与 frps 端 `force=true` 配套）；客户端 frpc 二进制必须用 fatedier 官方 release（见 Wave B 下载链接），切勿混用第三方包装 |
| frpc 突然连不上，frps 日志**完全没有新连接**，抓包看 ECS:7000 收到 SYN 但被 `[UFW BLOCK]` | Ollama 主机运营商 NAT 出口 IP 漂移，不再匹配 ufw 白名单。恢复：①`ssh welkin@... 'curl -s ifconfig.me'` 取新出口 IP；②ECS 上 `ufw allow from <新IP> to any port 7000 proto tcp comment 'frps from ollama egress'`；③`ufw status numbered` 找到旧 IP 那条 `ufw delete <序号>`；④确认 frpc 自动重连成功 |
| `git pull` 拒绝 | ECS 上有本地改动，先 `git stash` 或回滚 |
