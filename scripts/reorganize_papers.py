#!/usr/bin/env python3
"""
reorganize_papers.py — 一次性整理脚本

把 papers/ 下的论文从旧 NN_author_year 格式迁移到 author_year 格式：
- 去除 NN_ 前缀，合并重复条目（BFS 时期同一论文多份拷贝）
- 从 SS API 补全 doi / title / authors
- 删除旧产物（analysis_refs.md, session_*.jsonl, refs_failed.[ts].md 等）

用法:
    python scripts/reorganize_papers.py           # 执行
    python scripts/reorganize_papers.py --dry-run # 只打印计划，不改动
"""
from __future__ import annotations

import re
import shutil
import sys
import time
import difflib
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from database import models  # noqa: E402

try:
    from scripts.config import SS_API_KEY  # noqa: E402
except ImportError:
    SS_API_KEY = ""

DRY_RUN = "--dry-run" in sys.argv
PAPERS_ROOT = ROOT / "papers"
DB_PATH = ROOT / "kb.db"
_SS_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"
_SS_HEADERS = {"x-api-key": SS_API_KEY} if SS_API_KEY else {}

# 长名根论文的目标 stem（无法用正则解析）
SPECIAL_PAPER = {
    "stem": "Organizing for AI Innovation Insights From an Empirical Exploration of US Patents",
    "new_stem": "organizing_ai_patents",
    "search_title": "Organizing for AI Innovation: Insights From an Empirical Exploration of US Patents",
}

# 标题行中表示"非标题"的跳过词
_SKIP_EXACT = {
    "nber working paper series", "uc berkeley", "working papers",
    "title", "authors", "publication date", "abstract", "keywords",
    "jel classification", "acknowledgements", "acknowledgments",
}
_SKIP_PREFIX = ("please note", "please not", "http", "doi:", "jel ", "keywords:")


def _is_noise(clean: str) -> bool:
    """判断一行是否是非标题噪声（页眉、作者行等）。"""
    if (
        len(clean) < 12
        or clean.lower() in _SKIP_EXACT
        or any(clean.lower().startswith(p) for p in _SKIP_PREFIX)
        or re.match(r"^\d+_", clean)
    ):
        return True
    # 短行且像人名：≤4词，首字母大写，无小写内容词
    words = clean.split()
    if len(words) <= 4 and all(
        (w[0].isupper() if w[0].isalpha() else True) for w in words
    ) and not any(w.islower() and len(w) > 2 for w in words):
        return True
    return False


def _extract_title_from_md(paper_dir: Path) -> str | None:
    """从论文主 .md 文件中找出可用标题（支持多行拼接）。"""
    for md in sorted(paper_dir.glob("*.md")):
        if any(x in md.name for x in ("analysis", "refs_failed", "download", "session")):
            continue
        lines = [
            ln.strip().lstrip("# ").strip()
            for ln in md.read_text("utf-8", errors="ignore").split("\n")
            if ln.strip()
        ]
        i = 0
        while i < len(lines):
            clean = lines[i]
            i += 1
            if _is_noise(clean):
                continue
            # 找到候选首行；若行太短且不完整，尝试拼接后续碎片行
            title_parts = [clean]
            CONTINUES = ("and", "or", "in", "of", "to", "the", "a", "an",
                         "for", "by", "from", "with", "on", "at")
            while i < len(lines):
                last = title_parts[-1].rstrip()
                ends_incomplete = (
                    len(" ".join(title_parts)) < 80
                    and not last.endswith((".", "?", "!", "∗", "*"))
                    and last.split()[-1].lower() in CONTINUES
                )
                nxt = lines[i]
                # 只拼接短碎片（<25字符），不含作者标记（数字后缀、•等）
                nxt_is_fragment = (
                    len(nxt) < 25
                    and not re.search(r"[•·@]|\d{4}", nxt)
                    and not _is_noise(nxt)
                )
                if ends_incomplete or nxt_is_fragment:
                    if not nxt_is_fragment and not ends_incomplete:
                        break
                    title_parts.append(nxt)
                    i += 1
                else:
                    break
            return " ".join(title_parts)
    return None


def _query_ss(title: str, year: str | None) -> dict | None:
    """调 SS Search API，返回最匹配的条目（ratio ≥ 0.55）。"""
    try:
        r = httpx.get(
            _SS_SEARCH,
            params={"query": title, "fields": "externalIds,title,year,authors", "limit": 5},
            headers=_SS_HEADERS,
            timeout=12,
        )
        if r.status_code != 200:
            print(f"    SS HTTP {r.status_code}: {r.text[:100]}")
            return None
        for item in r.json().get("data", []):
            if year and str(item.get("year", "")) != str(year):
                continue
            ratio = difflib.SequenceMatcher(
                None, title.lower(), (item.get("title") or "").lower()
            ).ratio()
            if ratio >= 0.55:
                # 从 externalIds 提取 DOI
                ext = item.get("externalIds") or {}
                item["doi"] = ext.get("DOI")
                return item
    except Exception as exc:
        print(f"    SS error: {exc}")
    return None


def _safe_delete(path: Path, label: str) -> None:
    if DRY_RUN:
        print(f"    [DRY DEL] {label}")
        return
    path.unlink(missing_ok=True)
    print(f"    [DEL] {label}")


def main() -> None:
    engine = create_engine(f"sqlite:///{DB_PATH}")
    with Session(engine) as session:
        papers = session.execute(
            select(models.Paper).order_by(models.Paper.id)
        ).scalars().all()

        # ── Step 1: 确定每篇论文的 new_stem 和可用标题 ──────────────────────────
        print("=== Step 1: 计算 new_stem ===")
        plan: list[dict] = []  # {paper, old_stem, new_stem, title, year_str}

        for p in papers:
            old_stem = p.stem
            paper_dir = PAPERS_ROOT / old_stem

            # 特殊长名论文
            if old_stem == SPECIAL_PAPER["stem"]:
                plan.append({
                    "paper": p,
                    "old_stem": old_stem,
                    "new_stem": SPECIAL_PAPER["new_stem"],
                    "title": SPECIAL_PAPER["search_title"],
                    "year_str": str(p.year) if p.year else None,
                })
                continue

            # 已处理过（无 NN_ 前缀）→ 幂等跳过
            if not re.match(r"^\d+_", old_stem):
                print(f"  [SKIP] {old_stem} — already clean")
                plan.append({
                    "paper": p,
                    "old_stem": old_stem,
                    "new_stem": old_stem,
                    "title": p.title or old_stem,
                    "year_str": str(p.year) if p.year else None,
                })
                continue

            m = re.match(r"^\d+_(.+?)_(\d{4})$", old_stem)
            if not m:
                print(f"  [WARN] 无法解析 stem: {old_stem}，跳过")
                continue
            lastname, year_str = m.group(1), m.group(2)
            new_stem = f"{lastname}_{year_str}"
            title = _extract_title_from_md(paper_dir) or old_stem

            plan.append({
                "paper": p,
                "old_stem": old_stem,
                "new_stem": new_stem,
                "title": title,
                "year_str": year_str,
            })
            print(f"  {old_stem} → {new_stem}")

        # ── Step 2: 检测重复（same new_stem = same paper） ──────────────────────
        print("\n=== Step 2: 检测重复论文 ===")
        by_new_stem: dict[str, list[dict]] = {}
        for entry in plan:
            by_new_stem.setdefault(entry["new_stem"], []).append(entry)

        keepers: list[dict] = []   # 保留的条目
        duplicates: list[dict] = []  # 需要删除的重复条目

        for ns, group in by_new_stem.items():
            group.sort(key=lambda x: x["paper"].id)
            keepers.append(group[0])
            for dup in group[1:]:
                print(f"  [DUP] {dup['old_stem']} → 合并到 {group[0]['old_stem']} (→ {ns})")
                duplicates.append({"dup": dup, "keeper": group[0]})

        # ── Step 3: 查询 SS API 补全元数据（仅对 keeper） ───────────────────────
        print("\n=== Step 3: SS API 元数据补全 ===")
        meta: dict[str, dict] = {}  # old_stem → {doi, title, authors, year}

        for entry in keepers:
            old_stem = entry["old_stem"]
            title = entry["title"]
            year_str = entry["year_str"]

            print(f"  查询: {title[:70]!r}  year={year_str}")
            ss = _query_ss(title, year_str)
            time.sleep(1.5)  # SS 限速保护

            def _norm_title(t: str) -> str:
                # 全大写标题转 title case
                if t and t == t.upper() and len(t) > 5:
                    # 保留 常见缩写（AI、US、UK 等）
                    words = t.split()
                    return " ".join(
                        w if len(w) <= 3 else w.capitalize()
                        for w in words
                    )
                return t

            if ss:
                authors = [a["name"] for a in (ss.get("authors") or [])[:5]]
                raw_title = ss.get("title") or title
                meta[old_stem] = {
                    "doi": ss.get("doi"),
                    "title": _norm_title(raw_title),
                    "authors": authors,
                    "year": ss.get("year") or (int(year_str) if year_str else None),
                }
                print(f"    ✓ DOI={meta[old_stem]['doi']!r}  title={meta[old_stem]['title'][:50]!r}")
            else:
                meta[old_stem] = {
                    "doi": None,
                    "title": _norm_title(title),
                    "authors": [],
                    "year": int(year_str) if year_str else entry["paper"].year,
                }
                print(f"    ✗ SS 未找到，保留本地解析标题")

        if DRY_RUN:
            print("\n=== DRY RUN 完成，以下变更将被执行 ===")
            for entry in keepers:
                m_data = meta[entry["old_stem"]]
                print(f"  {entry['old_stem']:40s} → {entry['new_stem']:30s}  doi={m_data['doi']}")
            print(f"\n  重复条目将被删除: {[d['dup']['old_stem'] for d in duplicates]}")
            return

        # ── Step 4: 重指向 edges（duplicate → keeper），删除重复 DB 记录 ────────
        print("\n=== Step 4: 合并重复论文 DB 记录 ===")
        for item in duplicates:
            dup_p = item["dup"]["paper"]
            keep_p = item["keeper"]["paper"]

            # 更新引用了 dup_p.id 的边
            for edge in session.execute(
                select(models.Edge).where(models.Edge.from_paper_id == dup_p.id)
            ).scalars().all():
                if edge.to_paper_id == keep_p.id:
                    session.delete(edge)  # 自环，丢弃
                else:
                    edge.from_paper_id = keep_p.id

            for edge in session.execute(
                select(models.Edge).where(models.Edge.to_paper_id == dup_p.id)
            ).scalars().all():
                if edge.from_paper_id == keep_p.id:
                    session.delete(edge)  # 自环，丢弃
                else:
                    edge.to_paper_id = keep_p.id

            session.flush()
            print(f"  [DEL DB] {dup_p.stem} (id={dup_p.id})")
            session.delete(dup_p)
            session.flush()

            # 删除重复目录
            dup_dir = PAPERS_ROOT / item["dup"]["old_stem"]
            if dup_dir.exists():
                print(f"  [RMDIR] papers/{item['dup']['old_stem']}")
                shutil.rmtree(dup_dir)

        # ── Step 5: 重命名目录、更新 DB、清理旧文件 ────────────────────────────
        print("\n=== Step 5: 重命名目录 + 更新 DB + 清理旧文件 ===")
        for entry in keepers:
            old_stem = entry["old_stem"]
            new_stem = entry["new_stem"]
            paper = entry["paper"]
            m_data = meta[old_stem]

            old_dir = PAPERS_ROOT / old_stem
            new_dir = PAPERS_ROOT / new_stem

            # 重命名目录
            if old_dir != new_dir:
                if new_dir.exists():
                    print(f"  [WARN] {new_stem}/ 已存在，跳过重命名 {old_stem}")
                elif old_dir.exists():
                    old_dir.rename(new_dir)
                    print(f"  [MV] papers/{old_stem} → papers/{new_stem}")

            # 重命名主 .md 文件
            if new_dir.exists():
                old_md = new_dir / f"{old_stem}.md"
                new_md = new_dir / f"{new_stem}.md"
                if old_md.exists() and not new_md.exists():
                    old_md.rename(new_md)
                    print(f"       {old_stem}.md → {new_stem}.md")

            # 更新 DB 记录
            paper.stem = new_stem
            paper.doi = m_data["doi"] or paper.doi
            paper.title = m_data["title"] or paper.title
            if m_data["authors"]:
                paper.authors_json = m_data["authors"]
            if m_data["year"]:
                paper.year = m_data["year"]

            # 更新路径
            paper.refs_path = None  # analysis_refs.md 即将删除
            if new_dir.exists():
                new_md = new_dir / f"{new_stem}.md"
                if new_md.exists():
                    paper.md_path = f"papers/{new_stem}/{new_stem}.md"
                insight = new_dir / "analysis_insight.md"
                if insight.exists():
                    paper.insight_path = f"papers/{new_stem}/analysis_insight.md"

            # 清理旧产物
            if new_dir.exists():
                for f in [*new_dir.glob("analysis_refs.md"),
                           *new_dir.glob("session_*.jsonl"),
                           *new_dir.glob("download_analysis.md"),
                           *new_dir.glob("refs_failed.*.md")]:   # 带时间戳的
                    _safe_delete(f, f"papers/{new_stem}/{f.name}")

        # ── Step 6: 全局清理 ────────────────────────────────────────────────────
        print("\n=== Step 6: 全局清理 ===")
        for rel in ["papers/_manifest.json", "network.json"]:
            target = ROOT / rel
            if target.exists():
                _safe_delete(target, rel)

        session.commit()
        print("\n✓ 整理完成。")
        print(f"  保留论文: {len(keepers)} 篇")
        print(f"  合并重复: {len(duplicates)} 篇")


if __name__ == "__main__":
    main()
