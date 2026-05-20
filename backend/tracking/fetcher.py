"""reference_fetcher bridge — re-exports from legacy services/reference_fetcher.py.

The legacy module is thread-safe and contains the full _KeyPool implementation.
This module is a thin re-export so tracking.* code imports from here rather than
directly from the Flask services package.
"""
from __future__ import annotations

import sys
import os

# Ensure the repo root (where services/ lives) is on sys.path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from services.reference_fetcher import (  # noqa: E402, F401
    ReferenceItem,
    _KeyPool,
    _ss_pool,
    _openalex_mailto,
    _reconstruct_abstract,
    normalize_doi,
    fetch_cited_by,
    fetch_references,
    merge_dedup,
    _ss_cited_by,
    _oa_cited_by,
    _ss_references,
    _oa_references,
    _cr_references,
)

# reference_fetcher.py uses functools.lru_cache but doesn't import functools at module
# top in the original — add a compatibility shim so the import above succeeds.
try:
    import functools  # noqa: F401 (may be needed by the module at import time)
except ImportError:
    pass
