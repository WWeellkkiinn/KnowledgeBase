# KnowledgeBase — 学术文献网络分析系统

以一篇论文为起点，自动展开引用网络、可视化关系图、监控新被引文献、生成跨论文综述。

---

## 功能概览

### Web UI（浏览器访问 `http://localhost:5173`）

| 页面 | 功能 |
|------|------|
| **概览 / Dashboard** | 论文总数、**运行中/队列/失败任务计数**（含 upload + track 任务）、活跃订阅、未读 Inbox |
| **论文库** | 核心 / 探索库双层级；**Google 风格分页**（固定 9 槽位，输入页码跳转）；**右上角"上传 PDF"按钮**（多论文同时上传，后台 worker 异步处理）；批量移库 / 删除 |
| **论文详情** | 结构化元数据；内容精炼（AI 提取的研究问题 / 方法 / 关键发现）；引用/被引列表（cache 命中秒回，cache miss 时显示"后台处理中"提示框可关闭页面）；**加载更多分页**；BibTeX 下载 |
| **引用图** | Cytoscape 网络图，仅显示核心库；节点按期刊 Tier 着色；点击跳详情 |
| **综述** | 勾选若干篇 + 关注维度 → 流式综述（调 Ollama） |
| **订阅** | 论文被引 / 作者新作 / 话题搜索三类订阅，定时跑 |
| **失败诊断** | 下载失败的引用汇总 |

### PDF 上传管线（Web UI 一键）

论文库右上角"上传 PDF"按钮：
1. 流式上传到 `papers/<stem>_<sha1[:8]>/<stem>_<sha1[:8]>.pdf`，sha1 + DOI 双重去重
2. 后端入队 `upload_pipeline` 任务，立即返回 task_id
3. 后台 worker 串行跑：**MinerU 云 API** PDF→Markdown → 抽 Title → DOI 反查 → Crossref 元数据 → Journal Tier → 引用抽取
4. Dashboard 实时显示任务进度，详情页自动刷新

无需 CLI 介入。原 `scripts/run_analysis_ui.py` 也保留可用。

### CLI（分析新论文，写入数据库）

| 命令 | 功能 |
|------|------|
| `pdf2md.py` | PDF → Markdown（调 MinerU） |
| `run_analysis_ui.py` | 单篇论文三阶段分析：内容分析 → 引用提取 → PDF 批量下载 |
| `search_refs.py` | 查询单篇论文元数据 + PDF 链接（调试用） |
| `download_pdf.py` | 下载单个 PDF（调试用） |

> CLI 负责"分析入库"，Web 负责"查看 + 引用追踪 + 监控 + 综述"。两者共享同一个 SQLite 数据库。

---

## 快速开始

### 前置条件

- Python 3.12（conda 环境）
- Node.js 18+
- Ollama 推理服务（端点通过 `KB_OLLAMA_URL` 环境变量配置，默认 `http://localhost:11434`；用于 AI 精炼 / 综述）
- **MinerU 云 API**：默认走 [mineru.net](https://mineru.net) 公网，需注册账号拿 Bearer token
  填到 `.env` 的 `KB_MINERU_API_KEY`；也可改 `KB_PDF2MD_PROVIDER=local` 走局域网 MinerU

### 1. 安装依赖

```bash
conda create -n kb python=3.12 -y
conda activate kb
pip install -r requirements.txt

cd frontend && npm install && cd ..
```

### 2. 初始化数据库

```bash
alembic upgrade head
python scripts/migrate_to_db.py   # 把现有 papers/ 目录里的论文导入数据库（首次跑一次）
```

### 3. 启动服务

> **Windows 注意**：`conda activate` 在 Git Bash 中无效，必须用 kb 环境的完整 Python 路径。
> 以下命令均在 **PowerShell** 中运行。

**终端 1 — Flask 后端：**
```powershell
cd C:\dev\KnowledgeBase
&lt;path-to-conda-env&gt;\python.exe scripts/serve.py
# 监听 http://127.0.0.1:5000，调度器自动启动
```

**终端 2 — Vite 前端：**
```powershell
cd C:\dev\KnowledgeBase\frontend
npm run dev    # 监听 http://localhost:5173
```

打开 `http://localhost:5173` 即可使用 Web UI。

#### 重启后端（不重启前端）

```powershell
# 1. 找到并杀掉占用 5000 端口的进程
Stop-Process -Id (Get-NetTCPConnection -LocalPort 5000).OwningProcess -Force

# 2. 重新启动（需在新 PowerShell 窗口或等待上条完成）
cd C:\dev\KnowledgeBase
&lt;path-to-conda-env&gt;\python.exe scripts/serve.py
```

#### 常见失败原因

| 症状 | 原因 | 解决 |
|------|------|------|
| `conda activate` 报错 | Git Bash 不支持 conda activate | 改用 PowerShell |
| `flask: command not found` | 用了 base conda 而不是 kb 环境 | 用完整路径 `&lt;path-to-conda-env&gt;\python.exe` |
| 500 / 端口已被占用 | 旧进程未退出 | 先 `Stop-Process` 再启动 |
| 调度器未启动 | 用 `flask run` 而非 `serve.py` | 必须用 `python scripts/serve.py`，它会自动设 `KB_ENABLE_SCHEDULER=1` |

---

## 分析新论文（CLI 工作流）

### Step 1：把 PDF 放进项目

```
papers/
  my_paper/
    my_paper.pdf    ← 手动放这里
```

### Step 2：PDF 转 Markdown

```bash
python scripts/pdf2md.py papers/my_paper/my_paper.pdf
# 输出：papers/my_paper/my_paper.md
```

### Step 3：运行三阶段分析

```bash
python scripts/run_analysis_ui.py papers/my_paper/my_paper.md --focus "研究方法"
# 自动打开 http://localhost:8765 显示实时进度
# 或加 --headless 跳过 UI（脚本调用时）
```

完成后生成：
- `analysis_insight.md` — 论文内容分析
- `analysis_refs.md` — 高相关引用清单
- `refs/*.pdf` — 自动下载的引用 PDF
- `refs_failed.md` — 下载失败清单（有则生成）

论文自动写入数据库，刷新 Web UI 即可看到。

---

## 引用追踪（Web UI）

进入核心论文详情页，前向（被引用）+ 后向（参考文献）**自动触发**；流程是**异步**的：

```
浏览器 → POST /papers/N/forward-track
                    │
            cache 命中？
              ├─ 是 → 200 + 分页数据（毫秒，gzip 后通常 <100KB）
              └─ 否 → 202 + {task_id}  ← 用户看到"后台处理中"
                       │
                       └─ worker 异步跑 SS + OpenAlex（30-90s）
                          → 写 cache → 推 socket done 事件
                          → 前端自动重发 → 命中 cache 拿到富数据
```

**优势：** 首次冷查询不阻塞用户，刷新页面 / 切走 / 关闭都不影响后台任务；Dashboard 实时显示进度。

### 缓存 + 每日自动刷新

- **后向**（参考文献，发表后不变）：永久缓存
- **前向**（被引用，会变化）：8 天 TTL
- **每日夜间流水线第一步**（北京 02:00 启动）：扫描核心库，cache 缺失 / forward > 7 天的论文自动入队刷新。stub 库不刷。
- **同篇仅刷一次**：流水线跳过已有 pending 任务的论文
- 全局并发 track 任务上限 20，超过返回 503 让用户稍后再试

### 数据来源

| 方向 | 来源 |
|------|------|
| 后向 | Semantic Scholar + OpenAlex + Crossref（三源并行去重） |
| 前向 | Semantic Scholar + OpenAlex（双源并行） |

### 探索库

探索库论文仅展示已入库引用关系，被引量不统计。如需，先移至核心库。

### 全量批量抓取

```bash
# 对所有核心论文重新抓取引用（凌晨跑，无上限）
python scripts/fetch_all_citations.py

# 仅前向 / 仅后向
python scripts/fetch_all_citations.py --forward-only
python scripts/fetch_all_citations.py --backward-only

# 清空缓存强制重抓（需输入 yes 确认）
python scripts/fetch_all_citations.py --clear-cache
```

---

## 订阅监控（自动发现新论文）

**Subscriptions** 页面可以设置三种订阅，定时自动跑：

| 类型 | 用途 | 需要填写 |
|------|------|---------|
| `paper_citations` | 监控某篇论文有没有新被引用 | DOI |
| `author_works` | 监控某作者有没有新发表 | 作者 ID（OpenAlex/SS） |
| `topic_search` | 监控某话题有没有新论文 | 查询词 |

**使用流程：**
1. 点「新建订阅」，选类型、填参数、设触发周期（默认每 7 天）
2. 保存后订阅自动激活，定时在后台运行
3. 有新发现时 Dashboard 顶部出现红点（Inbox 未读数）
4. 打开 **Dashboard** → Inbox 列表，点击查看新论文详情
5. 不需要时可在 Subscriptions 页暂停（paused）或删除

### 每日夜间流水线

每天北京时间 **02:00** 自动启动，四步全串行，上一步完成才进下一步：

| 步骤 | 做什么 |
|------|--------|
| 1. 拉取 | 各订阅按 cron 周期从 OpenAlex / arXiv 拉新论文；同时检查核心库 forward cache，超 7 天的论文入队刷新被引数 |
| 2. 评分 | 对所有未评分的订阅结果（`SubscriptionResult`）调 LLM，结合订阅的研究兴趣描述打相关度分（0–1），同时生成推荐理由、中文标题、标签等 |
| 3. 发邮件 | 取 score ≥ 0.65 的结果，按订阅分组渲染 HTML 邮件，发送给配置邮箱 |
| 4. 分析论文 | 对全库有摘要但尚未 AI 分析的论文批量生成摘要/标签（无时间压力，可跑到天亮） |

> 评分基于各订阅的 `description`（研究兴趣描述）；同一篇论文被两个不同订阅命中时，会产出两份独立评分结果。

---

## 综述生成（跨论文分析）

**Review** 页面可以对库内已分析的论文做跨论文比较：

1. 在左侧列表勾选若干篇已分析的论文（至少 1 篇）
2. 在「关注维度」输入框填写关注点，如「研究方法」「数据来源」「政策含义」
3. 点「生成综述」，右侧流式输出综述内容（Markdown 渲染）
4. 中途可点「取消」终止；生成完成后可重新勾选论文再次生成

综述结构：先对每篇论文生成方法摘要（round 1），再综合得出共识 / 分歧 / 演化路径（round 2）。

---

## 下载失败处理

分析过程中下载失败的引用会自动记录到各论文目录的 `refs_failed.md`。

**Web UI 的 Failures 页面**把所有失败条目汇总到一起：
- 按原因分类：付费墙（403）/ 非 PDF / 浏览器超时 / 未找到
- 按论文筛选
- 点击论文名跳转到对应的论文详情页

**手动补下载：** 根据 `refs_failed.md` 里的 DOI 或 pdf_url，手动下载后放入对应的 `papers/<stem>/refs/` 目录，文件名保持 `NN_作者_年份.pdf` 格式。

---

## BibTeX / 引用导出

论文详情页右上角有「下载 BibTeX」按钮（需要有 DOI），也可通过 API 批量导出：

```bash
# 全库 BibTeX（直接在浏览器访问或 curl 下载）
curl http://localhost:5000/api/citations.bib -o kb-all.bib

# 单篇 BibTeX
curl http://localhost:5000/api/papers/<id>/citations.bib -o paper.bib
```

首次导出时后端自动生成 BibTeX 条目并缓存；可通过「刷新引用」按钮强制重新生成。

---

## PDF 下载搜索链

给定标题 + DOI，按顺序逐源搜索，有 PDF 链接即返回：

```
DOI 路径：Unpaywall → OpenAlex(DOI) → Semantic Scholar(DOI)
           ↓ 无结果或 pdf_url 为空
标题路径：OpenAlex → Semantic Scholar → arXiv → RePEC → CORE → Zenodo → PubMed → Google Scholar
```

- 找到元数据但无 PDF 时**继续找下一源**（不提前放弃）
- 所有来源均做标题相似度验证（阈值 0.80），防止误匹配
- Zenodo：开放获取仓库，适合预印本和数据集
- PubMed/PMC：生物医学方向，有开放获取 PDF 时直接返回

下载 handler（`scripts/downloaders/`）：

| 触发 | Handler | 策略 |
|------|---------|------|
| `nber.org` | `nber.py` | URL 格式转换 |
| `ssrn.com` | `ssrn.py` | patchright + Cloudflare Turnstile 自动点击 |
| 其他 | `generic.py` | httpx → landing page → Unpaywall fallback |

**SSRN 下载需要提前启动 Chrome：**
```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir=.cache\real_profile
# 启动后访问 https://www.ssrn.com/ 一次即可
```

---

## 目录结构

```
KnowledgeBase/
  app/                          ← Flask Web 应用
    routes/api.py               ← REST API（papers / tasks / subscriptions / reviews / failures 等）
    sockets/progress.py         ← Socket.IO 实时进度推送
  services/                     ← 业务服务层
    _track_base.py              ← 前/后向追踪共享基类（缓存、图写入逻辑）
    reference_fetcher.py        ← SS + OpenAlex API 封装（fetch_cited_by / fetch_references）
    graph_writer.py             ← 追踪结果写入 papers + edges 表
    forward_track_service.py    ← 前向追踪（谁引用了这篇）
    backward_track_service.py   ← 后向追踪（这篇引用了哪些）
    analysis_service.py         ← 三阶段分析流水线
    subscription_service.py     ← 订阅调度（APScheduler）
    review_service.py           ← 跨论文综述生成（map-reduce + Ollama）
    journal_service.py          ← 期刊质量评分
    citation_service.py         ← BibTeX 生成与导出
  database/
    models.py                   ← SQLAlchemy 模型（9 张表，含 BackwardTrackCache）
    migrations/                 ← Alembic 迁移文件
    seed/journals.json          ← 期刊 Tier 数据
  frontend/                     ← Vue 3 + Vite + Tailwind SPA
    src/pages/                  ← 概览 / 论文库 / 引用图 / 综述 / 订阅 / 失败诊断
    src/stores/                 ← Pinia 状态管理
    src/api/                    ← axios + Socket.IO 封装
  scripts/                      ← CLI 入口
    run_analysis_ui.py          ← 单篇分析
    pdf2md.py                   ← PDF → Markdown（调 MinerU）
    search_refs.py              ← 元数据搜索（8 个来源）
    download_pdf.py             ← PDF 下载分发器
    downloaders/                ← 下载 handler 插件
    extract_refs.py             ← 从 Markdown 解析引用列表
    cross_analysis.py           ← 跨论文数据汇总
    backfill_journals.py        ← 期刊质量数据补全
    config.py                   ← API Keys（不提交）
    migrate_to_db.py            ← 一次性迁移脚本
  tests/                        ← pytest 测试套件（156 个用例）
  papers/                       ← 所有论文产物（人类可读副本）
  kb.db                         ← SQLite 主数据库
  alembic.ini
```

---

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Flask 3 + Flask-SocketIO + SQLAlchemy 2 + APScheduler + **flask-limiter** + **flask-compress (gzip/brotli)** |
| 任务队列 | 自研 TaskQueue（`tasks` 表）+ 单 worker 线程 daemon；FIFO 全局公平 |
| 数据库 | SQLite（`kb.db`），WAL 模式 |
| 前端 | Vue 3.5 + Vite 5 + Tailwind CSS 3 + Pinia + Cytoscape.js |
| 引用 API | Semantic Scholar + OpenAlex + Crossref（service 层 ThreadPoolExecutor 并行）|
| LLM | Ollama（端点经 `KB_OLLAMA_URL` 配置；默认模型 `qwen3.6-27b`，可经 `KB_OLLAMA_MODEL` 覆盖）|
| PDF 转换 | **MinerU 云 API**（`mineru.net`，默认）；可切 `local` 走自托管 |
| HTTP 客户端 | httpx |

---

## 推理服务器

Ollama 推理跑在独立主机上，本仓库不预设主机地址 / SSH 凭证。通过 `KB_OLLAMA_URL`
环境变量配置端点（参考 `.env.example`）；若推理主机在内网，可用 frp 反向隧道
把端口映射回应用主机（参考 `deploy/README.md` + `frpc.toml.example`）。

### Ollama 日常操作（示例 alias）

```bash
ollama-up              # 启动容器 + 预热模型
ollama-down            # 停止容器，释放 GPU
ollama-status          # 查看状态
```

### 已部署模型

| 模型 | Ollama 名称 | GPU | thinking |
|------|------------|-----|---------|
| Qwen 3.6 27B | `qwen3.6-27b` | 单卡 GPU1 | ✅（`/no_think` 前缀开启，语义反转） |
| Gemma 4 31B | `gemma4-31b` | 双卡 GPU0+1 | ✅ |
| Qwen 3.5 27B | `qwen3.5-27b` | 双卡 | ✅ |

> ⚠️ qwen3.6-27b 的 `/think` 和 `/no_think` 前缀语义与直觉**相反**：`/no_think` = 开启思维链，`/think` = 关闭思维链。

### MinerU 启动

```bash
docker run -d --name mineru-api-kb \
  --gpus '"device=3"' -p 8000:8000 \
  -e MINERU_MODEL_SOURCE=local --ipc host \
  mineru:latest mineru-api --host 0.0.0.0 --port 8000
```

---

## 生产部署（Docker + frp）

把项目以 Docker Compose 方式部署到一台有公网 IP 的服务器，并通过 frp 反向隧道
连接内网 Ollama 主机。详见 [`deploy/README.md`](deploy/README.md)。

> 历史版本曾用 cpolar 内网穿透从 Windows 本地暴露公网；当前推荐 Docker + frp。
> 国内网络下 Tailscale / Cloudflare Tunnel 经常无法连接其控制面与中继。

### 安全前提

公网部署后所有请求（包括 Socket.IO）都必须带 `Authorization: Bearer <token>`，缺/错一律 401。`/`、`/assets/*`、`/login`、`/health`、`/favicon*` 是白名单（要让前端 SPA 能加载）。

| 环境变量 | 必填 | 说明 |
|----------|------|------|
| `KB_API_TOKEN` | ✅ | 访问令牌；用户在登录页输入此值 |
| `KB_SECRET_KEY` | ✅ | Flask session / Socket.IO 签名密钥 |
| `KB_TRUST_PROXY` | ✅ | 公网部署设 `1`，启用 ProxyFix；**仅当 Flask 绑 127.0.0.1 + 单跳可信代理（nginx）时安全** |
| `KB_MINERU_API_KEY` | 上传时必填 | MinerU 云 Bearer token（注册 [mineru.net](https://mineru.net) 获取） |
| `KB_OLLAMA_URL` | 否 | Ollama 端点；容器内默认 `http://host.docker.internal:11434` |
| `KB_OLLAMA_MODEL` | 否 | 默认 `qwen3.6-27b` |
| `KB_PDF2MD_PROVIDER` | 否 | `mineru-cloud`（默认）/ `local` |
| `KB_MINERU_API_URL` | 否 | 默认 `https://mineru.net` |
| `KB_MINERU_ALLOWED_HOSTS` | 否 | 预签名 URL host 白名单；默认含 mineru.net + cdn-mineru.openxlab.org.cn + MinerU 官方 OSS bucket |
| `KB_MAX_CONTENT_LENGTH` | 否 | 全局请求体上限，默认 60MB；**非上传路径** 通过 before_request 单独限到 256KB |
| `KB_ENABLE_SCHEDULER` | 否 | `serve.py` 入口自动设 `1` |
| `KB_DISABLE_UPLOAD_WORKER` | 否 | 测试用；置 1 跳过后台 worker 线程 |
| `KB_ALLOW_MULTI_WORKER` | 否 | 仅当切换到多 Flask 进程部署时设；自动禁用进程内 worker |

生成两个 token（≥32 字节）：

```bash
python -c "import secrets; print('KB_API_TOKEN=' + secrets.token_urlsafe(32))"
python -c "import secrets; print('KB_SECRET_KEY=' + secrets.token_urlsafe(32))"
```

两者职责分离：

- `KB_API_TOKEN` — 用户的"门票"，在 `/login` 页输入它；泄露则换值重启 Flask 即可吊销
- `KB_SECRET_KEY` — 服务器内部用（Flask session / Socket.IO polling 签名），永不出现在前端

### 速率限制（`flask-limiter`）

按客户端 IP 配额，防 token 泄露后的重放：

| 端点 | 配额 |
|------|------|
| 全局默认 | 120 / min |
| `POST /api/papers/<id>/forward-track` | 10 / min（同时全局 in-flight ≤ 20） |
| `POST /api/papers/<id>/backward-track` | 10 / min（同时全局 in-flight ≤ 20） |
| `POST /api/papers/<id>/ai-analyze` | 5 / min |
| `POST /api/papers/upload` | 5 / min（最大 50 MB / 文件） |
| `POST /api/reviews` | 3 / hour |
| `POST /api/digest/send` | 2 / hour |

> ⚠️ **单 worker 部署限定**：`flask-limiter` 用 `memory://` 存储，限速状态进程内独占。
> docker compose 默认走 `socketio.run` 单进程，符合假设。
> 若切 gunicorn 多 worker，必须改用 `redis://` 后端。
>
> ⚠️ **ProxyFix x_for 跳数**：代码 `x_for=1`，假设 nginx → Flask 单跳。
> 若上游链路再加 CDN/反代，攻击者可伪造 `X-Forwarded-For` 绕过 IP 限速。

### 生产启动（Docker Compose）

详见 [`deploy/README.md`](deploy/README.md)。一键流程：

```bash
cp .env.example data/.env && vim data/.env   # 填 token / 各类 key
docker compose up -d --build
docker compose logs -f app
```

浏览器访问 `http://<your-server-ip-or-domain>`，输入 `KB_API_TOKEN` 登录。

### 开发与生产并存

公网走打包产物（`frontend/dist/`，由 Dockerfile stage1 构建），日常开发仍可用
Vite dev server（`localhost:5173`）+ Flask（`localhost:5000`）。`KB_API_TOKEN` 未
设置时后端进入 dev mode 全放行，前端 axios 不注入 token，体验和原来一致。

---

## 已知限制

| 项目 | 说明 |
|------|------|
| PDF 下载成功率 | 受 OA 覆盖率限制，付费墙期刊无法自动下载；失败条目进失败诊断页面 |
| 引用追踪 API 限速 | Semantic Scholar 1 req/s（worker 内强制 0.8s 间隔）；OpenAlex 无强制限制但带 mailto |
| MinerU 云配额 | 注册账号每日有额度上限；CD 大量批量上传前查看 mineru.net 控制台 |
| 单 worker 假设 | TaskQueue.fetch_next 无 SELECT FOR UPDATE，进程内只能 1 个 worker 线程；多 Flask worker 须独立跑 worker 进程（自动守卫拒启） |
