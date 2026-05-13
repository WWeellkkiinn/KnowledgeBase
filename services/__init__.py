"""KnowledgeBase Service 层。

设计原则（PLAN.md §6.2）：CLI 与 Web 共享同一份业务逻辑。M1.3 采用"最小抽离"：
services 类委托给 `scripts/` 中既有的纯函数，CLI 行为字节级保持，
后续 milestone 再把核心逻辑搬到 services/ 内部。

每个 service 构造参数 `db_session: Session | None = None`：
- None → 纯文件模式（M1.3 默认，CLI 路径走这里）
- Session → 双写文件 + DB（M1.4+ 任务队列、Web 路由走这里）
"""
from __future__ import annotations

from .search_service import SearchService
from .download_service import DownloadService
from .pdf2md_service import Pdf2MdService
from .analysis_service import AnalysisService
from .expand_service import ExpandService

__all__ = [
    "SearchService",
    "DownloadService",
    "Pdf2MdService",
    "AnalysisService",
    "ExpandService",
]
