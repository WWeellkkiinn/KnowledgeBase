# Settings Patch — Agent A (papers / journals / citations / ai_analysis)

## INSTALLED_APPS (append to existing list in config/settings.py)

```python
"papers",
"journals",
"citations",
"ai_analysis",
```

## core/api.py — router registration

```python
from papers.api import router as papers_router
from citations.api import router as citations_router
from citations.api import papers_citations_router

api.add_router("/papers", papers_router, tags=["papers"])
api.add_router("/papers", papers_citations_router, tags=["citations"])
api.add_router("/citations", citations_router, tags=["citations"])
```

## requirements.txt — no new third-party deps needed

All deps (httpx, celery, django-ninja) are already listed.
`pypdf` may be needed if MinerU cloud fallback is added locally — currently optional.

## Migrations

Run after merging INSTALLED_APPS:
```
python manage.py makemigrations papers journals
python manage.py migrate
python manage.py seed_journals
```

## Notes

- `citations` app has no models (no migration needed); it only reads `papers.Paper`
  and `journals.Journal`.
- `ai_analysis` app has no models; tags are stored in `papers.Tag` / `papers.PaperTag`.
- `journals.Journal` is referenced by `papers.Paper.journal_id` (IntegerField, not FK)
  to avoid cross-app migration dependency ordering issues. Main agent may choose to
  convert to a real ForeignKey after merging.
