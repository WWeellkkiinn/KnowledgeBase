# Settings Patch for Auth/Tenant/Admin (Agent C)

## INSTALLED_APPS — append

```python
"sesame",       # django-sesame (already in requirements.txt; needs app entry for migrations)
"admin_ext",    # custom admin extensions (pending-users view)
```

Already present and correct (no change needed):
- `accounts`, `tenants`, `core`
- `SESAME_MAX_AGE`, `SESAME_ONE_TIME`, `AUTHENTICATION_BACKENDS` — all configured

## New Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SUPERADMIN_EMAIL` | (none) | Explicit email to notify on new registrations; falls back to all `is_superuser=True` users |
| `MAGIC_LINK_BASE_URL` | `http://localhost:8000` | Base URL for magic-link emails (e.g. `https://kb.example.com`) |

Add to `.env` / `.env.example`:

```
DJANGO_SUPERADMIN_EMAIL=admin@example.com
MAGIC_LINK_BASE_URL=https://kb.example.com
```

## CSRF

For API clients sending JSON (non-browser), NinjaAPI uses session auth which requires CSRF
on state-changing endpoints. Either:

1. Ensure `X-CSRFToken` header is sent from the Vue frontend (Agent D handles this), OR
2. Add `CSRF_TRUSTED_ORIGINS` for your domain:

```python
CSRF_TRUSTED_ORIGINS = ["https://kb.example.com"]
```

No change required for dev with `DEBUG=True` and same-origin requests.

## requirements.txt — no additions needed

All dependencies already present: `django-sesame>=3.2`, `celery`, `redis`, `django-ninja>=1.3`.

## Migration note

Run after applying this patch:

```bash
python manage.py migrate
```

`sesame` ships its own migrations (token invalidation table). `admin_ext` has no models.
`accounts` and `tenants` migrations still need to be generated:

```bash
python manage.py makemigrations accounts tenants
python manage.py migrate
```
