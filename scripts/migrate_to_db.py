"""migrate_to_db.py —— 一次性迁移：把现有 papers/ 与 network.json 灌入 SQLite。

幂等：以 papers.stem 为去重键，已存在则 UPDATE 字段。
不修改任何文件系统产物。

用法：
    python scripts/migrate_to_db.py [--db kb.db] [--report migration_report.md]

退出码：
    0  全部成功（含跳过的悬空边，已计入 report）
    1  IO/数据库致命错误
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from database import Base, enable_sqlite_foreign_keys  # noqa: E402
from database import models  # noqa: E402  注册 mapper
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

PAPERS_DIR = ROOT / "papers"
NETWORK_JSON = ROOT / "network.json"
MANIFEST_JSON = PAPERS_DIR / "_manifest.json"

# 匹配 analysis_insight.md / analysis_refs.md 头部的元信息（容错：可能不全）
_RE_TITLE_HEAD = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_RE_YEAR_IN_STEM = re.compile(r"_(\d{4})$")
_RE_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.IGNORECASE)


# ──────────────────────────────────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────────────────────────────────


@dataclass
class PaperRecord:
    stem: str
    path: Path
    title: str | None = None
    year: int | None = None
    doi: str | None = None
    pdf_path: str | None = None
    md_path: str | None = None
    insight_path: str | None = None
    refs_path: str | None = None
    has_insight: bool = False
    source: str = "ref"
    depth: int | None = None


@dataclass
class Report:
    papers_total: int = 0
    papers_inserted: int = 0
    papers_updated: int = 0
    edges_total: int = 0
    edges_inserted: int = 0
    edges_source_dup: int = 0           # 源数据 network.json 自身重复
    edges_existing: int = 0             # 已存在于 DB（重跑场景）
    edges_updated: int = 0              # 命中既有 key，但内容（to/title）变了 → 已更新
    edges_dangling: list[dict] = field(default_factory=list)
    edges_conflicts: list[dict] = field(default_factory=list)  # 内容变化明细
    edges_dup_details: list[dict] = field(default_factory=list)  # 重复边明细
    missing_fields: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────
# 解析层
# ──────────────────────────────────────────────────────────────────────────


def _rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"无法解析 {path}: {e}") from e


def _parse_insight_head(path: Path, stem: str) -> tuple[str | None, str | None]:
    """从 analysis_insight.md 头部提取 (title, doi)；头部一般 < 4KB。

    若头部标题等于 stem（项目惯例：`# 01_giczy_2022`），视为占位、不当真实标题。
    """
    if not path.exists():
        return None, None
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:4096]
    except OSError:
        return None, None
    title = None
    m = _RE_TITLE_HEAD.search(head)
    if m:
        candidate = m.group(1).strip()
        if candidate and candidate != stem:
            title = candidate
    doi = None
    m = _RE_DOI.search(head)
    if m:
        doi = m.group(1).rstrip(".,;)")
    return title, doi


def _pick_pdf(dir_path: Path, stem: str) -> Path | None:
    """优先 <stem>.pdf；否则取目录下首个 .pdf（排除 refs/）。"""
    named = dir_path / f"{stem}.pdf"
    if named.exists():
        return named
    for entry in sorted(dir_path.glob("*.pdf")):
        return entry
    return None


def _scan_papers() -> list[PaperRecord]:
    """扫 papers/ 子目录，跳过 refs/ 等内部目录。"""
    if not PAPERS_DIR.exists():
        return []
    records: list[PaperRecord] = []
    for entry in sorted(PAPERS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith(".") or entry.name == "__pycache__":
            continue
        stem = entry.name
        insight = entry / "analysis_insight.md"
        refs = entry / "analysis_refs.md"
        md = entry / f"{stem}.md"
        pdf = _pick_pdf(entry, stem)
        title, doi = _parse_insight_head(insight, stem)
        year = None
        m = _RE_YEAR_IN_STEM.search(stem)
        if m:
            try:
                year = int(m.group(1))
            except ValueError:
                year = None
        rec = PaperRecord(
            stem=stem,
            path=entry,
            title=title,
            year=year,
            doi=doi,
            pdf_path=_rel(pdf) if pdf else None,
            md_path=_rel(md) if md.exists() else None,
            insight_path=_rel(insight) if insight.exists() else None,
            refs_path=_rel(refs) if refs.exists() else None,
            has_insight=insight.exists(),
        )
        records.append(rec)
    return records


def _apply_manifest(records: list[PaperRecord]) -> None:
    """根据 _manifest.json 标注 source / depth。"""
    manifest = _load_json(MANIFEST_JSON).get("analyzed", {})
    by_stem = {r.stem: r for r in records}
    for key, meta in manifest.items():
        rec = by_stem.get(key)
        if not rec:
            continue
        rec.depth = meta.get("depth")
        rec.source = "root" if meta.get("depth") == 0 else "ref"


# ──────────────────────────────────────────────────────────────────────────
# 写入层
# ──────────────────────────────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _upsert_paper(session, rec: PaperRecord, report: Report,
                  existing_by_stem: dict[str, models.Paper]) -> models.Paper:
    """Upsert by stem。

    覆盖策略分两类：
      - 文件系统派生字段（path/status/source）：总是覆盖（哪怕变 None），
        因为这些字段必须反映当前磁盘状态，否则重跑会留下 stale row。
      - 元数据字段（title/year/doi）：best-effort，仅在新值非空时填入，
        避免一次解析失败就把已知元数据擦掉。

    `existing_by_stem` 由调用方一次性查出，避免每条记录 N+1 单点查询。
    """
    existing = existing_by_stem.get(rec.stem)
    status = "analyzed" if rec.has_insight else "pending"
    # 总是覆盖
    fs_fields = {
        "pdf_path": rec.pdf_path,
        "md_path": rec.md_path,
        "insight_path": rec.insight_path,
        "refs_path": rec.refs_path,
        "status": status,
        "source": rec.source,
    }
    # best-effort 填充
    meta_fields = {
        "title": rec.title,
        "year": rec.year,
        "doi": rec.doi,
    }

    if existing is None:
        paper = models.Paper(stem=rec.stem, **fs_fields, **meta_fields)
        if rec.has_insight:
            paper.analyzed_at = _utcnow()
        session.add(paper)
        session.flush()
        report.papers_inserted += 1
        return paper

    for k, v in fs_fields.items():
        setattr(existing, k, v)
    for k, v in meta_fields.items():
        if v is not None:
            setattr(existing, k, v)
    if rec.has_insight and existing.analyzed_at is None:
        existing.analyzed_at = _utcnow()
    elif not rec.has_insight:
        # insight.md 被删除：清空 analyzed_at 以反映当前状态
        existing.analyzed_at = None
    report.papers_updated += 1
    return existing


def _load_edges(session, paper_by_stem: dict[str, int], report: Report) -> None:
    data = _load_json(NETWORK_JSON)
    edges = data.get("edges", []) or []
    report.edges_total = len(edges)

    # 一次性把现有的 backward edges 全部加载到内存索引，避免 N+1 单点查询
    from sqlalchemy import select as _select
    existing_edges = session.execute(
        _select(models.Edge).where(models.Edge.direction == "backward")
    ).scalars().all()
    existing_by_key: dict[tuple[int, str, int | None], models.Edge] = {
        (e.from_paper_id, e.direction, e.ref_index): e for e in existing_edges
    }

    seen_in_run: set[tuple[int, str, int | None]] = set()
    for edge in edges:
        src = edge.get("from")
        dst = edge.get("to")
        idx = edge.get("index")
        title = edge.get("title")
        src_id = paper_by_stem.get(src)
        dst_id = paper_by_stem.get(dst)
        if not src_id or not dst_id:
            report.edges_dangling.append({
                "from": src, "to": dst, "index": idx,
                "reason": "missing_paper" if (src_id is None) ^ (dst_id is None) else "both_missing",
            })
            continue

        key = (src_id, "backward", idx)
        if key in seen_in_run:
            report.edges_source_dup += 1
            report.edges_dup_details.append({
                "from": src, "to": dst, "index": idx, "title": title,
                "scope": "source_data",
            })
            continue
        seen_in_run.add(key)

        existing = existing_by_key.get(key)
        if existing is None:
            session.add(models.Edge(
                from_paper_id=src_id,
                to_paper_id=dst_id,
                direction="backward",
                ref_index=idx,
                ref_title=title,
            ))
            report.edges_inserted += 1
            continue

        # 既有边：检测内容是否变化
        if existing.to_paper_id != dst_id or (existing.ref_title or "") != (title or ""):
            report.edges_conflicts.append({
                "from": src, "index": idx,
                "old_to_id": existing.to_paper_id,
                "new_to_stem": dst,
                "old_title": existing.ref_title,
                "new_title": title,
            })
            existing.to_paper_id = dst_id
            existing.ref_title = title
            report.edges_updated += 1
        else:
            report.edges_existing += 1


# ──────────────────────────────────────────────────────────────────────────
# Report
# ──────────────────────────────────────────────────────────────────────────


def _write_report(report: Report, missing_records: list[PaperRecord], out_path: Path) -> None:
    lines: list[str] = []
    lines.append(f"# Migration Report — {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("## Papers")
    lines.append(f"- 总数：{report.papers_total}")
    lines.append(f"- 新增：{report.papers_inserted}")
    lines.append(f"- 更新：{report.papers_updated}")
    lines.append("")
    lines.append("## Edges")
    lines.append(f"- 总数：{report.edges_total}")
    lines.append(f"- 新增：{report.edges_inserted}")
    lines.append(f"- 已存在未变：{report.edges_existing}")
    lines.append(f"- 内容更新：{report.edges_updated}")
    lines.append(f"- 源数据重复：{report.edges_source_dup}")
    lines.append(f"- 悬空：{len(report.edges_dangling)}")
    if report.edges_dangling:
        lines.append("")
        lines.append("### 悬空边详情")
        for e in report.edges_dangling[:50]:
            lines.append(f"- from=`{e['from']}` → to=`{e['to']}` (index={e['index']}, reason={e['reason']})")
        if len(report.edges_dangling) > 50:
            lines.append(f"- ... 省略 {len(report.edges_dangling) - 50} 条")
    if report.edges_dup_details:
        lines.append("")
        lines.append("### 源数据重复边")
        for e in report.edges_dup_details[:50]:
            lines.append(f"- from=`{e['from']}` → to=`{e['to']}` (index={e['index']})")
    if report.edges_conflicts:
        lines.append("")
        lines.append("### 内容更新明细（同一 key 改了目标或标题）")
        for c in report.edges_conflicts[:50]:
            lines.append(
                f"- from=`{c['from']}` index={c['index']}: "
                f"old_to_id={c['old_to_id']} → new_to=`{c['new_to_stem']}`; "
                f"title `{c['old_title']}` → `{c['new_title']}`"
            )
    if missing_records:
        lines.append("")
        lines.append("## 缺关键字段的论文")
        for rec in missing_records:
            missing = []
            if not rec.pdf_path: missing.append("pdf")
            if not rec.md_path: missing.append("md")
            if not rec.insight_path: missing.append("insight")
            if not rec.title: missing.append("title")
            if not rec.year: missing.append("year")
            lines.append(f"- `{rec.stem}` → 缺 {', '.join(missing)}")
    if report.errors:
        lines.append("")
        lines.append("## 错误")
        for err in report.errors:
            lines.append(f"- {err}")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────────────────────────────────


def run_migration(report_path: Path) -> Report:
    from database import _db_url

    # 预先校验 network.json：避免 papers 已提交后才崩溃，留下半成品 DB。
    if NETWORK_JSON.exists():
        try:
            _load_json(NETWORK_JSON)
        except RuntimeError as e:
            raise RuntimeError(f"network.json 校验失败，已中止迁移：{e}") from e

    engine = create_engine(_db_url(), future=True)
    enable_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)  # 兜底；正常应由 alembic upgrade head 建表
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    report = Report()
    records = _scan_papers()
    report.papers_total = len(records)
    _apply_manifest(records)

    missing_records: list[PaperRecord] = []

    try:
        with Session() as s:
            # 一次性预加载 papers 索引，避免 _upsert_paper 内 N+1 单点查询
            from sqlalchemy import select as _select
            existing_papers = s.execute(_select(models.Paper)).scalars().all()
            existing_by_stem = {p.stem: p for p in existing_papers}

            paper_by_stem: dict[str, int] = {}
            for rec in records:
                try:
                    paper = _upsert_paper(s, rec, report, existing_by_stem)
                    paper_by_stem[rec.stem] = paper.id
                except Exception as e:
                    report.errors.append(f"paper {rec.stem}: {e!r}")
                    continue
                if not rec.has_insight or not rec.pdf_path or not rec.title:
                    missing_records.append(rec)
            try:
                _load_edges(s, paper_by_stem, report)
                # papers + edges 同事务原子提交：edges 失败时 papers 一起回滚
                s.commit()
            except Exception as e:
                report.errors.append(f"edges/transaction: {e!r}")
                s.rollback()
                raise
    finally:
        # 无论成功失败都写报告，便于操作员排查
        _write_report(report, missing_records, report_path)
        engine.dispose()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="一次性把 papers/ + network.json 灌入 SQLite。")
    parser.add_argument("--db", help="覆盖 KB_DB_PATH（默认 kb.db）")
    parser.add_argument("--report", default="migration_report.md", help="报告输出路径")
    args = parser.parse_args()

    if args.db:
        os.environ["KB_DB_PATH"] = args.db

    report_path = Path(args.report).resolve()
    try:
        report = run_migration(report_path)
    except Exception as e:
        print(f"FATAL: {e!r}", file=sys.stderr)
        return 1

    print(
        f"papers: {report.papers_inserted} new / {report.papers_updated} updated / "
        f"{report.papers_total} total"
    )
    print(
        f"edges:  {report.edges_inserted} new / {report.edges_existing} existing / "
        f"{report.edges_updated} updated / {report.edges_source_dup} source-dup / "
        f"{len(report.edges_dangling)} dangling / {report.edges_total} total"
    )
    print(f"report -> {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
