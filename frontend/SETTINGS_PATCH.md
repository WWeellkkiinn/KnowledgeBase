# Frontend SaaS Layer — Settings Patch

## New Routes Added

| Path | Name | Public |
|---|---|---|
| `/register` | `register` | yes |
| `/pending-approval` | `pending-approval` | yes |
| `/auth/magic` | `magic-link-consume` | yes |
| `/account` | `account` | no (requires auth) |

## npm Dependencies

No new npm packages required. Uses only existing:
- `axios` (already present)
- `vue-router` (already present)
- `pinia` (already present)

## Cookie / CSRF / Session Contract (align with Agent C Django backend)

| Item | Value |
|---|---|
| Session cookie name | `sessionid` (Django default) |
| CSRF cookie name | `csrftoken` (Django default) |
| CSRF request header | `X-CSRFToken` |
| `SESSION_COOKIE_SAMESITE` | `Lax` (allows cross-origin POST via same-site link, blocks CSRF) |
| `SESSION_COOKIE_HTTPONLY` | `True` |
| `CSRF_COOKIE_HTTPONLY` | `False` (frontend JS must read it) |
| `withCredentials` | `true` on all axios requests |

Django backend must set `CSRF_TRUSTED_ORIGINS` and `CORS_ALLOW_CREDENTIALS = True` (if using corsheaders).

## API Endpoints Expected (Agent A/B must implement these shapes)

- `POST /api/auth/login` → `{ user: MeResponse }`
- `POST /api/auth/register` → `{ message: string }`
- `POST /api/auth/magic-link` → `{ message: string }`
- `GET /api/auth/magic/consume?sesame=<token>` → `{ user: MeResponse }`
- `GET /api/auth/me` → `MeResponse`
- `POST /api/auth/switch-tenant` → `{ ok: true }`
- `POST /api/auth/logout` → `{ ok: true }`

### MeResponse shape

```json
{
  "id": 1,
  "email": "user@example.com",
  "approval_status": "approved",
  "memberships": [
    { "tenant_id": 1, "tenant_name": "My Org", "tenant_slug": "my-org", "role": "admin" }
  ],
  "active_tenant_id": 1
}
```

### 403 pending_approval shape

```json
{ "code": "pending_approval", "detail": "..." }
```

### 403 rejected shape

```json
{ "code": "rejected", "detail": "..." }
```
