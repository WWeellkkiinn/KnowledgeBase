# KnowledgeBase UI/功能修复计划

## 问题清单

| # | 问题 | 分类 | 主要文件 |
|---|------|------|---------|
| 1 | 核心库/探索库切换时出现"加载中"闪烁 | UI体验 | Papers.vue |
| 2 | 参考/被引中"已入库"和"API结果"分两块，改为合并一行+标签 | UI体验 | PaperDetail.vue |
| 3 | 导入时自动根据标题查询 DOI；批量补全现有无 DOI 论文 | 新功能 | doi_resolver.py (新), api.py |
| 4 | 引用图节点显示作者+年份，不是论文名称 | 引用图 | Network.vue |
| 5 | Tab 标题旁括号内显示数量（引用 N / 被引用 N） | UI体验 | PaperDetail.vue |
| 6 | 统一术语：全部"参考文献"改为"引用" | UI文本 | PaperDetail.vue |
| 7 | 引用图节点大小按被引用量决定 | 引用图 | Network.vue |
| 8 | 论文库支持多选，批量删除/移动到核心库/探索库 | 新功能 | Papers.vue, api.py |
| 9 | BibTeX 下载按钮移到 DOI 后面 | UI布局 | PaperDetail.vue |
| 10 | DOI 字体与年份统一；dl 网格对齐修复 | UI样式 | PaperDetail.vue |
| 11 | 引用图只展示核心论文节点 | 引用图 | Network.vue |
| 12 | 核心论文节点大小由被引用量决定（与 #7 合并，等价） | 引用图 | Network.vue |
| 13 | 期刊无法识别（journals 表为空，无论文关联到期刊） | 数据 | journal_service.py, api.py |

---

## 根因分析

### Issue 13 — 期刊识别失效
- `journals` 表当前 **0 条记录**，`papers.journal_id` 全部为 NULL
- `database/seed/journals.json` 存有 30 条手动期刊，**从未被加载进 DB**
- `journal_service.attach_to_paper()` 存在，但 journals 表空所以永远匹配不到
- 修复路径：
  1. 启动时自动 seed 30 条手动期刊
  2. 在论文导入/分析完成后调用 `attach_to_paper()`（传入从分析结果里提取的期刊名）
  3. 扩展：调用 CrossRef API 按期刊名查询 ISSN + 元数据，覆盖 seed 没有的期刊

### Issue 3 — DOI 查询
- LDR 通过 Semantic Scholar `paper/search` + OpenAlex `works?search=` 按标题查 DOI
- KnowledgeBase 没有类似服务，导入时 DOI 字段空着
- 修复路径：
  1. 新建 `services/doi_resolver.py`，调用 SS + CrossRef（双源，按置信度取最高分）
  2. 在 `graph_writer.upsert_paper()` 前调用，补全 stub paper 的 DOI
  3. 提供脚本一次性补全现有无 DOI 论文

---

## 文件归属

| 文件 | 涉及 Issue |
|------|-----------|
| `frontend/src/pages/Network.vue` | 4, 7+12, 11 |
| `frontend/src/pages/PaperDetail.vue` | 2, 5, 6, 9, 10 |
| `frontend/src/pages/Papers.vue` | 1, 8（前端） |
| `frontend/src/api/endpoints.ts` | 8（批量接口调用） |
| `frontend/src/types/api.ts` | 8（批量参数类型） |
| `app/routes/api.py` | 8（批量端点）, 13（期刊attach触发） |
| `services/journal_service.py` | 13（seed加载 + attach修复） |
| `services/doi_resolver.py`（新建） | 3 |
| `services/graph_writer.py` | 3（upsert时调用doi_resolver） |

---

## 并行策略

由于 `PaperDetail.vue` 和 `api.py` 各自涉及多个 issue，合并处理：

### 轮次 1（可完全并行，无文件冲突）

**Agent A — Network 图改造**（Issue 4, 7+12, 11）
- 只修改 `Network.vue`
- 节点 label 改为 `作者缩写 · 年份`
- 节点 size 按被引用量（forward-track 数量）缩放
- 只渲染 `is_core=true` 的节点（后端 API 已支持 `?tier=core`）

**Agent B — 期刊识别修复**（Issue 13）
- 只修改 `journal_service.py`
- 启动时 seed 30 条手动期刊（若表空则导入）
- 修复 `attach_to_paper()` 调用链（在 api.py 论文入库时触发）
- 对现有 21 篇核心论文跑一次补全

### 轮次 2（轮次1完成后，各 Agent 改不同文件）

**Agent C — PaperDetail 全改**（Issue 2, 5, 6, 9, 10）
- 合并"已入库"标签到 API 结果列（同 DOI 命中 → 加"已入库 →"链接）
- API 结果未到前显示已入库行 + loading 提示；按年份倒序
- Tab 标题加括号数量：`引用 (N)` / `被引用 (N)`
- "参考文献"全改为"引用"
- BibTeX 按钮移到 DOI 行后
- DOI 字体 `text-sm`（与其他字段一致），`dl` 网格加 `items-baseline`

**Agent D — Papers 列表改造**（Issue 1, 8）
- 切换 tab 时保留旧数据不清空（方案 A），等新数据返回后替换
- 加 checkbox 多选列，顶部出现批量操作栏（删除/移入核心库/移入探索库）
- 后端新增：`DELETE /api/papers/batch`（接收 id 列表）、`PATCH /api/papers/batch/tier`（接收 id+tier）

### 轮次 3（独立，不阻塞前两轮）

**Agent E — DOI 查询服务**（Issue 3）
- 新建 `services/doi_resolver.py`
  - 调用 SS `paper/search?query=<title>&fields=externalIds`
  - 调用 CrossRef `api.crossref.org/works?query.title=<title>&rows=3`
  - 双源结果按标题相似度取最高置信度返回 DOI
- 修改 `graph_writer.upsert_paper()` —— DOI 为空时调用 resolver 尝试补全
- 提供脚本 `scripts/fill_missing_dois.py`，一次性跑完现有无 DOI 论文

---

## 具体实现方案

### Issue 1 — 切换无闪烁

```typescript
// Papers.vue fetchPage 改动：去掉 items.value = [] 的清空
// 等新数据到了再赋值，旧数据在此期间保持显示
async function fetchPage() {
  const requestedTier = tier.value
  const requestedOffset = offset.value
  loading.value = true
  error.value = null
  // 不清空 items，保留旧数据避免闪烁
  try {
    const resp = await papersApi.list(...)
    if (tier.value !== requestedTier || offset.value !== requestedOffset) return
    hasMore.value = resp.items.length > pageSize
    items.value = resp.items.slice(0, pageSize)  // 数据到了才替换
  } ...
}
```

### Issue 2 — 参考/被引合并

- 已入库边 (`detail.edges_out`) 按 DOI 建 Map
- API 结果到来后按 DOI 查 Map，命中则在该行末尾加 `<RouterLink>已入库 →</RouterLink>`
- API 结果未返回前：先渲染已入库边（无 DOI 则仅显示标题），加 loading spinner
- 排序：有年份的按年份倒序，无年份的排最后

### Issue 8 — 多选批量操作

后端新增：
```python
@bp.delete("/papers/batch")
def delete_papers_batch():
    ids = request.json.get("ids", [])
    # 级联删除 edges，再删除 paper
    ...

@bp.patch("/papers/batch/tier")
def move_papers_batch():
    ids = request.json.get("ids", [])
    is_core = request.json.get("is_core")  # True=核心库, False=探索库
    ...
```

前端：
- 表格第一列加 checkbox，header checkbox 全选/取消
- 有选中项时顶部出现操作栏：`已选 N 篇 [删除] [移入核心库] [移入探索库]`
- 操作后刷新列表

### Issue 13 — 期刊识别

```python
# journal_service.py 新增
def seed_if_empty(session):
    """若 journals 表为空，从 seed/journals.json 导入"""
    count = session.execute(select(func.count()).select_from(Journal)).scalar()
    if count == 0:
        with open(SEED_PATH) as f:
            data = json.load(f)
        for item in data:
            session.add(Journal(**item))
        session.commit()

def attach_by_name(session, paper, journal_name: str):
    """按期刊名关联，命中 seed 则直接关联；否则调用 CrossRef 查元数据"""
    ...
```

在 `scripts/serve.py` 启动时调用 `seed_if_empty()`。
在 api.py 的 `analyze` / `import` 入口完成后调用 `attach_by_name()`。

### Issue 3 — DOI 查询

```python
# services/doi_resolver.py
def resolve_doi(title: str) -> Optional[str]:
    """按标题查询 DOI，SS 优先，CrossRef 备用"""
    # 1. Semantic Scholar
    resp = requests.get(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params={"query": title, "fields": "externalIds,title", "limit": 3},
        timeout=10
    )
    for paper in resp.json().get("data", []):
        if _title_similarity(paper.get("title",""), title) > 0.85:
            doi = (paper.get("externalIds") or {}).get("DOI")
            if doi: return doi

    # 2. CrossRef fallback
    resp = requests.get(
        "https://api.crossref.org/works",
        params={"query.title": title, "rows": 3, "select": "DOI,title"},
        timeout=10
    )
    for item in resp.json().get("message", {}).get("items", []):
        if _title_similarity(item.get("title",[""])[0], title) > 0.85:
            return item.get("DOI")
    return None
```

---

## 验收标准

| Issue | 验收条件 |
|-------|---------|
| 1 | 切换核心库/探索库时，旧数据保持显示，新数据到来后平滑替换，无空白闪烁 |
| 2 | 引用/被引 tab 只有一个列表；已入库论文末尾显示"已入库 →"链接；按年份倒序 |
| 3 | 新导入无 DOI 论文后，页面显示 DOI 已自动填入；`fill_missing_dois.py` 运行后现有无 DOI 论文减少 |
| 4 | 引用图节点显示 `Smith et al. · 2023` 而非论文标题 |
| 5 | 引用 tab 显示 `引用 (42)` 被引用 tab 显示 `被引用 (7)` |
| 6 | 全站"参考文献"改为"引用"，无遗漏 |
| 7+12 | 引用图节点大小与被引用量成正比；被引 0 篇的节点最小，被引最多的节点最大 |
| 8 | 可多选删除/移入核心库/探索库；操作后列表刷新；删除同时清理 edges |
| 9 | BibTeX 按钮紧跟 DOI 行右侧 |
| 10 | DOI 字体 `text-sm`，与年份一致；`dt/dd` 在同一基线对齐 |
| 11 | 引用图只显示 `is_core=true` 的论文节点和它们之间的边 |
| 13 | 21 篇核心论文至少有部分论文成功关联到期刊，期刊详情页不再全显示"—" |
