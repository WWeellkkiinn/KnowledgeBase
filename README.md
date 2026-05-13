# KnowledgeBase — 学术文献网络分析系统

以一篇论文为起点，自动展开引用网络、可视化关系图、监控新被引文献、生成跨论文综述。

---

## 功能概览

### Web UI（浏览器访问 `http://localhost:5173`）

| 页面 | 功能 |
|------|------|
| **Dashboard** | 论文总数、运行任务、活跃订阅、未读 Inbox，一览全库状态 |
| **Papers** | 所有论文列表，按状态/来源过滤，点进去看详情、引用关系、前向追踪 |
| **Network** | Cytoscape 引用网络图，节点按期刊 Tier 着色（金/银/铜），点击跳详情 |
| **Review** | 勾选若干篇论文 + 输入关注维度，一键生成流式综述（调 Ollama） |
| **Subscriptions** | 创建订阅（论文被引 / 作者新作 / 话题搜索），定时自动检查 |
| **Failures** | 所有下载失败的引用汇总，按付费墙 / 非PDF / 超时等分类，方便批量处理 |

### CLI（分析新论文，写入数据库）

| 命令 | 功能 |
|------|------|
| `run_analysis_ui.py` | 单篇论文三阶段分析：内容分析 → 引用提取 → PDF 批量下载 |
| `expand.py` | 从根论文 BFS 递归展开，支持断点续跑 |
| `search_refs.py` | 查询单篇论文元数据 + PDF 链接（调试用） |
| `download_pdf.py` | 下载单个 PDF（调试用） |

> CLI 负责"写入"，Web 负责"查看 + 监控 + 综述"。两者共享同一个 SQLite 数据库。

---

## 快速开始

### 前置条件

- Python 3.12（conda 环境）
- Node.js 18+
- 远程服务器上 Ollama（`:13812`）和 MinerU（`:8000`）已启动

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

**终端 1 — Flask 后端：**
```bash
conda activate kb
python scripts/serve.py           # 监听 http://localhost:5000
```

**终端 2 — Vite 前端：**
```bash
cd frontend && npm run dev         # 监听 http://localhost:5173
```

打开 `http://localhost:5173` 即可使用 Web UI。

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

### Step 4（可选）：递归展开引用网络

```bash
# 展开 1 层（root + 它的所有引用）
python scripts/expand.py papers/my_paper/my_paper.pdf --focus "研究方法" --max-depth 1

# 展开 2 层，每层最多 5 篇（控制预算）
python scripts/expand.py papers/my_paper/my_paper.pdf --focus "研究方法" --max-depth 2 --max-breadth 5
```

支持断点续跑：已分析的论文会被跳过，Ctrl+C 后重跑不丢数据。

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
    analysis_service.py         ← 三阶段分析流水线
    forward_track_service.py    ← 前向追踪（SS + OpenAlex）
    subscription_service.py     ← 订阅调度（APScheduler）
    review_service.py           ← 跨论文综述生成（map-reduce + Ollama）
    journal_service.py          ← 期刊质量评分
    citation_service.py         ← BibTeX 生成与导出
  database/
    models.py                   ← SQLAlchemy 模型（8 张表）
    migrations/                 ← Alembic 迁移文件
    seed/journals.json          ← 期刊 Tier 数据
  frontend/                     ← Vue 3 + Vite + Tailwind SPA
    src/pages/                  ← Dashboard / Papers / Network / Review / Subscriptions / Failures
    src/stores/                 ← Pinia 状态管理
    src/api/                    ← axios + Socket.IO 封装
  scripts/                      ← CLI 入口（保留，行为不变）
    run_analysis_ui.py          ← 单篇分析
    expand.py                   ← BFS 递归展开
    pdf2md.py                   ← PDF → Markdown（调 MinerU）
    search_refs.py              ← 元数据搜索
    download_pdf.py             ← PDF 下载
    downloaders/                ← 下载 handler 插件
    config.py                   ← API Keys（不提交）
    migrate_to_db.py            ← 一次性迁移脚本
  papers/                       ← 所有论文产物（人类可读副本）
  kb.db                         ← SQLite 主数据库
  alembic.ini
```

---

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Flask 3 + Flask-SocketIO + SQLAlchemy 2 + APScheduler |
| 数据库 | SQLite（`kb.db`） |
| 前端 | Vue 3.5 + Vite 5 + Tailwind CSS 3 + Pinia + Cytoscape.js |
| LLM | Ollama（`http://<ollama-host>:13812`，模型 `qwen3.6-27b`） |
| PDF 转换 | MinerU API（`http://<ollama-host>:8000`） |
| HTTP 客户端 | httpx |

---

## 推理服务器（<ollama-host>）

```bash
ssh -i <home>/.ssh/<deploy-ssh-key> <deploy-user>@<ollama-host>
```

### Ollama 日常操作

```bash
ollama-up              # 启动容器 + 预热 qwen3.6-27b
ollama-down            # 停止容器，释放 GPU
ollama-status          # 查看状态
```

Windows 本地访问端点：`http://<ollama-host>:13812`

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

## 已知限制

| 项目 | 说明 |
|------|------|
| PDF 下载成功率 | 受 OA 覆盖率限制，付费墙期刊无法自动下载；失败条目进 Failures 页面 |
| 新论文分析 | 目前只能通过 CLI 触发，Web UI 没有"上传并分析"入口 |
| BFS 展开 | 只能通过 CLI 触发，Web UI 没有"展开引用网络"入口 |
