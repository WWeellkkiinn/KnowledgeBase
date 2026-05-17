"""一次性 E2E 订阅测试：建订阅 → 生成检索式 → 拉 OpenAlex → LLM 评分 → 发邮件。
复用已有同描述订阅（已有 generated_queries 时跳过生成步骤）。
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# 加载 .env
ROOT = Path(__file__).parent.parent
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(ROOT))

from database import SessionLocal, models
from sqlalchemy import select
from services.subscription_service import SubscriptionService, score_pending_results
from services.llm_query_gen import generate_openalex_queries
from services.digest_service import send_subscription_digest

INTENT = "ABM 应用于宏观经济动态、金融市场、企业行为"


def main():
    db = SessionLocal()
    try:
        svc = SubscriptionService()

        # 1. 复用已有订阅，避免重复生成检索式
        existing = db.execute(
            select(models.Subscription).where(
                models.Subscription.description == INTENT,
                models.Subscription.type == "topic_search",
            )
        ).scalars().first()

        if existing and existing.generated_queries:
            sub = existing
            print(f"[1/5] 复用已有订阅 id={sub.id}，跳过生成检索式")
            print(f"[2/5] 已有检索式 {len(sub.generated_queries)} 条：")
            for q in sub.generated_queries:
                print(f"      - {q}")
        else:
            if existing:
                sub = existing
                print(f"[1/5] 复用已有订阅 id={sub.id}，但缺少检索式，重新生成")
            else:
                sub = svc.create(
                    db,
                    type="topic_search",
                    target={},
                    cron_expr="every 1d",
                    description=INTENT,
                    active=True,
                )
                db.commit()
                print(f"[1/5] 订阅已创建 id={sub.id}")

            t0 = time.time()
            print(f"[2/5] 调 LLM 生成检索式（预计 30-60s）…")
            queries = generate_openalex_queries(INTENT)
            sub.generated_queries = queries or None
            db.commit()
            print(f"    完成 {time.time()-t0:.1f}s, 生成 {len(queries)} 条:")
            for q in queries:
                print(f"      - {q}")

        # 3. 拉 OpenAlex
        t0 = time.time()
        print(f"[3/5] 拉 OpenAlex …")
        n = svc._execute_one(db, sub)
        db.commit()
        print(f"    完成 {time.time()-t0:.1f}s, 入库 {n} 条 subscription_results")

        # 4. LLM 评分
        t0 = time.time()
        print(f"[4/5] LLM 评分（max_score=120，预计数分钟）…")
        r = score_pending_results(db)
        print(f"    完成 {time.time()-t0:.1f}s, scored={r['scored']} errors={r['errors']}")

        # 5. 发邮件
        print(f"[5/5] 发邮件（min_score=0.65, limit=30）…")
        r = send_subscription_digest(db, subscription_id=sub.id)
        print(f"    {r}")

        print("\nDONE. 在 /inbox 也能看到。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
