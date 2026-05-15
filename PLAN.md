# 核心功能规划

## F1 — AI 论文打标签

**目标**：调用 GPU 服务器上的 Ollama，对论文标题 + 摘要进行分析，自动生成语义标签。

### 标签策略：积累型开放词表

- 维护 `services/tags_vocab.json`（初始为空，逐步积累）
- 每次 AI 分析论文时：
  1. 携带**当前词表**进 Prompt，要求优先从词表中选 3–5 个最匹配的标签
  2. 若词表无法覆盖，AI 可生成新标签，新标签**自动追加**进词表（供后续论文复用）
- 词表随项目积累自然扩展；语义重复由 Prompt 约束（"避免生成与词表中已有标签含义相同的新标签"）

### 实现要点

| 项 | 细节 |
|----|------|
| Ollama 端点 | `KB_OLLAMA_URL` 环境变量（默认 `http://localhost:11434`） |
| 模型 | `qwen3.6-27b`（`/no_think` 前缀开启思维链，tag 生成不需要，直接用默认） |
| 触发时机 | 论文入库时自动触发；批量补跑接口供已有论文使用 |
| 存储 | `papers` 表新增 `tags` JSON 字段；词表存 `services/tags_vocab.json` |
| UI | 论文卡片 + 详情页显示标签 chip；支持按标签筛选 |

---

## F2 — AI 论文精炼

**目标**：对每篇论文提取结构化研究摘要，供快速阅读和比较。

### 提取字段

| 字段 | 说明 |
|------|------|
| `research_question` | 核心研究问题（1–2 句） |
| `methodology` | 研究方法（数据来源、模型、实验设计） |
| `key_findings` | 主要结论（2–3 条） |

### 实现要点

- 与 F1 **合并为单次 Ollama 调用**，Prompt 同时返回标签 + 精炼（JSON 格式），减少请求次数
- 结果存入 `papers` 表新增的 `ai_summary` JSON 字段
- 详情页新增"AI 精炼"折叠区，展示三项内容
- 无摘要的论文（stub）跳过，不触发

---

## F3 — 邮件推送

**目标**：每天凌晨自动抓取新论文，筛选 ABM 相关内容，发送日报到 `&lt;DIGEST_RECIPIENT&gt;`；同时提供手动触发按钮。

### 流程

```
定时任务（每日 00:00，APScheduler）
  → 查询过去 24h 新增论文（created_at > now-24h）
  → 对每篇论文：调用 Ollama 判断与 ABM 领域的相关性（0–1 分）
  → 相关性 ≥ 0.6 的论文入选，同时触发 F1+F2 分析（若尚未分析）
  → 组装 HTML 邮件 → 发送至 &lt;DIGEST_RECIPIENT&gt;
  → 无入选论文时跳过（不发空邮件）
```

### 相关性判断 Prompt（领域定义）

> "Agent-Based Modeling (ABM), complex adaptive systems, social simulation, computational social science. Papers on multi-agent systems, emergent behavior, network dynamics, policy simulation using ABM methods."

### 邮件内容结构

```
主题：[KnowledgeBase] 今日论文日报 · 2026-05-14（共 N 篇）

今日推荐（按相关性排序）
─────────────────────────────────
标题：...
研究问题：...
研究方法：...
主要结论：...
标签：#ABM #social-simulation
相关性：0.85
─────────────────────────────────
...
```

### 实现要点

| 项 | 细节 |
|----|------|
| 定时任务 | 复用已有 APScheduler（`services/subscription_service.py`），新增 digest job |
| 手动触发 | 新增 `POST /api/digest/send` 接口；前端 Dashboard 增加"发送今日日报"按钮 |
| 邮件发送 | Python `smtplib`，163 SMTP（`smtp.163.com:465`，SSL） |
| SMTP 认证 | 授权码读自 `.env`（`EMAIL_AUTH_CODE=...`），**⚠️ 需用户提供授权码** |
| 收件人 | `&lt;DIGEST_RECIPIENT&gt;`（写死在配置里，不做多收件人） |

---

## 待处理

- [ ] **163 邮箱 SMTP 授权码**：在 163 邮箱「设置 → POP3/SMTP/IMAP」生成授权码，告知后写入 `.env`

---

## 实现顺序

```
1. F1+F2：ai_service.py（单次调用，返回 tags + summary JSON）
           → DB 迁移（新增 tags / ai_summary 字段）
           → 入库 hook（论文新增时自动触发）
           → 批量补跑接口 POST /api/papers/ai-analyze-batch

2. F3：    digest_service.py（相关性过滤 + 邮件组装）
           → APScheduler job（每日 00:00）
           → POST /api/digest/send 手动触发接口
           → 前端 Dashboard 按钮

3. UI：    标签 chip（论文卡片 + 详情页 + 筛选）
           + 详情页"AI 精炼"折叠区
           + Dashboard"发送日报"按钮
```
