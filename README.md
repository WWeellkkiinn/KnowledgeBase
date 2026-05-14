# KnowledgeBase — 学术文献网络分析系统

以一篇论文为起点，自动展开引用网络、可视化关系图、监控新被引文献、生成跨论文综述。

---

## 功能概览

### Web UI（浏览器访问 `http://localhost:5173`）

| 页面 | 功能 |
|------|------|
| **概览** | 论文总数、运行任务、活跃订阅、未读 Inbox，一览全库状态 |
| **论文库** | 所有论文列表，按状态/来源过滤 |
| **论文详情** | 基本信息、DB 引用出边（参考文献）、后向追踪（API 查它引用了谁）、前向追踪（API 查谁引用了它）、BibTeX 下载；追踪结果自动写入引用图 |
| **引用图** | Cytoscape 引用网络图，节点按期刊 Tier 着色（金/银/铜），点击跳详情 |
| **综述** | 勾选若干篇论文 + 输入关注维度，一键生成流式综述（调 Ollama） |
| **订阅** | 创建订阅（论文被引 / 作者新作 / 话题搜索），定时自动检查 |
| **失败诊断** | 所有下载失败的引用汇总，按付费墙 / 非PDF / 超时等分类，方便批量处理 |

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

---

## 引用追踪（Web UI）

论文分析入库后，在论文详情页可以通过 API 查询引用关系，**结果自动写入 papers + edges 表，引用图即时更新**。

### 后向追踪（这篇论文引用了哪些论文）

1. 打开**论文库**，点进任意一篇有 DOI 的论文
2. 切换到**后向引用**标签页
3. 点击「查询后向引用」

返回：被查论文的参考文献列表，每条包含标题、作者、年份、DOI、摘要、来源（SS / OpenAlex）。

### 前向追踪（谁引用了这篇论文）

1. 同上，切换到**被引用**标签页
2. 点击「触发前向追踪」

两种追踪均同时查询 Semantic Scholar 和 OpenAlex，结果去重合并。7 天内同一 DOI 命中缓存，不重复请求。没有 DOI 的论文无法触发（按钮置灰）。

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
| PDF 下载成功率 | 受 OA 覆盖率限制，付费墙期刊无法自动下载；失败条目进失败诊断页面 |
| 新论文分析 | 目前只能通过 CLI 触发，Web UI 没有"上传并分析"入口 |
| 引用追踪 API 限速 | Semantic Scholar 100 次/5分钟；OpenAlex 无强制限制但建议保留 mailto |
