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
| 引用文献元数据补充与 PDF 下载 | ✅ 已接入分析流程（Phase 3 自动执行） |
| 下载失败兜底清单（人工补） | ✅ 完成（`refs_failed.md`） |
| 迭代扩展（对下载到的引用继续分析） | ✅ 完成（`expand.py` BFS，支持断点续跑） |
| 知识网络（节点 + 边持久化） | ✅ 完成（`network.json`） |
| 知识网络可视化 | 🔲 待实现 |

---

## 脚本说明

```
scripts/
  config.py          ← API Keys（已加入 .gitignore，不提交）
  pdf2md.py          ← PDF → Markdown（调 MinerU API）
  extract_refs.py    ← 解析论文引用（数字格式 [1] 和 APA 格式）
  search_refs.py     ← 搜索引用文献元数据 + PDF URL
  download_pdf.py    ← 下载 PDF（支持落地页解析）
  run_analysis_ui.py ← 单篇分析 Web UI（SSE 流式，3 阶段：分析 → 引用 → 下载；支持 --headless）
  expand.py          ← 递归展开引用网络（BFS，manifest 去重，断点续跑）
  _marked.min.js     ← Web UI 依赖（Markdown 渲染）
  _dompurify.min.js  ← Web UI 依赖（XSS 防护）
```

### search_refs.py 查询链

给定论文标题 + DOI，按优先级依次查询：

```
DOI 完整 → Unpaywall → OpenAlex DOI直查 → Semantic Scholar DOI直查
             ↓（均无结果、无 pdf_url 或 title 不符）
标题搜索 → OpenAlex → Semantic Scholar → arXiv → RePEC → CORE → Google Scholar (scholarly)
```

- 所有路径均进行**标题相似度验证**（阈值 0.80），防止错误 DOI 或误匹配
- **关键行为**：某来源找到元数据但 `pdf_url` 为空时，**不会提前返回**，而是继续尝试后续来源，直到找到 PDF 链接或全部来源耗尽。元数据（doi、authors、year）保留自首次命中的来源。
- RePEC (IDEAS.repec.org) 专为经济学/金融/管理学论文设计，覆盖大量工作论文版本
- scholarly（Google Scholar 非官方）作为最后兜底，有限速风险但覆盖最广

### download_pdf.py 下载逻辑

`download_pdf.py` 是薄分发器，按 URL 特征选择 `scripts/downloaders/` 下的 handler：

| Handler | 触发条件 | 策略 |
|---|---|---|
| `nber.py` | `nber.org` | URL 重写（旧格式 → 新格式）+ httpx |
| `ssrn.py` | `ssrn.com` | patchright 浏览器 + CF Turnstile 自动点击 |
| `generic.py` | 兜底（所有其他 URL） | httpx → landing page 递归 → Unpaywall fallback → SSRN 重定向检测 |

**新增来源**：在 `scripts/downloaders/` 下创建新模块，实现 `can_handle(url)` + `download(url, path)`，在 `download_pdf.py` 的 `_HANDLERS` 列表中插入合适位置即可。

**SSRN 下载（全自动，无需手动操作）：**

patchright headed 浏览器自动处理 Cloudflare Turnstile：
- 检测到挑战页（标题含「请稍候」/「正在进行安全验证」）时，自动定位 `challenges.cloudflare.com` iframe 内的 checkbox 并点击
- 优先尝试 CDP 接管已运行的真实 Chrome（`:9222`），不可用时自动启动 headed 浏览器

**Wayback Machine（archive.org）：** 冷缓存响应慢，`generic.py` 对该域名使用 `httpx.Timeout(90.0, connect=30.0)` 单独控制读取超时。

**当前 landing 规则（generic.py）：** Harvard DASH、Gary King 个人主页、RePEC IDEAS、通用 DSpace。新增规则在 `_LANDING_PAGE_RULES` 追加一条即可。

---

## 目录结构

```
papers/                             ← 所有论文数据（分析产物入库，原始 PDF 不入库）
  _manifest.json                    ← 已分析论文清单（expand.py 去重 + 断点续跑用）
  <论文 stem>/                      ← stem 即文件名 basename（root 用论文标题，refs 用 NN_第一作者_年份）
    <论文 stem>.pdf                 ← 原始 PDF（手动放置或被上级 refs/ 下载）
    <论文 stem>.md                  ← MinerU 转换的 Markdown
    analysis_insight.md             ← Phase 1：LLM 内容分析
    analysis_refs.md                ← Phase 2：LLM 高相关引用分析（含可选 DOI）
    refs/                           ← Phase 3：自动下载的引用 PDF
      01_<第一作者>_<年份>.pdf       ← 编号与 analysis_refs.md 对齐，递归的入口
      02_<第一作者>_<年份>.pdf
      ...
    refs_failed.md                  ← Phase 3：下载失败清单（仅失败时存在，供人工补）
    session_*.jsonl                 ← LLM 会话记录

scripts/                            ← 所有脚本
  config.py                         ← API Keys（不提交）
  downloaders/                      ← PDF 下载 handler 插件目录
    nber.py                         ← NBER 工作论文（URL 重写）
    ssrn.py                         ← SSRN + Cloudflare Turnstile 自动点击
    unpaywall.py                    ← DOI → OA PDF 直链 helper（被 generic 调用）
    generic.py                      ← 通用 httpx + landing page + Unpaywall fallback

network.json                        ← 知识网络（节点 + 边），由 expand.py 维护
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
```

**日常使用：**

```powershell
conda activate kb
# 1. 确认服务器上 Ollama（:13812）和 MinerU（:8000）已启动
# 2. 启动一个手动 Chrome 实例（SSRN 引用文件下载必需，每天/Chrome 关掉后重做）：
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir=.cache\real_profile
# 3. 在该 Chrome 中访问 https://www.ssrn.com/ 一次（CF 一般自动放行；
#    若标题卡在「请稍候」，等几秒或刷新即可）
```

依赖清单（`requirements.txt`）：`httpx`、`patchright`（Playwright 隐身分支，提供 CDP 接管 API）。

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

分析完成后，`papers/<论文标题>/` 下会生成：

- `analysis_insight.md`（Phase 1）
- `analysis_refs.md`（Phase 2）
- `refs/NN_<第一作者>_<年份>.pdf`（Phase 3 自动下载，编号与 Phase 2 一致）
- `refs_failed.md`（仅失败时生成）—— 人工补下清单，逐条含标题/DOI/pdf_url/失败原因
- `session_*.jsonl`

### 3. 递归展开引用网络

```bash
# 对 root 论文跑完整流程，再对它下载到的 refs/*.pdf 跑一层（共 2 层）
python scripts/expand.py "papers/<root>/<root>.pdf" --focus "研究方法" --max-depth 1

# 更深递归 + 每篇限前 N 条 refs（控制预算）
python scripts/expand.py "papers/<root>/<root>.pdf" --focus "研究方法" --max-depth 2 --max-breadth 5
```

行为：
- BFS 遍历，串行执行（MinerU 同步 + SSRN 浏览器互斥）
- `papers/_manifest.json` 记录已分析的 stem，重跑命中即秒过（**支持断点续跑**）
- 每篇完成即持久化 `network.json`（节点 + 边），中途 Ctrl+C 不丢
- 失败节点（pdf2md / LLM / 下载失败）照样入网络图，但子树跳过；下载失败的单条引用进 `refs_failed.md`

### 4. 手动下载单个 PDF（调试用）

```bash
python scripts/download_pdf.py <url> <输出路径.pdf>
```

### 5. 查询论文元数据

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

### 分析流程（3 阶段；前两阶段 multi-turn 共享 KV cache）

| 阶段 | 说明 | 输出 |
|------|------|------|
| Phase 1 | 全文送入，输出论文在关注重点上的内容分析（总览 / 详细内容 / 小结） | `analysis_insight.md` |
| Phase 2 | 接续同一对话，列出高相关引用（完整标题 + 作用说明） | `analysis_refs.md` |
| Phase 3 | 逐条解析 Phase 2 引用 → `search_refs.py` 找 URL → `download_pdf.py` 下载 | `refs/*.pdf` + `refs_failed.md`（如有失败） |

---

## 已知限制与待办

| 项目 | 说明 |
|------|------|
| PDF 下载成功率 | 受 OA 覆盖率限制；失败条目进 `refs_failed.md` 供人工介入 |
| 递归去重粒度 | 当前仅按 stem（文件名）去重；未来遇到"同一论文不同 stem"时可升级为 DOI / title-slug |
| 网络图可视化 | `network.json` 结构就绪（`nodes` + `edges`），未来接 Obsidian Canvas / D3 渲染 |

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
