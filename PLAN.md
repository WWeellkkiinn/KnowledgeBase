# KnowledgeBase 演进方案（方案 B：Web 应用化）

## 0. 决策摘要

- **演进方向**：从纯 CLI 升级为 Flask + SocketIO 全栈 Web 应用，对齐 LDR (`C:/dev/local-deep-research`) 架构。
- **核心目标**：在保留现有三阶段 LLM 流水线 + BFS 引用展开能力的基础上，新增**前向追踪、新论文订阅、知识网络可视化、跨论文综述**四大能力。
- **目标场景**：ABM (Agent-Based Modeling) 方法学的全方向文献监控——后向（已有）+ 前向（新增）+ 增量监控（新增）+ 综述（新增）。
- **存储演进**：文件系统产物保留作为人类可读副本，SQLite + SQLAlchemy 作为查询/状态/订阅的真相源。
- **CLI 命运**：保留 `expand.py` / `run_analysis_ui.py` 入口，重构为调用同一 service 层的薄壳。

---

## 1. 现状盘点

### 1.1 已有能力（保留）
- 三阶段 LLM 流水线：内容分析 → 引用提取 → 自动下载（`run_analysis_ui.py`）
- BFS 引用网络递归（`expand.py`，断点续跑靠 `_manifest.json`）
- 搜索链：Unpaywall → OpenAlex → Semantic Scholar → arXiv → RePEC → CORE → scholarly
- 下载器：`nber`（URL 重写）、`ssrn`（patchright + CF Turnstile）、`generic`（landing page + Unpaywall fallback）
- 产物结构：`papers/<stem>/{md, analysis_insight.md, analysis_refs.md, refs/*.pdf, refs_failed.md, session_*.jsonl}` + 顶层 `network.json`

### 1.2 缺口
1. **前向追踪**：当前只能从一篇论文向引用文献展开，无法反向找"谁引用了这篇"
2. **新论文订阅**：无法监控某主题/作者/论文有新工作出现
3. **网络可视化**：`network.json` 数据结构就绪但无渲染
4. **跨论文综述**：每篇论文有 `analysis_insight.md`，但没有跨论文的方法论总结
5. **任务管理**：失败/暂停/恢复全靠 `_manifest.json` 文件级去重，无队列状态可见性
6. **引用元数据**：每篇引用的期刊质量、影响力无标注

---

## 2. 整体架构

```
┌────────────────────────────────────────────────────────────┐
│                     Web 前端 (Vite SPA)                    │
│  - Dashboard (任务/订阅/进度)                              │
│  - Papers (列表/详情/Cited by tab)                         │
│  - Network (Cytoscape.js 引用图)                           │
│  - Subscriptions (监控配置)                                │
│  - Review (综述生成器)                                     │
└──────────────┬─────────────────────────────────────────────┘
               │ REST API + WebSocket
┌──────────────▼─────────────────────────────────────────────┐
│              Flask + Flask-SocketIO 后端                   │
│  - API routes  - Socket events  - Auth (单用户简化)        │
└──────────────┬─────────────────────────────────────────────┘
               │
┌──────────────▼─────────────────────────────────────────────┐
│                   Service Layer (现有 CLI 重构)            │
│  AnalysisService / ExpandService / SearchService /         │
│  DownloadService / ForwardTrackService /                   │
│  SubscriptionService / ReviewService                       │
└────┬────────────────┬──────────────────┬───────────────────┘
     │                │                  │
┌────▼─────┐   ┌──────▼──────┐    ┌──────▼─────────┐
│ SQLite   │   │ APScheduler │    │ 文件系统       │
│ +SQLAlc. │   │ (订阅/重试) │    │ papers/*.pdf   │
│          │   │             │    │ + analysis_*.md│
└──────────┘   └─────────────┘    └────────────────┘
```

**关键原则**：
- **文件系统不消失**：`papers/<stem>/` 目录是产物的人类可读副本，DB 仅做索引、状态、查询、订阅。任何论文删除文件夹后，DB 可重建。
- **CLI 不消失**：`expand.py` 改为调用 service 层，等价于 Web UI 提交任务，方便脚本场景。

---

## 3. 数据模型（SQLite schema）

```
papers
  id PK
  stem (与文件夹同名)
  doi UNIQUE NULL
  arxiv_id UNIQUE NULL
  title
  authors_json
  year
  journal_id FK → journals (NULL if unknown)
  pdf_path (相对路径)
  md_path
  insight_path
  refs_path
  status (pending|analyzed|failed)
  failure_reason NULL
  source (root|ref|forward|subscription)
  added_at / analyzed_at

journals
  id PK
  issn UNIQUE
  name
  publisher
  quality_tier (1-4)
  is_predatory BOOL
  oa_status
  source_dataset (openalex|doaj|predatory_list)
  refreshed_at

edges                          # network.json 落地
  id PK
  from_paper_id FK
  to_paper_id FK
  direction (backward|forward) # backward=被from引用; forward=引用from
  index INT                    # 在分析中的序号
  ref_title                    # 命中时记录的标题
  discovered_at

tasks                          # 替代 _manifest.json
  id PK
  type (analyze|expand|forward_track|subscription_check)
  paper_id FK NULL
  payload_json
  status (queued|running|paused|completed|failed)
  attempt INT
  max_attempts INT (默认 3)
  parent_task_id FK NULL       # BFS 父子关系
  started_at / finished_at
  error_log TEXT

subscriptions
  id PK
  type (paper_citations|author_works|topic_search)
  target_json                  # {doi:...} / {author_id:...} / {query:..., focus:...}
  cron_expr                    # APScheduler 表达式
  last_run_at
  next_run_at
  active BOOL

subscription_results
  id PK
  subscription_id FK
  paper_id FK NULL             # 新发现的论文（若入库）
  raw_metadata_json
  notified BOOL
  found_at

citations                      # 规范化引文（参考 LDR）
  id PK
  paper_id FK
  citation_key (BibTeX key)
  bibtex TEXT
  apa TEXT
  refreshed_at

sessions                       # session_*.jsonl 索引
  id PK
  paper_id FK
  jsonl_path
  phase (1|2|3)
  model
  started_at
```

**索引**：`papers(doi)`, `papers(stem)`, `edges(from_paper_id)`, `edges(to_paper_id)`, `tasks(status, type)`, `subscriptions(active, next_run_at)`。

---

## 4. 模块拆解 + 优先级

### Milestone 1 — 基础设施（P0，2 周）

| 模块 | 内容 | 验收 |
|------|------|------|
| M1.1 SQLite + SQLAlchemy ORM | 上述 schema + Alembic 迁移 | `alembic upgrade head` 通过 |
| M1.2 Service 层抽离 | 把 `run_analysis_ui.py`/`expand.py` 的核心逻辑抽到 `services/` | CLI 仍可跑、行为不变 |
| M1.3 数据迁移脚本 | 扫描现有 `papers/*` 与 `network.json` 填入 DB | 25 篇论文全量入库 |
| M1.4 Flask 应用骨架 | `app.py` + blueprint + SocketIO | `flask run` 起 5000 端口 |
| M1.5 任务队列数据库化 | `tasks` 表替代 `_manifest.json`，支持 retry/暂停/恢复 | 跑一次 expand，任务状态可见 |
| M1.6 WebSocket 进度推送 | 现有 SSE 升级为 Socket.IO `progress` 事件 | 前端能实时看到三阶段进度 |

### Milestone 2 — 论文监控（P1，2 周）

| 模块 | 内容 | 验收 |
|------|------|------|
| M2.1 前向追踪服务 | `ForwardTrackService`：调用 SS Citing Papers + OpenAlex `cited_by_api_url` | 输入一篇论文 DOI，返回最近 N 篇引用它的论文 |
| M2.2 期刊质量评分 | 移植 LDR 的 `journals` 数据（OpenAlex + DOAJ + Stop Predatory），每篇入库时打分 | papers 详情页显示期刊 Tier |
| M2.3 订阅服务 | `SubscriptionService` + APScheduler，三种订阅类型 | 创建一个 paper_citations 订阅，定时跑通 |
| M2.4 订阅通知 | 新发现论文落 `subscription_results`，前端 inbox 提示，可选邮件 | 新增 1 篇被引论文，UI 红点 + 详情 |
| M2.5 引文规范化 + BibTeX | 移植 LDR `citation_normalizer`，每篇可导出 `.bib` | 单篇/全库导出 BibTeX |

### Milestone 3 — 可视化与综述（P1，2 周）

| 模块 | 内容 | 验收 |
|------|------|------|
| M3.1 前端骨架 | Vite + Vue/React（选一） + Bootstrap 或 Tailwind | 路由/布局/SocketIO 接好 |
| M3.2 Dashboard 页 | 任务/订阅状态、最近活动、统计卡片 | 看得到运行中任务 |
| M3.3 Papers 列表 + 详情 | 列表带筛选（年份/期刊 Tier/状态），详情含 `Cited by` tab | 25 篇可浏览 |
| M3.4 网络图（Cytoscape.js） | 渲染 `edges` 表为有向图，节点颜色按期刊 Tier，可过滤 | 点击节点跳详情 |
| M3.5 综述生成器 | 选中网络若干节点 → 触发 RAG map-reduce → 流式输出 review draft | 选 5 篇生成一份方法论综述 |

### Milestone 4 — 补全与优化（P2，1 周）

| 模块 | 内容 |
|------|------|
| M4.1 Zenodo 搜索源 | 接入搜索链第 7 站 |
| M4.2 PubMed 搜索源（可选） | 若 ABM 涉及生物医学 |
| M4.3 失败诊断面板 | 把 `refs_failed.md` UI 化，按失败原因聚合 |
| M4.4 用户认证（如要联网访问） | 单用户密码登录，CSRF |
| M4.5 SQLCipher（可选） | 若有隐私顾虑再启用 |

---

## 5. 技术栈选型

| 层 | 选型 | 备选 | 决策理由 |
|----|------|------|----------|
| 后端框架 | **Flask + Flask-SocketIO** | FastAPI + Starlette WebSocket | 对齐 LDR，生态成熟，与现有 Python 代码无缝 |
| ORM | **SQLAlchemy 2.x + Alembic** | Peewee, SQLModel | LDR 用的就是这个，迁移管理强 |
| 数据库 | **SQLite (普通)** | PostgreSQL, SQLCipher | 单人单机够用，零部署；后期再加密 |
| 调度 | **APScheduler** | Celery, RQ | 嵌入式，无需额外 broker，符合单进程定位 |
| 前端构建 | **Vite** | Webpack, Rollup | 快、现代，LDR 同款 |
| 前端框架 | **Vue 3** | React | 单文件组件对单人项目更友好；如熟悉 React 也可选 |
| UI 库 | **Tailwind CSS + Headless UI** | Bootstrap 5 | 视觉更现代；如想完全对齐 LDR 用 Bootstrap |
| 网络图 | **Cytoscape.js** | D3 force, vis-network, sigma.js | 专做学术/生物图，API 稳定，性能好 |
| Markdown 渲染 | marked + dompurify | markdown-it | 沿用现有依赖 |
| HTTP 客户端 | httpx (已有) | requests | 已有 |
| LLM 调用 | 沿用现有 Ollama (`http://<ollama-host>:13812`) | — | 不变 |

---

## 6. 关键技术决策点

### 6.1 数据真相源
- **决策**：文件系统 = 产物副本（人类可读），SQLite = 索引 + 状态 + 关系。
- **不变式**：任何论文产物删除后，重跑 `kb reindex` 可重建 DB；DB 损坏不影响产物本身。
- **写入顺序**：先写文件，再写 DB；DB 写失败时记录到 `tasks.error_log`，不删文件。

### 6.2 CLI 与 Web 同源
- **决策**：CLI（`expand.py`、`run_analysis_ui.py`）保留作为入口，重构后只是 service 层薄壳。
- **效果**：脚本场景 + Web UI 共用同一份业务逻辑，不会出现"CLI 能跑 Web 不行"或反之的偏差。

### 6.3 任务队列单进程
- **决策**：用 SQLAlchemy + APScheduler 在 Flask 进程内做队列，不引入 Celery/Redis。
- **理由**：单人单机、长任务并发度低（PDF 下载 + LLM 调用是 IO bound，已被外部资源限速）。
- **风险**：Flask 进程崩溃时运行中任务状态会卡在 `running`。**对策**：启动时扫描 `running` 任务 → 重置为 `queued`。

### 6.4 前向追踪 API 选择
- **首选**：Semantic Scholar `papers/{paper_id}/citations` API（免费、字段多、有 intent 标注）。
- **备选**：OpenAlex `works/{id}` 的 `cited_by_api_url`（全免费、量大但元数据稍弱）。
- **策略**：两个都打，结果按 DOI 去重合并。

### 6.5 订阅频率
- **默认**：`paper_citations` 每周一次（学术索引更新慢，每天浪费配额）。
- **可配**：`cron_expr` 字段，每个订阅独立配。

### 6.6 综述生成策略
- **首选 map-reduce**：每篇论文先生成 100-200 字方法论摘要 → 全部塞进上下文 → LLM 综合。
- **备选 RAG**：把 `analysis_insight.md` 切块入向量库 → 按主题查询。
- **决策**：先 map-reduce（实现简单、可控），网络规模超过 100 篇后再考虑 RAG。

---

## 7. 实施路径

### 阶段化交付

```
Week 1-2  Milestone 1（基础设施）       → 内部可用，CLI 仍跑
Week 3-4  Milestone 2（论文监控）       → 前向追踪 + 订阅可用
Week 5-6  Milestone 3（可视化 + 综述）  → 完整 Web UI 上线
Week 7    Milestone 4（补全 + 优化）    → 收尾
```

### 每个 Milestone 的人工评审点
- M1 末：验证 25 篇论文全量入库无丢失，CLI 行为与之前一致
- M2 末：跑一次完整订阅周期，验证发现+通知链路
- M3 末：5 篇论文生成一份综述，验证质量可接受
- M4 末：决定 SQLCipher / 多源补充等可选项是否启用

---

## 8. 风险与权衡

| 风险 | 影响 | 缓解 |
|------|------|------|
| Web 化对单人使用是 over-engineering | 维护成本上升 | 保留 CLI 入口，Web 失败可回退命令行 |
| SocketIO 在 Windows + rootless Docker 下 worker 选型 | 进度推送失败 | 默认 threading worker；如部署到 Linux 服务器再考虑 eventlet/gevent |
| 前向追踪 API 配额（SS 免费 100 req/5min） | 大批量追踪受限 | 增加本地缓存表（`forward_track_cache`），同一 DOI 7 天内不重查 |
| 期刊质量数据维护 | OpenAlex/DOAJ 数据会过期 | 字段 `refreshed_at`，每月一次后台刷新任务 |
| 网络图节点 > 500 后渲染卡顿 | UI 体验差 | Cytoscape 默认 layout 改为 `cose-bilkent`；超过阈值切换为 WebGL renderer |
| 综述生成质量不稳定 | 用户失望 | M3.5 提供"重新生成 / 调整 prompt / 选不同模型"按钮，不依赖一次成功 |
| 现有 papers/* 元数据不全（缺 DOI/年份） | 入库时 schema 字段空 | 入库时补全：尝试从 `analysis_insight.md` 头部解析；失败则标记 `status=incomplete` 待人工补 |

---

## 9. 迁移策略（现有数据 → 新系统）

### 9.1 一次性脚本 `scripts/migrate_to_db.py`
1. 扫描 `papers/` 下所有子目录
2. 对每个子目录：
   - 读 `analysis_insight.md` 头部解析 title/year/doi（若有）
   - 读 `analysis_refs.md` 解析引用列表
   - 读 `network.json` 取节点 + 边
   - 写入 `papers`、`edges`、`citations` 表
3. 输出 `migration_report.md`：成功数、失败数、缺字段清单

### 9.2 不动文件系统
- 不重命名、不移动、不删除任何现有文件
- 仅在 DB 中记录 `papers.pdf_path` / `md_path` / `insight_path` 等指针

### 9.3 回滚方案
- 删除 SQLite 文件即可回到迁移前状态
- CLI 仍可继续跑（service 层向后兼容文件系统）

---

## 10. 目录结构（演进后）

```
KnowledgeBase/
  app/                          ← 新增：Web 应用
    __init__.py                 ← Flask app factory
    routes/
      api.py                    ← REST API
      pages.py                  ← 页面路由
    sockets/
      progress.py               ← Socket.IO 事件
    auth.py                     ← 单用户认证（M4）
  services/                     ← 新增：业务服务层
    analysis_service.py         ← 三阶段流水线（原 run_analysis_ui.py 核心）
    expand_service.py           ← BFS 展开（原 expand.py 核心）
    search_service.py           ← 搜索链
    download_service.py         ← 下载分发器
    forward_track_service.py    ← 前向追踪（新）
    subscription_service.py     ← 订阅（新）
    review_service.py           ← 综述生成（新）
    journal_service.py          ← 期刊评分（新）
  database/                     ← 新增
    models.py                   ← SQLAlchemy 模型
    migrations/                 ← Alembic
    seed/
      journals.json             ← LDR 移植的期刊数据
  frontend/                     ← 新增：Vite SPA
    src/
      pages/
      components/
      stores/
    vite.config.ts
    package.json
  scripts/                      ← 保留
    expand.py                   ← 改为 services 的薄壳
    run_analysis_ui.py          ← 改为 services 的薄壳
    pdf2md.py
    search_refs.py
    download_pdf.py
    downloaders/
    migrate_to_db.py            ← 新增：一次性迁移
  papers/                       ← 保留：产物副本
  network.json                  ← 保留：DB 重建用（兼容入口）
  kb.db                         ← 新增：SQLite 主数据库
  alembic.ini
  AGENTS.md
  README.md
  PLAN.md                       ← 本文件
```

---

## 11. 验收清单（全量完成后）

- [ ] 25 篇现有论文全量入库，所有引用边正确
- [ ] `expand.py` CLI 行为等价（产物结构不变 + 多了 DB 写入）
- [ ] Web UI 能看到任务进度（Socket.IO 推送）
- [ ] 输入 DOI 可触发前向追踪，5 分钟内有结果
- [ ] 创建订阅，下周期自动跑，新论文落库 + UI 红点
- [ ] 网络图可渲染 25 节点，节点点击跳详情
- [ ] 选 5 篇生成综述，输出可读的方法论总结
- [ ] 单篇/全库 BibTeX 导出
- [ ] 所有期刊都有 Tier 标注（无 Tier 显示 "Unknown"）

---

## 12. 后续可选（不在本 PLAN 范围）

- SQLCipher 加密（若有隐私需求）
- Zotero 双向同步
- 多用户/权限
- 部署到服务器 + 反向代理
- 移动端响应式
