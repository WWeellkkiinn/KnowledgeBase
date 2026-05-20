"""Pdf2MdService — PDF → Markdown via MinerU cloud (mineru.net).

SaaS rewrite drops the local subprocess fallback (only mineru-cloud is used in
prod). If KB_PDF2MD_PROVIDER != "mineru-cloud", raises explicitly so misconfigs
fail loud instead of falling back to a missing scripts/pdf2md.py.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable, Optional

from .pdf2md_cloud import convert as _cloud_convert

_log = logging.getLogger(__name__)


class Pdf2MdService:
    """Thin wrapper so callers don't depend on the cloud module directly."""

    def convert(
        self,
        pdf_path: Path,
        output_dir: Path,
        on_progress: Optional[Callable[[str, str], None]] = None,
        shutdown_event=None,
    ) -> dict:
        provider = os.environ.get("KB_PDF2MD_PROVIDER", "mineru-cloud").strip().lower()
        if provider != "mineru-cloud":
            raise RuntimeError(
                f"Unsupported KB_PDF2MD_PROVIDER={provider!r}; SaaS build only ships mineru-cloud"
            )
        return _cloud_convert(
            Path(pdf_path),
            Path(output_dir),
            on_progress=on_progress,
            stop_event=shutdown_event,
        )
