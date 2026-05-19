"""检索词自迭代服务：每周用正信号论文驱动 LLM 刷新 OpenAlex 检索词。"""

from services.llm_client import chat_completion
from database import models
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import json, logging, re

logger = logging.getLogger(__name__)


def refresh_subscription_queries(db: Session, sub) -> dict:
    try:
        since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=60)
        stmt = select(models.SubscriptionResult).where(
            models.SubscriptionResult.subscription_id == sub.id,
            models.SubscriptionResult.found_at >= since,
            (models.SubscriptionResult.paper_id.isnot(None)) |
            (models.SubscriptionResult.llm_score >= 0.8),
        )
        positive_results = db.execute(stmt).scalars().all()
        positive_titles = []
        for result in positive_results:
            raw_metadata = result.raw_metadata_json or {}
            title = raw_metadata.get("title")
            if title:
                positive_titles.append(title)
            if len(positive_titles) >= 10:
                break
        saved_explore = db.execute(
            select(models.ExplorePool).where(
                models.ExplorePool.subscription_id == sub.id,
                models.ExplorePool.action == "saved",
                models.ExplorePool.found_at >= since,
            ).order_by(models.ExplorePool.acted_at.desc().nulls_last()).limit(10)
        ).scalars().all()
        for item in saved_explore:
            title = (item.raw_metadata_json or {}).get("title")
            if title:
                positive_titles.append(title)
        skipped_explore = db.execute(
            select(models.ExplorePool).where(
                models.ExplorePool.subscription_id == sub.id,
                models.ExplorePool.action == "skipped",
                models.ExplorePool.found_at >= since,
            ).order_by(models.ExplorePool.acted_at.desc().nulls_last()).limit(10)
        ).scalars().all()
        negative_titles = []
        for item in skipped_explore:
            title = (item.raw_metadata_json or {}).get("title")
            if title:
                negative_titles.append(title)

        if len(positive_results) < 3:
            return {"refreshed": False, "reason": "insufficient_signal", "added": [], "removed": []}

        all_stmt = select(models.SubscriptionResult).where(
            models.SubscriptionResult.subscription_id == sub.id,
            models.SubscriptionResult.found_at >= since,
            models.SubscriptionResult.scored_at.isnot(None),
        )
        all_results = db.execute(all_stmt).scalars().all()
        grouped = {}
        for result in all_results:
            source_query = (result.raw_metadata_json or {}).get("source_query")
            if not source_query:
                continue
            grouped.setdefault(source_query, []).append(result)

        hit_rates = {}
        for query, results in grouped.items():
            hit_rates[query] = sum(1 for result in results if result.llm_score >= 0.65) / len(results)

        stats = dict(sub.query_stats_json or {})
        existing_queries = list(sub.generated_queries or [])
        to_remove = []
        for q in existing_queries:
            if q not in stats:
                stats[q] = {"low_weeks": 0, "last_hit_rate": None}
            hit_rate = hit_rates.get(q)
            if hit_rate is not None and hit_rate < 0.10:
                stats[q]["low_weeks"] += 1
            if hit_rate is not None and hit_rate >= 0.10:
                stats[q]["low_weeks"] = 0
            if hit_rate is not None:
                stats[q]["last_hit_rate"] = hit_rate
            if stats[q]["low_weeks"] >= 2:
                to_remove.append(q)

        system_prompt = (
            "You are a search query optimizer for an academic paper subscription system.\n"
            "Given a researcher's interest description, their current OpenAlex boolean queries with hit rates, \n"
            "and titles of highly relevant recent papers, suggest improved search queries.\n"
            "Output ONLY a JSON object: {\"add\": [\"query1\", ...], \"remove\": [\"query1\", ...]}\n"
            "- \"add\": 1-3 new OpenAlex boolean queries covering topics in the positive papers but not well-covered by current queries. Use the same format: \"term\" AND (\"variant1\" OR \"variant2\")\n"
            "- \"remove\": existing queries the LLM thinks are redundant or off-topic (ONLY those with low_weeks >= 2 from the provided list)\n"
            "No prose, no markdown."
        )
        query_info = [
            {
                "query": q,
                "hit_rate": stats.get(q, {}).get("last_hit_rate"),
                "low_weeks": stats.get(q, {}).get("low_weeks", 0),
            }
            for q in existing_queries
        ]
        user_prompt = f"Research interest: {sub.description}\n\nCurrent queries and hit rates:\n{json.dumps(query_info, ensure_ascii=False)}\n\nPositive signal paper titles (imported or highly relevant):\n{json.dumps(positive_titles, ensure_ascii=False)}\n\nNegative signal paper titles (user marked as irrelevant):\n{json.dumps(negative_titles, ensure_ascii=False)}\n\nOutput JSON now."
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        response = chat_completion(messages, max_tokens=8192)

        match = re.search(r"\{[\s\S]*\}", response)
        parsed = json.loads(match.group(0)) if match else {}
        added = []
        for q in parsed.get("add", []):
            if isinstance(q, str) and 2 <= len(q) <= 500 and q not in existing_queries and q not in added:
                added.append(q)

        llm_remove = []
        for q in parsed.get("remove", []):
            if q in existing_queries and stats.get(q, {}).get("low_weeks", 0) >= 2:
                llm_remove.append(q)
        to_remove = [q for q in to_remove if q in llm_remove]

        if len(to_remove) >= len(existing_queries) and existing_queries:
            keep = max(
                existing_queries,
                key=lambda q: stats.get(q, {}).get("last_hit_rate")
                if stats.get(q, {}).get("last_hit_rate") is not None else -1,
            )
            to_remove = [q for q in to_remove if q != keep]

        removed_set = set(to_remove)
        new_queries = [q for q in existing_queries if q not in removed_set]
        for q in added:
            if q not in new_queries:
                new_queries.append(q)
            if len(new_queries) >= 8:
                break
        added = [q for q in added if q in new_queries]

        sub.generated_queries = new_queries
        sub.query_stats_json = {k: v for k, v in stats.items() if k in new_queries}
        sub.query_refreshed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        return {"refreshed": True, "added": added, "removed": to_remove, "reason": "ok"}
    except Exception as e:
        logger.warning("refresh_subscription_queries failed: %s", e)
        return {"refreshed": False, "reason": "error", "added": [], "removed": []}
