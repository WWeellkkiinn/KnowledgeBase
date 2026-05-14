"""fill_missing_dois.py — 对数据库中无 DOI 但有标题的论文批量查询 DOI。

用法：
    python scripts/fill_missing_dois.py [--core-only] [--dry-run]

--core-only  只处理核心论文（默认处理全部）
--dry-run    只打印会做什么，不写库
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from database import SessionLocal, models
from sqlalchemy import select
from services.doi_resolver import resolve_doi
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
_log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-only", action="store_true")
    parser.add_argument("--write", action="store_true", help="实际写入数据库（默认只预览）")
    args = parser.parse_args()
    args.dry_run = not args.write

    session = SessionLocal()
    try:
        stmt = (
            select(models.Paper)
            .where(models.Paper.title.isnot(None))
            .where(models.Paper.title != "")
            .where((models.Paper.doi.is_(None)) | (models.Paper.doi == ""))
        )
        if args.core_only:
            stmt = stmt.where(models.Paper.is_core.is_(True))
        papers = session.execute(stmt).scalars().all()

        _log.info("找到 %d 篇无 DOI 论文", len(papers))
        found = 0
        for i, paper in enumerate(papers, 1):
            _log.info("[%d/%d] 查询: %s", i, len(papers), (paper.title or "")[:70])
            doi = resolve_doi(paper.title or "")
            if doi:
                # 检查该 DOI 是否已被其他论文占用
                conflict = session.execute(
                    select(models.Paper.id).where(
                        models.Paper.doi == doi,
                        models.Paper.id != paper.id,
                    ).limit(1)
                ).first()
                if conflict:
                    _log.info("  → %s（已被 paper_id=%d 占用，跳过）", doi, conflict[0])
                else:
                    _log.info("  → %s", doi)
                    found += 1
                    if not args.dry_run:
                        paper.doi = doi
            else:
                _log.info("  → 未找到")
            time.sleep(1)  # 避免触发限速

        if not args.dry_run and found:
            session.commit()
            _log.info("已写入 %d 条 DOI", found)
        else:
            _log.info("预览模式，未写入。共能补全 %d 条（加 --write 实际执行）", found)
    finally:
        try:
            session.rollback()
        except Exception:
            pass
        session.close()


if __name__ == "__main__":
    main()
