# KnowledgeBase — Agent 使用指南

## 核心命令

```bash
# 单篇论文三阶段分析（内容 → 引用 → 下载）
python scripts/run_analysis_ui.py <md_path> --focus <关注点> [--headless]

# BFS 递归展开引用网络（断点续跑）
python scripts/expand.py <root_pdf> --focus <关注点> [--max-depth 1] [--max-breadth N]

# 查询单篇论文元数据 + PDF 链接
python scripts/search_refs.py "<title>" [--year <year>] [--doi "<doi>"]

# 下载单个 PDF
python scripts/download_pdf.py <url> <output.pdf>

# 初始化 / 升级数据库
alembic upgrade head
python scripts/migrate_to_db.py

# 启动 Web 服务
python scripts/serve.py          # Flask 后端 :5000
cd frontend && npm run dev        # Vite 前端 :5173
```

## 搜索链路

```
DOI 路径：Unpaywall → OpenAlex(DOI) → Semantic Scholar(DOI)
标题路径：OpenAlex → Semantic Scholar → arXiv → RePEC → CORE → Zenodo → PubMed → scholarly
```

有元数据但无 pdf_url 时继续搜下一源。所有来源做标题相似度验证（阈值 0.80）。

## 下载 Handler（`scripts/downloaders/`）

| 文件 | 触发 | 说明 |
|------|------|------|
| `nber.py` | `nber.org` | URL 格式转换 |
| `ssrn.py` | `ssrn.com` | patchright + CF Turnstile 自动点击 |
| `generic.py` | 兜底 | httpx + landing page + Unpaywall fallback |

新增来源：在 `downloaders/` 下新建模块，实现 `can_handle(url)` + `download(url, path)`，加入 `download_pdf.py` 的 `_HANDLERS` 列表。

## 产物结构

```
papers/
  _manifest.json              ← BFS 去重表（CLI 断点续跑用）
  <stem>/
    <stem>.pdf                ← 原始 PDF
    <stem>.md                 ← MinerU 转换
    analysis_insight.md       ← Phase 1 内容分析
    analysis_refs.md          ← Phase 2 引用分析
    refs/*.pdf                ← Phase 3 下载成功
    refs_failed.md            ← 下载失败清单（含原因）
    session_*.jsonl           ← LLM 会话记录
network.json                  ← 知识图谱（nodes + edges，CLI 维护）
kb.db                         ← SQLite 主数据库（Web + CLI 共用）
```

## REST API 端点（`http://localhost:5000/api/`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/papers` | 论文列表（`?status=&source=&limit=&offset=`） |
| GET | `/papers/stats` | 总数 + 已分析数 |
| GET | `/papers/<id>` | 论文详情 + edges |
| POST | `/papers/<id>/forward-track` | 触发前向追踪 |
| GET | `/papers/<id>/citations.bib` | 单篇 BibTeX 下载 |
| POST | `/papers/<id>/citation` | 生成/刷新 BibTeX |
| GET | `/citations.bib` | 全库 BibTeX |
| GET | `/tasks` | 任务列表 |
| GET/POST | `/subscriptions` | 订阅 CRUD |
| PATCH | `/subscriptions/<id>` | 更新订阅 |
| DELETE | `/subscriptions/<id>` | 删除订阅（有未读时返回 409） |
| GET | `/inbox` | 订阅发现的新论文 |
| POST | `/inbox/<id>/read` | 标已读 |
| POST | `/reviews` | 触发综述生成（SSE 流式，`chunk`/`done`/`error` 事件） |
| GET | `/network` | 网络图节点 + 边 |
| GET | `/failures` | 所有下载失败条目 + 分类统计 |
| GET | `/health` | 健康检查 |

## 典型下载率参考

经济学 / 管理学 / 统计期刊：约 **50%**（NBER paywall 和老旧闭源期刊是主要瓶颈）。
