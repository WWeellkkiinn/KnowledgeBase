from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger('services').setLevel(logging.INFO)
_log = logging.getLogger(__name__)

from sqlalchemy import delete, select

from database import SessionLocal, models
from services import BackwardTrackService, ForwardTrackService


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--forward-only", action="store_true")
    group.add_argument("--backward-only", action="store_true")
    parser.add_argument("--clear-cache", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.clear_cache:
            do_forward = not args.backward_only
            do_backward = not args.forward_only
            tables = []
            if do_forward:
                tables.append('forward_track_cache')
            if do_backward:
                tables.append('backward_track_cache')
            _log.warning('将清空以下表的全部缓存：%s', ', '.join(tables))
            confirm = input('确认清空？输入 yes 继续：').strip().lower()
            if confirm != 'yes':
                _log.info('已取消。')
                return
            if do_forward:
                db.execute(delete(models.ForwardTrackCache))
                _log.info('已清空 forward_track_cache')
            if do_backward:
                db.execute(delete(models.BackwardTrackCache))
                _log.info('已清空 backward_track_cache')
            db.commit()

        papers = db.execute(
            select(models.Paper)
            .where(models.Paper.is_core.is_(True))
            .where(models.Paper.doi.is_not(None))
            .where(models.Paper.doi != "")
            .order_by(models.Paper.id.asc())
        ).scalars().all()

        total = len(papers)
        backward = BackwardTrackService(db_session=db)
        forward = ForwardTrackService(db_session=db)

        for i, paper in enumerate(papers, start=1):
            prefix = f"[{i}/{total}]"
            if not args.forward_only:
                try:
                    result = backward.track(paper.doi, refresh=True, from_paper_id=paper.id)
                    db.commit()
                    print(f"{prefix} backward {paper.doi}: {result.get('references_count', 0)}")
                except Exception as exc:
                    db.rollback()
                    print(f"{prefix} backward {paper.doi}: failed: {exc}")

            if not args.backward_only:
                try:
                    result = forward.track(paper.doi, refresh=True, from_paper_id=paper.id)
                    db.commit()
                    print(f"{prefix} forward {paper.doi}: {result.get('citing_count', 0)}")
                except Exception as exc:
                    db.rollback()
                    print(f"{prefix} forward {paper.doi}: failed: {exc}")

            if i < total:
                time.sleep(2)
    finally:
        db.close()


if __name__ == "__main__":
    main()
