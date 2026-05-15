"""pdf2md_cloud.py —— MinerU 官方云 API（mineru.net）适配层。

环境变量：
- KB_MINERU_API_URL    默认 https://mineru.net；必须 https 且 host 在白名单内
- KB_MINERU_API_KEY    必填（Bearer token）
- KB_MINERU_ALLOWED_HOSTS  逗号分隔，预签名 PUT URL 与 zip 下载 URL 的 host 白名单
                            （默认 mineru.net + aliyuncs.com 后缀）
- KB_MINERU_POLL_INTERVAL  默认 5（秒）
- KB_MINERU_POLL_TIMEOUT   默认 600（秒）
- KB_MINERU_ZIP_MAX_BYTES  默认 209715200（200MB）

安全约束：
1. PUT 上传目标 URL 必须 https + host 在白名单内 → 杜绝把 PDF 发给攻击者
2. 下载 zip URL 同样校验 + 设最大字节数 → 杜绝 SSRF + zip bomb
3. PDF 流式上传（不整 read 到内存）

进度回调：on_progress(step, msg) 让上层（worker）转发到 progress_bus。
中断响应：传入 _shutdown_event 时，轮询 sleep 用 Event.wait，可被外部立即唤醒。
"""
from __future__ import annotations

import io
import logging
import os
import re
import threading
import time
import urllib.parse
import zipfile
from pathlib import Path
from typing import Callable, Optional

import httpx

_log = logging.getLogger(__name__)

_DEFAULT_BASE = "https://mineru.net"
# MinerU 上传/下载 URL host 白名单。收敛到具体 bucket / CDN 子域，避免顶级
# .aliyuncs.com / .myqcloud.com 放行任意第三方 OSS bucket（攻击者若能控制
# MinerU API 响应，可让 worker 把 PDF 上传到他们的 bucket）。
# 用户自托管 MinerU 时通过 KB_MINERU_ALLOWED_HOSTS 显式声明对应 bucket 子域。
_DEFAULT_ALLOWED = (
    "mineru.net,"
    "cdn-mineru.openxlab.org.cn,"  # MinerU 官方下载 CDN（实测）
    "mineru-pdf.oss-cn-shanghai.aliyuncs.com,"  # MinerU 官方上传 OSS bucket
    "mineru-pdf.oss-accelerate.aliyuncs.com"
)
_HTTP_TIMEOUT = 60


def _sanitize(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name)[:120]


def _extract_sections(md_path: Path) -> list[dict]:
    sections: list[dict] = []
    with open(md_path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            m = re.match(r"^(#{1,3})\s+(.+)", line.rstrip())
            if m:
                sections.append({
                    "id": len(sections),
                    "level": len(m.group(1)),
                    "title": m.group(2).strip(),
                    "line": lineno,
                })
    return sections


def _unwrap_data(resp_json):
    """MinerU 接口返回常用两种壳：{code, data: {...}} 或裸 {...}。统一展开。"""
    if isinstance(resp_json, dict) and isinstance(resp_json.get("data"), (dict, list)):
        return resp_json["data"]
    return resp_json


def _first_present(d: dict, *keys):
    if not isinstance(d, dict):
        return None
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def _allowed_hosts() -> set[str]:
    raw = os.environ.get("KB_MINERU_ALLOWED_HOSTS", _DEFAULT_ALLOWED)
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def _validate_external_url(url: str, role: str) -> None:
    """对第三方返回的 URL 做 scheme + host 白名单校验，防 SSRF / token 外发。

    role：用于报错描述，如 "upload"、"download"、"api-base"。
    """
    if not isinstance(url, str) or not url:
        raise MinerUCloudError(f"{role} url empty")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "https":
        raise MinerUCloudError(f"{role} url not https: {parsed.scheme}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise MinerUCloudError(f"{role} url has no host")
    allowed = _allowed_hosts()
    if not any(host == a or host.endswith("." + a) for a in allowed):
        raise MinerUCloudError(f"{role} host not in allowlist: {host}")


ProgressCb = Callable[[str, str], None]


class MinerUCloudError(RuntimeError):
    pass


def _interruptible_sleep(seconds: float, stop_event: Optional[threading.Event]) -> bool:
    """Event.wait 模拟 time.sleep；stop_event 触发时立即返回 True。"""
    if stop_event is None:
        time.sleep(seconds)
        return False
    return stop_event.wait(seconds)


def convert(
    pdf_path: Path,
    output_dir: Path,
    *,
    on_progress: Optional[ProgressCb] = None,
    timeout: Optional[float] = None,
    stop_event: Optional[threading.Event] = None,
) -> dict:
    """同步调用 MinerU 云 API，结果落盘到 output_dir。

    output_dir 必须由调用方按 stem 区分给入（pdf2md_service 默认会做）。
    返回：{"md_path": str, "sections": [...]} 或 {"error": str}。

    重要：不再做"md_path 已存在直接复用"短路 —— 上层（worker / sha1 dedup）才是
    去重边界；此处短路会让残缺/失败遗留的 md 被错误地标记为成功。
    """
    api_key = os.environ.get("KB_MINERU_API_KEY", "").strip()
    if not api_key:
        return {"error": "KB_MINERU_API_KEY not configured"}
    base = os.environ.get("KB_MINERU_API_URL", _DEFAULT_BASE).rstrip("/")
    try:
        _validate_external_url(base, "api-base")
    except MinerUCloudError as e:
        return {"error": str(e)}

    poll_interval = float(os.environ.get("KB_MINERU_POLL_INTERVAL", "5") or 5)
    poll_timeout = float(timeout if timeout is not None else os.environ.get("KB_MINERU_POLL_TIMEOUT", "600") or 600)
    zip_max_bytes = int(os.environ.get("KB_MINERU_ZIP_MAX_BYTES", str(200 * 1024 * 1024)) or 0)

    stem = _sanitize(pdf_path.stem)
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"{stem}.md"

    def _emit(step: str, msg: str) -> None:
        if on_progress is not None:
            try:
                on_progress(step, msg)
            except Exception:
                pass

    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT, headers=headers) as client:
            # 1) 申请上传 URL
            _emit("pdf2md.request_url", "申请上传链接…")
            r = client.post(
                f"{base}/api/v4/file-urls/batch",
                json={
                    "enable_formula": True,
                    "enable_table": True,
                    "language": "auto",
                    "files": [{"name": pdf_path.name, "is_ocr": False}],
                },
            )
            r.raise_for_status()
            data = _unwrap_data(r.json())
            batch_id = _first_present(data, "batch_id", "batchId")
            file_urls = _first_present(data, "file_urls", "fileUrls") or []
            if not batch_id or not file_urls:
                raise MinerUCloudError(f"unexpected response: {data}")
            upload_url = file_urls[0]
            _validate_external_url(upload_url, "upload")

            # 2) 流式 PUT 上传（不把整个 PDF 加载到内存；不带 Authorization）
            _emit("pdf2md.upload", "上传 PDF…")
            file_size = pdf_path.stat().st_size
            with open(pdf_path, "rb") as f, httpx.Client(timeout=300) as up_client:
                up_headers = {"Content-Length": str(file_size)}
                up = up_client.put(upload_url, content=f, headers=up_headers)
            up.raise_for_status()

            # 3) 轮询，支持外部 shutdown 立即唤醒
            deadline = time.time() + poll_timeout
            full_zip_url: Optional[str] = None
            first_iter = True
            while time.time() < deadline:
                if not first_iter:
                    if _interruptible_sleep(poll_interval, stop_event):
                        raise MinerUCloudError("shutdown requested")
                first_iter = False
                pr = client.get(f"{base}/api/v4/extract-results/batch/{batch_id}")
                pr.raise_for_status()
                pdata = _unwrap_data(pr.json())
                results = []
                if isinstance(pdata, dict):
                    results = _first_present(pdata, "extract_result", "results") or []
                elif isinstance(pdata, list):
                    results = pdata
                if results:
                    first = results[0]
                    state = str(_first_present(first, "state", "status") or "").lower()
                    _emit("pdf2md.poll", f"MinerU 状态：{state or 'pending'}")
                    if state in ("done", "completed", "success"):
                        full_zip_url = _first_present(first, "full_zip_url", "zip_url")
                        if not full_zip_url:
                            raise MinerUCloudError(f"completed but no zip url: {first}")
                        break
                    if state in ("failed", "error"):
                        raise MinerUCloudError(f"MinerU task failed: {first}")
                else:
                    _emit("pdf2md.poll", "排队中…")
            if not full_zip_url:
                raise MinerUCloudError(f"MinerU timed out (>{poll_timeout}s)")
            _validate_external_url(full_zip_url, "download")

            # 4) 流式下载 zip 并强制大小上限
            _emit("pdf2md.download", "下载结果…")
            zip_bytes = _stream_download(full_zip_url, zip_max_bytes)
            md_content = _pick_markdown_from_zip(zip_bytes, stem, zip_max_bytes)
            if not md_content:
                raise MinerUCloudError("zip contains no markdown")

            md_path.write_text(md_content, encoding="utf-8")
            return {
                "md_path": str(md_path),
                "sections": _extract_sections(md_path),
            }
    except MinerUCloudError as e:
        return {"error": str(e)}
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except httpx.HTTPError as e:
        return {"error": f"network error: {e}"}
    except Exception as e:
        _log.exception("pdf2md cloud unexpected")
        return {"error": f"unexpected: {e}"}


def _stream_download(url: str, max_bytes: int) -> bytes:
    """流式下载并限制最大字节；超过即抛 MinerUCloudError。"""
    buf = bytearray()
    with httpx.stream("GET", url, timeout=120, follow_redirects=False) as resp:
        resp.raise_for_status()
        for chunk in resp.iter_bytes(chunk_size=64 * 1024):
            buf.extend(chunk)
            if max_bytes > 0 and len(buf) > max_bytes:
                raise MinerUCloudError(f"zip exceeds size limit {max_bytes}")
    return bytes(buf)


def _pick_markdown_from_zip(content: bytes, stem: str, max_extract_bytes: int) -> str:
    """从 zip 字节流挑出 Markdown：优先与 stem 同名，其次任意 .md。

    防 zip-bomb：解压前看声明大小；超过 max_extract_bytes 直接拒；
    防 zip-slip：只用条目名查找/读内容，不写盘到 zip 内任意路径。
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        return ""
    md_infos = [zi for zi in zf.infolist() if zi.filename.lower().endswith(".md")]
    if not md_infos:
        return ""
    # 优先 stem 同名
    preferred = [zi for zi in md_infos if Path(zi.filename).stem.lower() == stem.lower()]
    pick = (preferred or md_infos)[0]
    if max_extract_bytes > 0 and pick.file_size > max_extract_bytes:
        raise MinerUCloudError(f"md entry too large: {pick.file_size}")
    with zf.open(pick) as f:
        return f.read(max_extract_bytes if max_extract_bytes > 0 else -1).decode(
            "utf-8", errors="replace"
        )
