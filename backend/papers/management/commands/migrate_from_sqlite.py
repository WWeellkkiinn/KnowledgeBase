"""One-shot cutover migration: SQLite (Flask era) → Postgres (Django SaaS).

All existing rows are attached to a single default tenant (slug "legacy"). The
script preserves primary keys so foreign-key references (edges, explore_pool
→ papers) stay valid.

Usage::

    docker compose run --rm django python manage.py migrate_from_sqlite \\
        --sqlite-path /data/kb.db \\
        --tenant-slug legacy \\
        --tenant-name "Legacy import" \\
        --admin-email admin@example.com \\
        --admin-password '<set me>'

After this command runs, the Postgres sequences for tables whose IDs were
preserved are bumped to MAX(id)+1 so future INSERTs don't collide.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


_TENANT_SCOPED_SEQUENCES = (
    "papers_paper",
    "papers_tag",
    "papers_papertag",
    "papers_paperfile",
    "journals_journal",
    "subscriptions_subscription",
    "subscriptions_subscriptionresult",
    "explore_explorepool",
    "explore_tagdict",
    "network_edge",
)


def _to_dt(val):
    """SQLite stores datetimes as ISO strings; coerce to aware UTC datetimes."""
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    s = str(val).replace("T", " ").rstrip("Z")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _coerce_json(val):
    if val is None:
        return None
    if isinstance(val, (list, dict)):
        return val
    try:
        return json.loads(val)
    except (TypeError, ValueError):
        return None


def _connect_sqlite(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise CommandError(f"SQLite file not found: {path}")
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


class Command(BaseCommand):
    help = "Migrate papers + journals + subscriptions + explore + tags + edges from a legacy SQLite kb.db into Postgres."

    def add_arguments(self, parser):
        parser.add_argument("--sqlite-path", required=True, type=str)
        parser.add_argument("--tenant-slug", default="legacy")
        parser.add_argument("--tenant-name", default="Legacy import")
        parser.add_argument("--admin-email", required=True)
        parser.add_argument("--admin-password", required=True)
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **opts):
        from tenants.models import Tenant
        from accounts.models import User, Membership
        from journals.models import Journal
        from papers.models import Paper
        from subscriptions.models import Subscription
        from explore.models import ExplorePool, TagDict
        from network.models import Edge

        path = Path(opts["sqlite_path"])
        sqlite_conn = _connect_sqlite(path)
        dry_run = opts["dry_run"]

        self.stdout.write(self.style.NOTICE(f"Source: {path}"))
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — will rollback at end"))

        # 0) tenant + super-admin
        tenant, created = Tenant.objects.get_or_create(
            slug=opts["tenant_slug"], defaults={"name": opts["tenant_name"]}
        )
        self.stdout.write(f"  tenant: {tenant.slug} (new={created})")

        admin, admin_created = User.objects.get_or_create(
            email=opts["admin_email"],
            defaults={
                "is_staff": True,
                "is_superuser": True,
                "approval_status": User.Approval.APPROVED,
                "approved_at": datetime.now(timezone.utc),
            },
        )
        if admin_created:
            admin.set_password(opts["admin_password"])
            admin.save()
        Membership.objects.get_or_create(
            user=admin, tenant=tenant, defaults={"role": Membership.Role.OWNER}
        )
        self.stdout.write(f"  admin: {admin.email} (new={admin_created})")

        with closing(sqlite_conn) as src:
            # 1) journals (shared, no tenant)
            journals = list(src.execute("SELECT * FROM journals"))
            for r in journals:
                Journal.objects.update_or_create(
                    id=r["id"],
                    defaults={
                        "issn": r["issn"],
                        "name": r["name"],
                        "publisher": r["publisher"],
                        "quality_tier": r["quality_tier"],
                        "is_predatory": bool(r["is_predatory"]),
                        "oa_status": r["oa_status"],
                        "source_dataset": r["source_dataset"],
                        "refreshed_at": _to_dt(r["refreshed_at"]),
                        "easyscholar_json": _coerce_json(r["easyscholar_json"]),
                        "easyscholar_fetched_at": _to_dt(r["easyscholar_fetched_at"]),
                    },
                )
            self.stdout.write(f"  journals: {len(journals)}")

            # 2) papers (tenant-scoped)
            papers = list(src.execute("SELECT * FROM papers"))
            for r in papers:
                Paper.objects.update_or_create(
                    id=r["id"],
                    defaults={
                        "tenant": tenant,
                        "stem": r["stem"] or "",
                        "doi": r["doi"],
                        "arxiv_id": r["arxiv_id"],
                        "title": r["title"],
                        "abstract": r["abstract"],
                        "authors_json": _coerce_json(r["authors_json"]),
                        "year": r["year"],
                        "journal_id": r["journal_id"],
                        "pdf_path": r["pdf_path"],
                        "md_path": r["md_path"],
                        "sha1": r["sha1"],
                        "refs_path": r["refs_path"],
                        "status": r["status"] or "pending",
                        "failure_reason": r["failure_reason"],
                        "source": r["source"] or "ref",
                        "is_core": bool(r["is_core"]),
                        "added_at": _to_dt(r["added_at"]) or datetime.now(timezone.utc),
                        "analyzed_at": _to_dt(r["analyzed_at"]),
                        "ai_summary": _coerce_json(r["ai_summary"]),
                        "ai_analyzed_at": _to_dt(r["ai_analyzed_at"]),
                    },
                )
            self.stdout.write(f"  papers: {len(papers)}")

            # 3) subscriptions
            subs = list(src.execute("SELECT * FROM subscriptions"))
            for r in subs:
                Subscription.objects.update_or_create(
                    id=r["id"],
                    defaults={
                        "tenant": tenant,
                        "sub_type": Subscription.SubType.TOPIC_SEARCH,
                        "description": r["description"] or "",
                        "generated_queries": _coerce_json(r["generated_queries"]),
                        "active": bool(r["active"]),
                        "target_ref": "",
                        "query_refreshed_at": _to_dt(r["query_refreshed_at"]),
                        "last_filled_at": _to_dt(r["last_filled_at"]),
                    },
                )
            self.stdout.write(f"  subscriptions: {len(subs)}")

            # 4) explore_pool — fill empty external_id with deterministic placeholder
            #    to satisfy the new unique(subscription, external_id) constraint.
            pool_rows = list(src.execute("SELECT * FROM explore_pool"))
            for r in pool_rows:
                ext_id = (r["external_id"] or "").strip() or f"legacy:{r['id']}"
                ExplorePool.objects.update_or_create(
                    id=r["id"],
                    defaults={
                        "tenant": tenant,
                        "subscription_id": r["subscription_id"],
                        "paper_id": r["paper_id"],
                        "raw_metadata_json": _coerce_json(r["raw_metadata_json"]),
                        "title_zh": r["title_zh"] or "",
                        "tags_json": _coerce_json(r["tags_json"]),
                        "research_question": r["research_question"] or "",
                        "methodology": r["methodology"] or "",
                        "key_findings_json": _coerce_json(r["key_findings_json"]),
                        "llm_reason": r["llm_reason"] or "",
                        "scored_at": _to_dt(r["scored_at"]),
                        "score_attempts": r["score_attempts"] or 0,
                        "action": r["action"],
                        "acted_at": _to_dt(r["acted_at"]),
                        "external_id": ext_id,
                    },
                )
            self.stdout.write(f"  explore_pool: {len(pool_rows)}")

            # 5) tag_dict (dedupe by (tenant, tag))
            tags = list(src.execute("SELECT * FROM tag_dict"))
            seen = set()
            inserted = 0
            for r in tags:
                key = (tenant.id, r["tag"])
                if key in seen:
                    continue
                seen.add(key)
                _, was_created = TagDict.objects.get_or_create(
                    tenant=tenant, tag=r["tag"],
                    defaults={
                        "source": r["source"] or "llm",
                        "alpha": r["alpha"] if r["alpha"] is not None else 0.5,
                        "beta": r["beta"] if r["beta"] is not None else 0.5,
                    },
                )
                if was_created:
                    inserted += 1
            self.stdout.write(f"  tag_dict: {inserted} new (source had {len(tags)})")

            # 6) edges (likely empty in current dataset but handle anyway)
            edges = list(src.execute("SELECT * FROM edges"))
            for r in edges:
                Edge.objects.update_or_create(
                    id=r["id"],
                    defaults={
                        "tenant": tenant,
                        "from_paper_id": r["from_paper_id"],
                        "to_paper_id": r["to_paper_id"],
                        "direction": r["direction"],
                        "ref_index": r["ref_index"],
                        "ref_title": r["ref_title"] or "",
                        "discovered_at": _to_dt(r["discovered_at"]) or datetime.now(timezone.utc),
                    },
                )
            self.stdout.write(f"  edges: {len(edges)}")

        # 7) bump Postgres sequences so SERIAL ids continue past the imported max
        with connection.cursor() as cursor:
            for table in _TENANT_SCOPED_SEQUENCES:
                cursor.execute(
                    f"SELECT setval(pg_get_serial_sequence(%s, 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 1))",
                    [table],
                )

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — rolling back"))
            raise CommandError("dry-run abort")
        self.stdout.write(self.style.SUCCESS("Migration complete."))
