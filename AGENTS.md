# KnowledgeBase — Agent 使用指南

## 主要脚本

```
python scripts/expand.py <root_pdf> --focus <关注点> [--max-depth 1] [--max-breadth N]
```

以一篇 PDF 为根，自动完成：pdf2md → Phase1 内容分析 → Phase2 引用分析 → Phase3 搜索+下载，并递归展开 refs/*.pdf。支持断点续跑（已分析的 stem 命中 manifest 即跳过）。

```
python scripts/run_analysis_ui.py <md_path> --focus <关注点> --headless --output-dir papers
```

单篇分析（三阶段）。`--headless` 跳过浏览器 UI，适合脚本调用。

```
python scripts/search_refs.py "<title>" [--year <year>] [--doi "<doi>"]
```

查询单篇论文的元数据和 PDF URL，输出 JSON。

```
python scripts/download_pdf.py <url> <output.pdf>
```

下载单个 PDF，自动按域名选择合适的 handler。

## 搜索链路

```
DOI路径: Unpaywall → OpenAlex DOI → Semantic Scholar DOI
标题路径: OpenAlex → Semantic Scholar → arXiv → RePEC → CORE → scholarly
```

有元数据但无 pdf_url 时继续搜下一源，直到找到 PDF 链接。

## 下载 Handler

| 文件 | 触发 | 说明 |
|---|---|---|
| `downloaders/nber.py` | `nber.org` | URL 重写旧格式 |
| `downloaders/ssrn.py` | `ssrn.com` | patchright + CF Turnstile 自动点击 |
| `downloaders/generic.py` | 兜底 | httpx + landing page + Unpaywall + archive.org 长超时 |

新增来源：在 `downloaders/` 下新建模块，实现 `can_handle` + `download`，加入 `download_pdf.py` 的 `_HANDLERS`。

## 产物结构

```
papers/
  _manifest.json              ← 已分析论文去重表
  <stem>/
    <stem>.md                 ← MinerU 转换
    analysis_insight.md       ← Phase1 内容分析
    analysis_refs.md          ← Phase2 引用分析
    refs/*.pdf                ← Phase3 下载成功
    refs_failed.md            ← 下载失败清单（含原因）
    session_*.jsonl           ← LLM 会话记录
network.json                  ← 知识图谱（nodes + edges）
```

## 典型下载率参考（2026-04-25）

经济学/管理学/统计期刊引用：约 **50%**（NBER paywall 和老旧闭源期刊是主要瓶颈）。
