# 推理服务器部署文档

## 服务器

| 项目 | 值 |
|------|-----|
| IP | `<ollama-host>` |
| 用户 | `<deploy-user>` |
| GPU | `4 x RTX 4090` |
| 显存 | `96GB` |
| RAM | `1TB` |

### SSH 连接

```bash
# 私钥路径（Claude Code / Git Bash 环境用 /c/ 前缀，不能用 C:/）
ssh -i <home>/.ssh/<deploy-ssh-key> <deploy-user>@<ollama-host>

# ⚠ Windows 路径 C:/Users/... 在 Git Bash 下会报 exit 255，必须用 /c/Users/...
```

- 私钥文件：`<home>\.ssh\<deploy-ssh-key>`（ed25519，无密码）
- Ollama 日志：写 `~/ollama.log` 可能权限不足，改用 `/tmp/ollama.log`
- `pkill` 返回 1 = 没有找到进程（正常，不是失败）

---

## Ollama

### 基本信息

| 项目 | 值 |
|------|-----|
| 二进制 | `/data/home/<deploy-user>/bin/ollama` |
| 版本 | `0.21.0` |
| 端口 | `13811` |
| 模型目录 | `/data/home/<deploy-user>/ollama` |

### 已部署模型

| 模型 | 文件 | 大小 | Ollama 名称 | num_ctx |
|------|------|------|-------------|---------|
| Gemma 4 31B | `gemma-4-31B-it-Q4_K_M.gguf` | `18GB` | `gemma4-31b` | 默认 |
| SuperGemma 4 26B | `supergemma4-26b-uncensored-fast-v2-Q4_K_M.gguf` | `16GB` | `supergemma4-26b` | **262144** |

### 启动命令（标准）

```bash
# Ollama（GPU1+2，双卡，必须关闭 Flash Attention）
OLLAMA_FLASH_ATTENTION=0 CUDA_VISIBLE_DEVICES=1,2 \
OLLAMA_HOST=0.0.0.0:13811 OLLAMA_MODELS=/data/home/<deploy-user>/ollama \
nohup /data/home/<deploy-user>/bin/ollama serve > /tmp/ollama.log 2>&1 &

# 验证
ss -tlnp | grep 13811
```

> ⚠️ **`OLLAMA_FLASH_ATTENTION=0` 必须设置**（影响所有 gemma4 模型）：
> gemma4 + `think=true` + 任意 prompt 下，Flash Attention 会导致 prefill 卡死（GPU 利用率归零，永不输出），
> 重现于 GitHub issue [#15350](https://github.com/ollama/ollama/issues/15350)。
> 不加此参数将导致每次 LLM 调用超时后返回 500，且**不会有任何错误提示**，只是静默卡死。
> 已在 supergemma4-26b 和 gemma4-31b 上均验证修复。

### 性能参考

| 模型 | 配置 | tok/s | thinking 可用 | 结论 |
|------|------|-------|--------------|------|
| supergemma4-26b | 单卡 | `~143` | ❌ 大输入下 thinking 失控 | 不推荐用 thinking |
| supergemma4-26b | 双卡 | `~148` | ❌ 同上 | — |
| gemma4-31b | 单卡 | `~24.5` | ✅ | 可用 |
| gemma4-31b | 双卡 | `~40.7` | ✅ | **推荐，当前默认** |

> supergemma4-26b 在 `think=true` + 大段落输入（~8000字符）下，thinking token 无上限发散，
> 建议设 `num_predict: 4096` 或直接关闭 thinking。

---

## MinerU

### 部署信息

| 项目 | 值 |
|------|-----|
| 目录 | `/data/home/<deploy-user>/project/MinerU` |
| 基础镜像 | `vllm/vllm-openai:v0.11.2-x86_64` |
| 业务镜像 | `mineru:latest` |
| 镜像大小 | `~53.2GB` |

### 启动命令

```bash
# MinerU（GPU3，端口 8000）
docker run -d --name mineru-api-kb \
  --gpus '"device=3"' -p 8000:8000 \
  -e MINERU_MODEL_SOURCE=local --ipc host \
  mineru:latest mineru-api --host 0.0.0.0 --port 8000
```

### 常驻空闲占用

| 资源 | 占用 |
|------|------|
| CPU | `~0.73%` |
| 内存 | `~2.76GiB` |
| 显存（单卡） | `~13GB` |

---

## 文献调研 Agent

### 架构

```
本地
  ├── AGENTS.md              ← 定义调研行为，Codex 启动自动读取
  ├── kb.bat                 ← 启动入口（Codex + Ollama）
  └── scripts/
        ├── pdf2md.py        ← PDF → Markdown（调 MinerU API）
        ├── extract_refs.py  ← 解析引用文献（数字 / APA 两种格式，支持多作者 &）
        ├── search_refs.py   ← 搜索元数据（OpenAlex → SS → arXiv）
        ├── run_analysis.py  ← 单篇分析（CLI，无 UI）
        └── run_analysis_ui.py ← 5阶段分析 + 实时浏览器 UI（SSE 流式）

服务器（仅提供计算）
  ├── MinerU API  :8000      ← PDF 转换
  └── Ollama      :13811     ← LLM 推理（gemma4-31b，双卡）
```

### GPU 分配

| 卡 | 服务 | 显存 |
|---|---|---|
| GPU 1+2 | Ollama（双卡，gemma4-31b） | ~18GB |
| GPU 3 | MinerU API（Docker） | ~13GB |
| GPU 0 | 保留 | — |

### 本地使用

```bash
# Web UI 分析（推荐）
conda activate kb
python scripts/run_analysis_ui.py <paper.md> --focus "研究方法"
# 自动打开 http://localhost:8765

# CLI 单篇分析
conda activate kb
python scripts/run_analysis.py <paper.md> --focus "研究方法"
```

### run_analysis_ui.py 关键配置

```python
MODEL = "gemma4-31b"        # 当前默认模型
ENABLE_THINKING = True      # 31B 可开，26B 大输入下建议关
MAX_SECTIONS = 4            # 每次最多分析章节数

# LLM 调用参数
"options": {"temperature": 0.1, "num_ctx": 8192, "num_predict": 4096}
```

### 5 阶段流程

| 阶段 | 说明 |
|------|------|
| Phase 1 | 关键词匹配选出最相关的 ≤4 个章节（自动跳过无实质内容的标题节） |
| Phase 2 | 逐章节：LLM 写 50 字摘要 + **判断与关注点相关的引用**（模型筛选，非全文正则） |
| Phase 3 | 综合各章节摘要，输出 300 字深度分析 |
| Phase 4 | 将模型选出的引用标记与 refs.json 匹配（支持 APA / 数字两种格式） |
| Phase 5 | 补充引用元数据（OpenAlex → Semantic Scholar → arXiv） |

### 输出结构

```
papers/
  <论文文件名>/
    <论文文件名>.md      ← 原文 Markdown（MinerU 转换）
    analysis.md          ← 中文分析 + 引用文献概览
    refs.json            ← 引用文献列表（含 DOI/pdf_url/relevance）
    todo_download.txt    ← 待下载清单（[index] 标题 | DOI | pdf_url 或 NOT_FOUND）
    session_*.jsonl      ← 完整对话记录（仅保留最新）
```

### Codex 配置

`~/.codex/config.toml` 已配置 `ollama-local` provider，`kb.bat` 启动时自动使用：

```toml
[model_providers.ollama-local]
name = "Ollama (local server)"
base_url = "http://<ollama-host>:13811/v1"
wire_api = "responses"
```

---

## 已知问题 / 优化待办

### P1 — refs.json relevance 字段仍为空

**状态**：待开始

Phase 4 匹配到引用后，`relevance` 字段（high/medium/low）在 Web UI 模式下未填写。
需要在 Phase 2 或 Phase 5 中让模型对每条引用输出相关性评级。

### P2 — 结构化输出验证

**状态**：待开始

Phase 2 输出为自由文本（`摘要：xxx\n引用：xxx`），依赖 `parse_phase2_output` 正则解析。
改为 JSON 结构化输出并加验证，防止格式漂移导致静默失败。

### P3 — 元数据命中率追踪

**状态**：暂缓

`search_refs.py` 三个来源（OpenAlex → SS → arXiv）无命中日志，不知道整体覆盖率。
暂不处理，等前两项稳定后再评估。
