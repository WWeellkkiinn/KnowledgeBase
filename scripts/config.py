"""External API credentials loaded from environment variables.

Historically this module hard-coded secrets and lived outside git. After the
Docker / ECS migration, secrets are injected through `.env` (see `.env.example`)
and this file ships in version control. All original module-level names are
preserved so existing imports (`from scripts.config import ...`,
`from config import ...`) keep working with no caller changes.

If an env var is unset, the value falls back to an empty string — callers
already guard against missing keys (the old hard-coded values were optional
for most code paths).
"""
from __future__ import annotations

import os

# Unpaywall OA discovery (free, requires only an email for rate-limit identification)
UNPAYWALL_EMAIL = os.environ.get("UNPAYWALL_EMAIL", "")

# Daily digest mailer (SMTP / 163 mail)
DIGEST_FROM = os.environ.get("DIGEST_FROM", "")
DIGEST_TO = os.environ.get("DIGEST_TO", "")
DIGEST_AUTH_CODE = os.environ.get("DIGEST_AUTH_CODE", "")

# CORE API (full-text discovery)
CORE_API_KEY = os.environ.get("CORE_API_KEY", "")

# Semantic Scholar API
SS_API_KEY = os.environ.get("SS_API_KEY", "")
