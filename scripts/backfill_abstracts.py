"""一次性脚本：从 forward/backward_track_cache 回填 papers.abstract。"""
import json
import sqlite3
from pathlib import Path

DB = Path(__file__).parent.parent / "kb.db"


def _ingest(cur, table: str, list_key: str, abs_map: dict[str, str]) -> None:
    """从 cache 表的 JSON list 提取 (doi, abstract) 取最长摘要。"""
    for (raw,) in cur.execute(f"SELECT result_json FROM {table}"):
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        for item in data.get(list_key) or []:
            if not isinstance(item, dict):
                continue
            doi = (item.get("doi") or "").strip().lower()
            abs_ = (item.get("abstract") or "").strip()
            if doi and abs_ and len(abs_) > len(abs_map.get(doi, "")):
                abs_map[doi] = abs_


def main():
    with sqlite3.connect(DB) as conn:
        cur = conn.cursor()
        abs_map: dict[str, str] = {}

        print("loading forward cache...", flush=True)
        _ingest(cur, "forward_track_cache", "citing_papers", abs_map)
        print(f"  {len(abs_map)} unique DOIs after forward", flush=True)

        print("loading backward cache...", flush=True)
        _ingest(cur, "backward_track_cache", "referenced_papers", abs_map)
        print(f"  total unique DOIs with abstracts: {len(abs_map)}", flush=True)

        # 收集待回填论文
        rows = cur.execute(
            "SELECT id, doi FROM papers "
            "WHERE (abstract IS NULL OR abstract = '') "
            "  AND doi IS NOT NULL AND doi != ''"
        ).fetchall()
        print(f"  {len(rows)} papers without abstract", flush=True)

        # 批量更新
        updates: list[tuple[str, int]] = []
        for pid, doi in rows:
            doi_key = (doi or "").strip().lower()
            if not doi_key:
                continue
            abs_ = abs_map.get(doi_key)
            if abs_:
                updates.append((abs_, pid))

        BATCH = 1000
        for i in range(0, len(updates), BATCH):
            cur.executemany(
                "UPDATE papers SET abstract = ? WHERE id = ?",
                updates[i:i + BATCH],
            )
            print(f"  committed {min(i + BATCH, len(updates))}/{len(updates)}", flush=True)

        conn.commit()
        print(f"DONE: updated {len(updates)} papers", flush=True)

        # 最终统计
        total, has_abs = cur.execute(
            "SELECT COUNT(*), "
            "       COUNT(CASE WHEN abstract IS NOT NULL AND abstract != '' THEN 1 END) "
            "FROM papers"
        ).fetchone()
        core_total, core_has_abs = cur.execute(
            "SELECT COUNT(*), "
            "       COUNT(CASE WHEN abstract IS NOT NULL AND abstract != '' THEN 1 END) "
            "FROM papers WHERE is_core=1"
        ).fetchone()
        print(
            f"FINAL: {has_abs}/{total} papers have abstracts; "
            f"core: {core_has_abs}/{core_total}",
            flush=True,
        )


if __name__ == "__main__":
    main()
