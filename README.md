# 推理服务器部署文档

## 服务器

| 项目 | 值 |
|------|-----|
| IP | `<ollama-host>` |
| 用户 | `<deploy-user>` |
| GPU | `4 x RTX 4090` |
| 显存 | `96GB` |

### SSH 连接

```bash
# 私钥路径（Claude Code / Git Bash 环境用 /c/ 前缀，不能用 C:/）
ssh -i <home>/.ssh/<deploy-ssh-key> <deploy-user>@<ollama-host>

# ⚠ Windows 路径 C:/Users/... 在 Git Bash 下会报 exit 255，必须用 /c/Users/...
```

- 私钥文件：`<home>\.ssh\<deploy-ssh-key>`（ed25519，无密码）
- Ollama 日志：写 `~/ollama.log` 可能权限不足，改用 `/tmp/ollama.log`
- `pkill` 返回 1 = 没有找到进程（正常，不是失败）
| RAM | `1TB` |

---

## Ollama

### 基本信息

| 项目 | 值 |
|------|-----|
| 二进制 | `/data/home/<deploy-user>/bin/ollama` |
| 版本 | `0.21.0` |
| 端口 | `13811` |
| 模型目录 | `/data/home/<deploy-user>/ollama` |

### 环境变量

```bash
export OLLAMA_HOST=0.0.0.0:13811
export OLLAMA_MODELS=/data/home/<deploy-user>/ollama
```

### 已部署模型

| 模型 | 文件 | 大小 | Ollama 名称 | num_ctx |
|------|------|------|-------------|---------|
| Gemma 4 31B | `gemma-4-31B-it-Q4_K_M.gguf` | `18GB` | `gemma4-31b` | 默认 |
| SuperGemma 4 26B | `supergemma4-26b-uncensored-fast-v2-Q4_K_M.gguf` | `16GB` | `supergemma4-26b` | **262144** |

### 启停

```bash
~/start-ollama.sh          # 默认
~/start-ollama.sh 1        # 指定 GPU1
~/start-ollama.sh 2        # 指定 GPU2
```

- 日志：`~/ollama.log`
- 停止：`pkill -u <deploy-user> -f 'ollama serve'`
- 验证：`ss -tlnp | grep 13811`

### 性能参考

| 模型 | 配置 | tok/s | 结论 |
|------|------|-------|------|
| supergemma4-26b | 单卡 | `~143` | 推荐单卡 |
| supergemma4-26b | 双卡 | `~148` | 提升很小 |
| gemma4-31b | 单卡 | `~24.5` | 可用 |
| gemma4-31b | 双卡 | `~40.7` | 推荐双卡 |

### 调用示例

```python
from openai import OpenAI

client = OpenAI(base_url="http://<ollama-host>:13811/v1", api_key="ollama")
response = client.chat.completions.create(
    model="supergemma4-26b",
    messages=[{"role": "user", "content": "你好"}],
)
print(response.choices[0].message.content)
```

---

## MinerU

### 部署信息

| 项目 | 值 |
|------|-----|
| 目录 | `/data/home/<deploy-user>/project/MinerU` |
| 基础镜像 | `vllm/vllm-openai:v0.11.2-x86_64` |
| 业务镜像 | `mineru:latest` |
| 镜像大小 | `~53.2GB` |

### 构建调整

```dockerfile
RUN /bin/bash -c "mineru-models-download -s modelscope -m all"
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
本地（Codex TUI）
  ├── AGENTS.md              ← 定义调研行为，Codex 启动自动读取
  ├── kb.bat                 ← 启动入口（接 Ollama）
  └── scripts/
        ├── pdf2md.py        ← PDF → Markdown（调 MinerU API）
        ├── extract_refs.py  ← 解析引用文献（数字 / APA 两种格式）
        ├── search_refs.py   ← 搜索元数据（OpenAlex → SS → arXiv）
        └── run_analysis.py  ← 单篇分析快捷脚本

服务器（仅提供计算）
  ├── MinerU API  :8000      ← PDF 转换
  └── Ollama      :13811     ← LLM 推理（supergemma4-26b，256k context）
```

### GPU 分配

| 卡 | 服务 | 显存 |
|---|---|---|
| GPU 1+2 | Ollama（双卡，supergemma4-26b 或 gemma4-31b） | ~16-18GB |
| GPU 3 | MinerU API（Docker） | ~13GB |
| GPU 0 | 保留 | — |

### 服务器端启动

```bash
# MinerU（GPU3，端口 8000）
docker run -d --name mineru-api-kb \
  --gpus '"device=3"' -p 8000:8000 \
  -e MINERU_MODEL_SOURCE=local --ipc host \
  mineru:latest mineru-api --host 0.0.0.0 --port 8000

# Ollama（GPU1+2，双卡，必须关闭 Flash Attention）
OLLAMA_FLASH_ATTENTION=0 CUDA_VISIBLE_DEVICES=1,2 \
OLLAMA_HOST=0.0.0.0:13811 OLLAMA_MODELS=/data/home/<deploy-user>/ollama \
nohup /data/home/<deploy-user>/bin/ollama serve > /tmp/ollama.log 2>&1 &
```

> ⚠️ **`OLLAMA_FLASH_ATTENTION=0` 必须设置**（影响所有 gemma4 模型）：
> gemma4 + `think=true` + 任意 prompt 下，Flash Attention 会导致 prefill 卡死（GPU 利用率归零，永不输出），
> 重现于 GitHub issue [#15350](https://github.com/ollama/ollama/issues/15350)。
> 不加此参数将导致每次 LLM 调用超时后返回 500，且**不会有任何错误提示**，只是静默卡死。
> 已在 supergemma4-26b 和 gemma4-31b 上均验证修复。

### 本地使用

```bash
# 文献调研模式（Codex + Ollama）
kb.bat

# 单篇快速分析（保存对话记录）
# 依赖：pip install httpx
conda activate kb
python scripts/run_analysis.py <paper.md> --focus "研究方法"
```

### 输出结构

```
papers/
  <论文文件名>/
    <论文文件名>.md      ← 原文 Markdown（MinerU 转换）
    analysis.md          ← 中文分析 + 引用文献概览
    refs.json            ← 引用文献列表（含 DOI/pdf_url/relevance）
    todo_download.txt    ← 待下载清单（[index] 标题 | DOI | pdf_url 或 NOT_FOUND）
    session_*.jsonl      ← 完整对话记录
```

### Codex 配置

`~/.codex/config.toml` 已配置 `ollama-local` provider，`kb.bat` 启动时自动使用：

```toml
[model_providers.ollama-local]
name = "Ollama (local server)"
base_url = "http://<ollama-host>:13811/v1"
wire_api = "responses"
```

普通 `codex` 命令走全局默认（gpt-5.4），两者不冲突。

---

## 优化待办（按优先级）

### P1 — 重新设计 LLM 任务（relevance 判断 + 分析深度）

**状态**：待开始

当前 LLM 只做「定位章节 + 200 字摘要 + 列引用编号」，三件事代码几乎都能做。`refs.json` 的 `relevance` 字段在批处理模式下全部为空，而这是决定「下一步读哪篇」的核心判断。

目标：重新设计 prompt，让 LLM 在分析时同时输出：
- 每条引用的相关性评级（high/medium/low）及理由
- 方法论关键决策与潜在局限
- 每条引用支撑了哪个具体论点

### P2 — 结构化输出验证

**状态**：待开始

LLM 输出为自由文本，靠 `AGENTS.md` 约束格式，无校验机制。LLM 承担更多判断后，输出必须是可解析的结构（JSON），并在写文件前验证，防止静默失败。

### P3 — 全文上下文分段策略

**状态**：待开始

当前全文一次性送入模型（256k context 够用但有噪音）。改为先定位目标章节，再精准送入，减少无关内容干扰，提升分析聚焦度。

### P4 — 元数据命中率追踪

**状态**：暂缓

`search_refs.py` 三个来源（OpenAlex → SS → arXiv）无命中日志，不知道整体覆盖率。暂不处理，等前三项稳定后再评估是否必要。
