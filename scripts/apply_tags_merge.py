import argparse
import datetime
import json
import os
import shutil
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "kb.db"
PLAN_PATH = ROOT / ".tag_merge_plan.json"
REPORT_PATH = ROOT / ".tag_merge_apply_dryrun.txt"


def load_mapping():
    with PLAN_PATH.open("r", encoding="utf-8") as f:
        mapping = json.load(f).get("mapping_flat")
    if not isinstance(mapping, dict):
        raise ValueError(".tag_merge_plan.json missing mapping_flat dict")
    return mapping


def parse_tags(raw):
    if not raw:
        return []
    tags = json.loads(raw)
    return [tag for tag in tags if isinstance(tag, str)] if isinstance(tags, list) else []


def merge_tags(tags, mapping):
    merged, seen = [], set()
    for tag in tags:
        tag = mapping.get(tag, tag)
        if tag not in seen:
            seen.add(tag)
            merged.append(tag)
    return merged


def scan(conn, mapping):
    aliases = set(mapping)
    affected = []
    counts = {alias: 0 for alias in mapping}
    remaining = set()
    rows = conn.execute("SELECT id, tags_json FROM explore_pool").fetchall()

    for row_id, raw_tags in rows:
        before = parse_tags(raw_tags)
        for tag in before:
            if tag in aliases:
                counts[tag] += 1
        after = merge_tags(before, mapping)
        if after != before:
            affected.append((row_id, before, after))
        remaining.update(tag for tag in after if tag in aliases)

    hits = {alias: count for alias, count in counts.items() if count}
    return {
        "total": len(rows),
        "affected": affected,
        "hits": hits,
        "unmatched": sorted(alias for alias, count in counts.items() if not count),
        "remaining": sorted(remaining),
    }


def summary(result, mapping, title="Tag merge dry-run summary"):
    return "\n".join([
        title,
        f"Total rows scanned: {result['total']}",
        f"Affected rows: {len(result['affected'])}",
        f"Aliases in mapping: {len(mapping)}",
        f"Aliases hit: {len(result['hits'])}",
        f"Unmatched aliases: {len(result['unmatched'])}",
    ])


def dry_run(conn, mapping):
    result = scan(conn, mapping)
    lines = [summary(result, mapping), "", "Sample diffs:"]
    for row_id, before, after in result["affected"][:5]:
        lines += [
            f"Row id: {row_id}",
            f"  before: {json.dumps(before, ensure_ascii=False)}",
            f"  after : {json.dumps(after, ensure_ascii=False)}",
        ]

    lines += ["", "Per-alias hit counts:"]
    lines += [f"{alias}: {result['hits'][alias]}" for alias in sorted(result["hits"])]
    lines += ["", "Unmatched aliases:"]
    lines += result["unmatched"] or ["(none)"]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(summary(result, mapping))


def backup_db():
    backup = ROOT / f"kb.db.bak.{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(DB_PATH, backup)
    backups = sorted(ROOT.glob("kb.db.bak.*"), key=os.path.getmtime, reverse=True)
    for path in backups[3:]:
        path.unlink()
    return backup


def apply_merge(conn, mapping):
    backup = backup_db()
    before = scan(conn, mapping)
    cur = conn.cursor()
    cur.execute("BEGIN")
    try:
        cur.executemany(
            "UPDATE explore_pool SET tags_json = ? WHERE id = ?",
            [(json.dumps(after, ensure_ascii=False), row_id)
             for row_id, _before, after in before["affected"]],
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"FATAL: apply_merge failed, rolled back: {e}")
        raise

    after = scan(conn, mapping)
    if after["remaining"]:
        print("ERROR: aliases remain after apply:")
        print("\n".join(after["remaining"]))
        raise SystemExit(1)
    print(
        f"Done. Updated {len(before['affected'])} rows, "
        f"applied {len(before['hits'])} aliases, backup: {backup}"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    mapping = load_mapping()
    with sqlite3.connect(DB_PATH) as conn:
        apply_merge(conn, mapping) if args.apply else dry_run(conn, mapping)


if __name__ == "__main__":
    main()
