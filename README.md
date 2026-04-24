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
  run_analysis_ui.py ← 单篇分析 Web UI（SSE 流式，两轮 multi-turn）
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

**两条分支：**

1. **普通站点**（默认）：`httpx` 直接 GET → 校验 PDF（Content-Type 或 `%PDF` 文件头）→ 若为落地页，按 `_LANDING_PAGE_RULES` 递归抽取真实 PDF 链接（最多 3 跳，复用同一 client 保留 cookie/Referer）
2. **SSRN**（`ssrn.com` 域名）：走 `patchright` 启动真实 Chrome（持久化 profile，存于项目下 `.cache/browser_profile/`），等 Cloudflare 挑战通过，自动点"Download This Paper"按钮保存 PDF

**当前 landing 规则：** Harvard DASH、Gary King 个人主页、RePEc IDEAS、通用 DSpace。新增规则在 `_LANDING_PAGE_RULES` 列表追加一条即可。

**SSRN 分支说明：** 会短暂弹出可见 Chrome 窗口（无头模式会被 Cloudflare 识破）。首次访问约 10s 通过挑战，后续复用 cookie 更快。需本机装有 Chrome。浏览器持久化 profile 存于项目下 `.cache/browser_profile/`（已 gitignore）。

---

## 目录结构

```
papers/                         ← 所有论文数据（分析产物入库，原始 PDF 不入库）
  <论文标题>/
    <论文标题>.pdf               ← 原始 PDF（手动放置或自动下载）
    <论文标题>.md                ← MinerU 转换的 Markdown
    analysis_insight.md         ← LLM 内容分析（总分总结构）
    analysis_refs.md            ← LLM 高相关引用分析（完整标题）
    refs.json                   ← 全部引用（含 DOI/pdf_url/relevance）
    todo_download.txt           ← 高相关性引用的下载清单
    session_*.jsonl             ← LLM 会话记录（仅保留最新）

scripts/                        ← 所有脚本
  config.py                     ← API Keys（不提交）

network.json                    ← 知识网络数据（待实现）
```

**关于 papers/ 目录**：分析产物（Markdown、refs.json、分析结果等）纳入版本控制，原始 PDF 体积较大不建议提交。`tests/` 目录放测试用 PDF，已被 `.gitignore` 忽略。

---

## 使用方法

### 前置条件

**首次配置环境（只跑一次）：**

```powershell
conda create -n kb python=3.12 -y
conda activate kb
pip install -r requirements.txt
# SSRN 等 Cloudflare 站点需要真实 Chrome（用系统已装的 Chrome 即可，以下命令补全 Playwright 驱动）
python -m patchright install chrome
```

**日常使用：**

```powershell
conda activate kb
# 确认服务器上 Ollama（:13812）和 MinerU（:8000）已启动
```

依赖清单（`requirements.txt`）：`httpx`、`patchright`（隐身 Playwright 分支，用于绕 SSRN 的 Cloudflare）。

### 1. PDF 转 Markdown

```bash
python scripts/pdf2md.py path/to/paper.pdf
# 输出：papers/<论文标题>/<论文标题>.md
```

### 2. 单篇分析

```bash
python scripts/run_analysis_ui.py papers/<论文标题>/<论文标题>.md --focus "研究方法"
# 自动打开 http://localhost:8765
```

分析完成后，`papers/<论文标题>/` 下会生成 `analysis_insight.md`、`analysis_refs.md`、`session_*.jsonl`。

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
MODEL = "qwen3.6-27b"
ENABLE_THINKING = True   # /no_think 前缀开启思维链（qwen3.6 语义反转）

# LLM 调用参数
num_ctx=65536, num_predict=8192, temperature=0.1
```

### 分析流程（两轮 multi-turn，共享 KV cache）

| 轮次 | 说明 | 输出文件 |
|------|------|----------|
| Turn 1 | 全文送入，输出论文在关注重点上的内容分析（总览 / 详细内容 / 小结） | `analysis_insight.md` |
| Turn 2 | 接续同一对话，列出高相关引用（完整标题 + 作用说明） | `analysis_refs.md` |

---

## 已知限制与待办

| 项目 | 说明 |
|------|------|
| PDF 下载成功率 | 管理学/经济学期刊约 10-20%，受 OA 覆盖率限制，非代码问题 |
| 迭代扩展 | `expand.py` 待实现：自动读 todo_download.txt → 下载 → 分析 → 积累网络 |
| 知识网络 | `network.json` 数据结构已设计，可视化层待实现 |

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
| GPU 1+2 | Ollama 双卡模型（gemma4-31b / supergemma4-26b / qwen3.5-27b） | ~18-26GB |
| GPU 0 或单卡 | Ollama 单卡模型（qwen3.6-27b Q4_K_M） | ~22GB |
| GPU 3 | MinerU API（Docker） | ~13GB |

### Ollama（<deploy-user> 用户 rootless Docker）

#### 日常使用（最常用）

```bash
# SSH 进服务器
ssh -i <home>/.ssh/<deploy-ssh-key> <deploy-user>@<ollama-host>

# 三个快捷命令（~/.local/bin 里的 shell 脚本）
ollama-up                   # 启动容器 + 预热 qwen3.6-27b（~7s 热盘 / 60s 冷盘），出来就能秒回
ollama-up gemma4-31b        # 启动并预热其他模型（会换容器默认模型，需先跑 gemma 容器）
ollama-down                 # 停止容器，释放 GPU
ollama-status               # 看容器状态 + 当前加载的模型

# 也可以用原生命令
ollama list                         # 列模型（本质是 docker exec 透传）
ollama ps                           # 看当前加载的模型
ollama run qwen3.6-27b              # 交互式对话
```

从 Windows 本地调用：容器跑着时 `http://<ollama-host>:13812` 就是 Ollama REST API 端点（`run_analysis_ui.py` / Cherry Studio / codex 都走这里）。

#### 生命周期策略（当前）

| 行为 | 设置 |
|------|------|
| rootless docker daemon | `Linger=yes` → 服务器开机就起（~150MB RAM，0 GPU），<deploy-user> 是否登录无关 |
| 容器 `ollama-<deploy-user>` | `--restart=no` → daemon 在也不会自动起，必须 `ollama-up` 才跑 |
| `OLLAMA_KEEP_ALIVE=24h` | 容器内模型加载后常驻 24h，避免反复冷加载 |

所以开停完全手动：你 `ollama-up` 就用，`ollama-down` 就释放，ssh 断不断都不影响。

#### 首次安装 / 灾难恢复

```bash
# 1. daemon 常驻（linger）+ 自启
loginctl enable-linger <deploy-user>
systemctl --user enable --now docker.service

# 2. 重建容器（已定型的 B 方案：FA=1 + Q8 KV + 64k）
docker rm -f ollama-<deploy-user> 2>/dev/null || true
docker run -d \
  --name ollama-<deploy-user> \
  --restart no \
  --runtime nvidia \
  --gpus '"device=1"' \
  -e OLLAMA_FLASH_ATTENTION=1 \
  -e OLLAMA_KV_CACHE_TYPE=q8_0 \
  -e OLLAMA_CONTEXT_LENGTH=65536 \
  -e OLLAMA_HOST=0.0.0.0:11434 \
  -e OLLAMA_KEEP_ALIVE=24h \
  -p 13812:11434 \
  -v /data/home/<deploy-user>/ollama:/root/.ollama/models \
  ollama/ollama:latest
```

#### 配置说明

| 参数 | 值 | 理由 |
|------|------|------|
| `--gpus '"device=1"'` | 单卡 GPU1 | qwen3.6-27b Q4 + 64k Q8 KV ≈ 23GB，单卡够用；gemma4 等双卡模型另起容器 |
| `OLLAMA_FLASH_ATTENTION=1` | 开 | KV cache 量化的前提条件；⚠️ gemma4 系列会卡死（[#15350](https://github.com/ollama/ollama/issues/15350)），跑 gemma 要另起容器 FA=0 |
| `OLLAMA_KV_CACHE_TYPE=q8_0` | Q8 量化 KV | 把 KV cache 从 fp16 压到 8bit，64k 上下文省 4GB，质量损失 <0.5% ppl |
| `OLLAMA_CONTEXT_LENGTH=65536` | 64k | 覆盖典型论文（~40-45k token），留 20k buffer；预分配，启动即占满 |
| `-p 13812:11434` | 宿主 13812 映射到容器 11434 | 避开原裸机 13811 冲突 |
| `-v /data/home/<deploy-user>/ollama:/root/.ollama/models` | 挂载模型目录 | 复用 4 个已下载的模型 blobs，不重下 |

#### 调用入口汇总（一处改端口，改全部）

| 入口 | 文件 | 行为 |
|------|------|------|
| Windows 脚本 | `scripts/run_analysis_ui.py` 33 行 | `OLLAMA_BASE = "http://<ollama-host>:13812"` |
| Cherry Studio | UI 设置 | API 地址 `http://<ollama-host>:13812`，模型参数 `num_ctx=65536` |
| codex CLI | `~/.codex/config.toml` | `base_url = "http://<ollama-host>:13812/v1"` |
| <deploy-user> shell | `~/.bashrc` | `export OLLAMA_HOST=http://127.0.0.1:13812` |
| 直接 curl | 任何地方 | `curl http://<ollama-host>:13812/api/chat -d ...` |

#### 跑 gemma4 系列（需要另起容器）

gemma4 / supergemma4 在 FA=1 下会卡死。要跑它们：

```bash
docker run -d \
  --name ollama-<deploy-user>-gemma \
  --restart no \
  --runtime nvidia \
  --gpus '"device=0,1"' \
  -e OLLAMA_FLASH_ATTENTION=0 \
  -e OLLAMA_CONTEXT_LENGTH=32768 \
  -e OLLAMA_HOST=0.0.0.0:11434 \
  -e OLLAMA_KEEP_ALIVE=24h \
  -p 13813:11434 \
  -v /data/home/<deploy-user>/ollama:/root/.ollama/models \
  ollama/ollama:latest
```

端口 13813 区分开；双卡避免 CPU offload（31B 模型单卡装不下）。

#### 历史裸机配置 ↔ Docker 参数对照（归档）

| 裸机时代（已删除） | Docker 等价 |
|---|---|
| `OLLAMA_HOST=0.0.0.0:13811` | `-e OLLAMA_HOST=0.0.0.0:11434` + `-p 13812:11434` |
| `OLLAMA_MODELS=/data/home/<deploy-user>/ollama` | `-v /data/home/<deploy-user>/ollama:/root/.ollama/models` |
| `OLLAMA_FLASH_ATTENTION=0` | qwen 场景改 `=1`（支持 KV 量化）；gemma 场景保持 `=0` |
| `CUDA_VISIBLE_DEVICES=1` | `--gpus '"device=1"'` |
| `/tmp/ollama.log` | `docker logs ollama-<deploy-user>` |

### 已部署模型

| 模型 | Ollama 名称 | 量化 | tok/s | GPU 数 | thinking |
|------|------------|------|-------|--------|---------|
| Gemma 4 31B | `gemma4-31b` | — | ~40.7 | 双卡 | ✅ 推荐 |
| SuperGemma 4 26B | `supergemma4-26b` | — | ~148 | 双卡 | ❌ 大输入下发散 |
| Qwen 3.5 27B | `qwen3.5-27b` | Q5_K_M | — | 双卡 | ✅ |
| Qwen 3.6 27B | `qwen3.6-27b` | Q4_K_M | ~40.6 | 单卡 | ✅ 多模态（见注意事项） |

### qwen3.6-27b 思维链说明

**模板**：v2 ChatML（`capabilities: ['completion', 'thinking']`）

**⚠️ `/think` / `/no_think` 语义与直觉相反**（该 GGUF 的已知行为）：

| 指令 | 实际效果 |
|------|--------|
| `system: "/no_think"` | **开启**思维链，`thinking` 字段有内容，content 干净 |
| `system: "/think"` | **关闭**思维链，content 为直接回答 |

**直接调用示例（开启思考）**：
```bash
curl http://<ollama-host>:13812/api/chat -d '{
  "model": "qwen3.6-27b",
  "stream": false,
  "messages": [
    {"role": "system", "content": "/no_think"},
    {"role": "user", "content": "你的问题"}
  ]
}'
# response.message.thinking → 推理过程
# response.message.content  → 最终答案
```

**Cherry Studio**：thinking 开关正常（Cherry Studio 在客户端侧自行构建 ChatML，不受此影响）。

### MinerU 启动

```bash
docker run -d --name mineru-api-kb \
  --gpus '"device=3"' -p 8000:8000 \
  -e MINERU_MODEL_SOURCE=local --ipc host \
  mineru:latest mineru-api --host 0.0.0.0 --port 8000
```

### Codex 配置

`~/.codex/config.toml` 已配置 `ollama-local` provider：

```toml
[model_providers.ollama-local]
name = "Ollama (local server)"
base_url = "http://<ollama-host>:13812/v1"
wire_api = "responses"
```
