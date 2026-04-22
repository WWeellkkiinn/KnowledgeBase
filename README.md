# KnowledgeBase — 学术文献网络分析系统

## 项目愿景

**目标**：以一篇论文 + 一个关注点为起点，通过 LLM 迭代展开，自动构建覆盖某研究领域的文献知识网络。

**核心流程**：
1. 输入一篇论文 + 关注点（方法、话题、研究问题、政策等）
2. LLM 分析论文，提取与关注点相关的引用文献及关键信息
3. 对提取到的引用文献递归重复上述过程（迭代扩展）
4. 所有论文与引用关系积累为结构化的**知识网络**

**知识网络的价值**：
- 引用关系可视化（论文为节点，引用/方法共用为边）
- 方法溯源：追踪某方法最早出自哪篇论文
- 方法/话题聚类：找到使用相同方法的论文群
- 影响力识别：快速定位被引最多的论文或方法

**可视化方向**（待定）：Obsidian 风格图谱，或 Neo4j + 前端渲染。

---

## 当前实现状态

| 层次 | 状态 |
|------|------|
| 单篇分析（PDF → 分析 → 引用提取） | ✅ 完成 |
| 引用文献元数据补充与 PDF 下载 | ✅ 完成（下载成功率受 OA 覆盖率限制） |
| 迭代扩展（自动下载并分析引用论文） | 🔲 待实现 |
| 知识网络构建与可视化 | 🔲 待实现 |

---

## 脚本说明

```
scripts/
  config.py          ← API Keys（已加入 .gitignore，不提交）
  pdf2md.py          ← PDF → Markdown（调 MinerU API）
  extract_refs.py    ← 解析论文引用（数字格式 [1] 和 APA 格式）
  search_refs.py     ← 搜索引用文献元数据 + PDF URL
  download_pdf.py    ← 下载 PDF（支持落地页解析）
  run_analysis.py    ← 单篇分析 CLI（无 UI）
  run_analysis_ui.py ← 单篇分析 Web UI（SSE 流式，推荐）
  _marked.min.js     ← Web UI 依赖（Markdown 渲染）
  _dompurify.min.js  ← Web UI 依赖（XSS 防护）
```

### search_refs.py 查询链

给定论文标题 + DOI，按优先级依次查询：

```
DOI 完整 → Unpaywall → OpenAlex DOI直查 → Semantic Scholar DOI直查
             ↓（均无结果或 title 不符）
标题搜索 → OpenAlex → Semantic Scholar → arXiv → CORE
```

- 所有路径均进行**标题相似度验证**（阈值 0.80），防止错误 DOI 或误匹配
- Unpaywall `best_oa_location` 字段同时返回直链（`url_for_pdf`）和落地页（`url`），两者均可被 `download_pdf.py` 处理

### download_pdf.py 下载逻辑

1. 直接 GET 目标 URL（浏览器 UA，跟随重定向）
2. 校验响应是否为 PDF（Content-Type 或 `%PDF` 文件头）
3. 若响应是 HTML 落地页，自动解析其中的 PDF 直链（当前支持 Harvard DASH）
4. 成功写文件，失败 exit 1 并打印原因到 stderr

---

## 目录结构

```
papers/                         ← 所有论文数据（已加入 .gitignore）
  <论文标题>/
    <论文标题>.pdf               ← 原始 PDF（手动放置或自动下载）
    <论文标题>.md                ← MinerU 转换的 Markdown
    analysis.md                 ← LLM 分析结果
    refs.json                   ← 全部引用（含 DOI/pdf_url/relevance）
    todo_download.txt           ← 高相关性引用的下载清单
    session_*.jsonl             ← LLM 会话记录（仅保留最新）

scripts/                        ← 所有脚本
  config.py                     ← API Keys（不提交）

network.json                    ← 知识网络数据（待实现）
```

**关于 papers/ 目录**：完全被 `.gitignore` 忽略，不进入版本控制。论文 PDF 和 Markdown 文件体积较大，应放在 `papers/<论文标题>/` 下后直接运行分析脚本。

---

## 使用方法

### 前置条件

```bash
conda activate kb
# 确认服务器上 Ollama（:13811）和 MinerU（:8000）已启动
```

### 1. PDF 转 Markdown

```bash
python scripts/pdf2md.py path/to/paper.pdf
# 输出：papers/<论文标题>/<论文标题>.md
```

### 2. 单篇分析

```bash
# Web UI（推荐，实时流式输出）
python scripts/run_analysis_ui.py papers/<论文标题>/<论文标题>.md --focus "研究方法"
# 自动打开 http://localhost:8765

# CLI（无 UI，适合批量或脚本调用）
python scripts/run_analysis.py papers/<论文标题>/<论文标题>.md --focus "研究方法"
```

分析完成后，`papers/<论文标题>/` 下会生成 `analysis.md`、`refs.json`、`todo_download.txt`。

### 3. 下载引用文献 PDF

```bash
# 单条下载（测试用）
python scripts/download_pdf.py <url> papers/<新论文标题>/<新论文标题>.pdf

# 批量下载引用文献（todo_download.txt 中所有条目）
# ← expand.py 待实现，当前需手动逐条下载
```

### 4. 查询论文元数据

```bash
python scripts/search_refs.py "论文标题" --doi "10.xxxx/xxxxx"
# 输出 JSON：{ title, authors, year, doi, pdf_url, source }
```

---

## run_analysis_ui.py 关键配置

```python
MODEL = "gemma4-31b"        # 当前默认模型
ENABLE_THINKING = True      # 31B 可开，26B 大输入下建议关
MAX_SECTIONS = 4            # 每次最多分析章节数

# LLM 调用参数
"options": {"temperature": 0.1, "num_ctx": 8192, "num_predict": 4096}
```

### 分析阶段

| 阶段 | 说明 |
|------|------|
| Phase 1 | 关键词匹配，选出最相关的 ≤4 个章节 |
| Phase 2 | 逐章节：50 字摘要 + 提取与关注重点相关的引用标记 |
| Phase 3 | 综合各章节摘要，输出 300 字深度分析 |
| Phase 4 | 引用匹配与元数据补充，标记 high/low 相关性 |

---

## 已知限制与待办

| 项目 | 说明 |
|------|------|
| PDF 下载成功率 | 管理学/经济学期刊约 10-20%，受 OA 覆盖率限制，非代码问题 |
| 迭代扩展 | `expand.py` 待实现：自动读 todo_download.txt → 下载 → 分析 → 积累网络 |
| 知识网络 | `network.json` 数据结构已设计，可视化层待实现 |
| Phase 2 引用解析 | 依赖正则，可改为 JSON 结构化输出提高鲁棒性 |

---

## 推理服务器

### 服务器信息

| 项目 | 值 |
|------|-----|
| IP | `<ollama-host>` |
| 用户 | `<deploy-user>` |
| GPU | `4 × RTX 4090`，显存 96GB |
| RAM | 1TB |

```bash
# SSH 连接（Git Bash / Claude Code 环境用 /c/ 前缀）
ssh -i <home>/.ssh/<deploy-ssh-key> <deploy-user>@<ollama-host>
```

### GPU 分配

| 卡 | 服务 | 显存 |
|----|------|------|
| GPU 1+2 | Ollama（gemma4-31b，双卡） | ~18GB |
| GPU 3 | MinerU API（Docker） | ~13GB |
| GPU 0 | 保留 | — |

### Ollama 启动

```bash
OLLAMA_FLASH_ATTENTION=0 CUDA_VISIBLE_DEVICES=1,2 \
OLLAMA_HOST=0.0.0.0:13811 OLLAMA_MODELS=/data/home/<deploy-user>/ollama \
nohup /data/home/<deploy-user>/bin/ollama serve > /tmp/ollama.log 2>&1 &
```

> ⚠️ `OLLAMA_FLASH_ATTENTION=0` 必须设置：gemma4 + `think=true` 下 Flash Attention 会导致 prefill 永久卡死（GPU 利用率归零，无任何报错）。见 [#15350](https://github.com/ollama/ollama/issues/15350)。

### 已部署模型

| 模型 | Ollama 名称 | tok/s（双卡） | thinking |
|------|------------|-------------|---------|
| Gemma 4 31B | `gemma4-31b` | ~40.7 | ✅ 推荐 |
| SuperGemma 4 26B | `supergemma4-26b` | ~148 | ❌ 大输入下发散 |

### MinerU 启动

```bash
docker run -d --name mineru-api-kb \
  --gpus '"device=3"' -p 8000:8000 \
  -e MINERU_MODEL_SOURCE=local --ipc host \
  mineru:latest mineru-api --host 0.0.0.0 --port 8000
```

### Codex 配置

`~/.codex/config.toml` 已配置 `ollama-local` provider，`kb.bat` 启动时自动使用：

```toml
[model_providers.ollama-local]
name = "Ollama (local server)"
base_url = "http://<ollama-host>:13811/v1"
wire_api = "responses"
```
