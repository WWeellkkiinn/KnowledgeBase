"""一次性脚本：把 journals seed 入库 + 给已有 papers 链接 journal_id。

用法：
  python scripts/backfill_journals.py                    # 全量
  python scripts/backfill_journals.py --only-tierless    # 只补还没 journal_id 的
  python scripts/backfill_journals.py --max 5            # 限量（debug）

幂等。运行多次只会更新 metadata。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# 允许从项目根直接 `python scripts/backfill_journals.py`
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from database import SessionLocal, models  # noqa: E402
from services.journal_service import JournalService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only-tierless", action="store_true",
                        help="只处理 papers.journal_id 为 NULL 的论文")
    parser.add_argument("--max", type=int, default=0,
                        help="最多处理 N 篇（0=不限制）")
    parser.add_argument("--sleep", type=float, default=1.0,
                        help="每次 OpenAlex 调用之间的间隔秒数")
    args = parser.parse_args()

    svc = JournalService()
    with SessionLocal() as session:
        seed_report = svc.bootstrap_from_seed(session)
        session.commit()
        print(f"[seed] {seed_report}")

        stmt = select(models.Paper)
        if args.only_tierless:
            stmt = stmt.where(models.Paper.journal_id.is_(None))
        papers = session.execute(stmt).scalars().all()
        if args.max:
            papers = papers[:args.max]

        stats = {"linked": 0, "no_doi": 0, "no_journal": 0}
        for i, p in enumerate(papers, 1):
            if not p.doi:
                stats["no_doi"] += 1
                continue
            j = svc.attach_to_paper(session, p)  # meta=None → OpenAlex 兜底
            if j is None:
                stats["no_journal"] += 1
            else:
                stats["linked"] += 1
                tier = j.quality_tier if j.quality_tier is not None else "?"
                print(f"  [{i}/{len(papers)}] {p.stem} → {j.name} (Tier {tier})")
            session.commit()
            if args.sleep > 0 and i < len(papers):
                time.sleep(args.sleep)

        print(f"[backfill] {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
