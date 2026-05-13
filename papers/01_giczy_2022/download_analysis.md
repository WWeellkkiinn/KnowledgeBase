# 01_giczy_2022 下载失败原因分析

> 本文档基于第一次跑 giczy 单篇测试时的 4 条失败做归因，并标注后续修复结果。
> 修复后预期下载率从 2/6 → **4/6**，剩余 2 条为源头 OA 缺失。

测试数据：单篇分析产生 6 条高相关引用，Phase3 搜索+下载初次成功 **2/6**，失败 4 条。修 SSRN 链路后预期 4/6。

## 分析质量检查

- `analysis_insight.md`：总览/详细/小结三段齐全，对「研究方法」关注点的展开具体到 LSTM 双通道架构、Word2Vec 300 维向量、引用网络 L1/L2 扩展、50% 阈值设定等技术细节，与原文一致。
- `analysis_refs.md`：6 条引用的「作用」+「与研究方法的联系」两段式结构完整，每条都指出了**具体方法学贡献**（种子集、向量化、金标准、基准对照等），不是空泛描述。

整体分析质量 **合格**。

---

## 下载失败 4 条逐条归因

### [2] Toole et al. (2020) — SSRN DOI 间接落地 ✅ 已修复

- `pdf_url`: `https://doi.org/10.2139/ssrn.3555834`
- 实测：DOI 重定向到 `https://www.ssrn.com/abstract=3555834`，Cloudflare 返回 **403 HTML**
- **根因**：`download_pdf.py` 分支判断**只看初始 URL**。DOI 不在 `ssrn.com` 域名清单，走普通 `httpx` 分支，遇到 Cloudflare 就 403。
- **修复**：`_fetch` 失败后将 `final_url` 返给 `download()`，落到 `ssrn.com` 即 fallback 浏览器分支。已实测下到 637 KB PDF。

### [4] Harris et al. (2020) — Elsevier 落地页无 PDF 直链

- `pdf_url`: `https://doi.org/10.1016/j.wpi.2020.101961`
- 实测：重定向到 `linkinghub.elsevier.com/retrieve/pii/S0172219019300791`，200 OK 但返回 HTML（Elsevier 落地页）
- **根因**：Elsevier 对非订阅用户只提供 landing page，**没有可抓的 PDF 直链**。Unpaywall 也未覆盖（Elsevier OA 论文占比低）。
- **修复**：这类 paywall 源头上就没有合法 PDF 可下。Phase3 前应先过 Unpaywall `is_oa=false` 过滤，避免浪费一次请求；或接入机构 IP 代理。

### [5] Cockburn et al. (2019) — SSRN 浏览器按钮定位失败 ✅ 已修复

- `pdf_url`: `https://papers.ssrn.com/sol3/Delivery.cfm/nber_w24449.pdf?abstractid=3154213&mirid=1`
- 报错：`waiting for locator("a:has-text(\"Download This Paper\")") ... Timeout 90000ms`
- **根因**：URL 已是 SSRN `Delivery.cfm` 端点（PDF 直出），但 `download_pdf.py` SSRN 分支**一律去 abstract 页**找 "Download This Paper" 按钮。对 Delivery.cfm 这类直链，页面根本没这个按钮。又叠加：CF 对 patchright 自动化进入 Managed Challenge 模式，挑战页持续不放行。
- **修复**：分两步。
  1. 改用 CDP 接管手动启动的真实 Chrome（`--remote-debugging-port=9222`），CF 自动放行。
  2. Delivery.cfm 路径单独处理：先访问 abstract 页拿 cookies，再带 Referer goto Delivery.cfm，触发 download 事件并保存。已实测下到 794 KB PDF。

### [6] WIPO (2019) — 灰色文献无元数据

- `pdf_url`: `-`（`source=not_found`）
- **根因**：WIPO Technology Trends 报告属于组织出版物（灰色文献），不在 OpenAlex / Semantic Scholar / arXiv / CORE 任一学术数据库索引中。`search_refs.py` 查询链全部 miss。
- **修复**：这类文献（政府/IGO 报告、白皮书）需要单独的搜索源。可接入：
  - WIPO 自身 PDF 发布目录（`www.wipo.int/edocs/pubdocs/en/...`）
  - Google Scholar 作为 fallback（但无官方 API）
  - 或直接标记为「LLM 需人工补」类别，不做自动查询

---

## 按根因分类汇总

| 类别 | 数量 | 失败条目 | 状态 |
|---|---|---|---|
| SSRN 分支判断不全 + CF 拦自动化 | 2 | [2] Toole、[5] Cockburn | ✅ 已修复（CDP 接管真 Chrome） |
| Paywall 源本身无 OA PDF | 1 | [4] Harris | ❌ 物理限制，靠 `refs_failed.md` 人工补 |
| 灰色文献无元数据 | 1 | [6] WIPO | ⚠️ 需专门源（WIPO/Google Scholar） |

修复后预期 **4/6 (67%)**。[4] 和 [6] 属于源头缺失，无法自动化。

---

## 对比 root 论文的历史下载记录

作为参照：root 论文 `Organizing for AI Innovation` 的 `analysis_refs.md` 有 8 条引用，你之前提到"上一阶段下载好了"的是 5 条（位于 `tests/downloads/`）。那一轮的成功率是 5/8 ≈ 62%。本次 giczy 是 2/6 ≈ 33%。

giczy 成功率偏低的主因是它引用 **SSRN / Elsevier / WIPO 占比更高**，这正好踩中当前实现的三类弱项。
