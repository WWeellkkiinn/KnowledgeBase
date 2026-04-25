"""SSRN downloader — 通过 patchright 浏览器绕过 Cloudflare Turnstile。

优先尝试 CDP 接管已运行的真实 Chrome（:9222）；
不可用时自动启动 patchright headed 浏览器。
"""
import re
from pathlib import Path

CDP_URL = "http://127.0.0.1:9222"

_CF_TITLES = {
    "请稍候…", "Just a moment...", "Just a moment", "",
    "正在进行安全验证", "Security | papers.ssrn.com",
    "Attention Required! | Cloudflare",
}


def can_handle(url: str) -> bool:
    return "ssrn.com" in url


def download(url: str, output_path: str) -> tuple[bool, str]:
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        return False, "patchright not installed (pip install patchright)"

    page = None
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.connect_over_cdp(CDP_URL)
                ctx = browser.contexts[0] if browser.contexts else browser.new_context(accept_downloads=True)
            except Exception:
                browser = p.chromium.launch(headless=False, args=["--start-maximized"])
                ctx = browser.new_context(accept_downloads=True, no_viewport=True)

            page = ctx.new_page()
            return _do_download(page, url, output_path)
    except Exception as e:
        return False, f"browser fail: {type(e).__name__}: {e}"
    finally:
        if page is not None:
            try:
                page.close()
            except Exception:
                pass


def _wait_cf_clear(page, timeout: int = 60000):
    import time
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        if page.title() not in _CF_TITLES:
            return
        try:
            frame = page.frame_locator("iframe[src*='challenges.cloudflare.com']")
            cb = frame.locator("input[type='checkbox']")
            cb.first.wait_for(state="visible", timeout=2000)
            cb.first.click(timeout=3000)
        except Exception:
            pass
        time.sleep(1)


def _do_download(page, url: str, output_path: str) -> tuple[bool, str]:
    if "/delivery.cfm" in url.lower():
        warm_url = "https://www.ssrn.com/"
        m = re.search(r"abstractid=(\d+)", url, re.I)
        if m:
            warm_url = f"https://papers.ssrn.com/sol3/papers.cfm?abstract_id={m.group(1)}"
        page.goto(warm_url, wait_until="domcontentloaded", timeout=60000)
        _wait_cf_clear(page, timeout=60000)
        with page.expect_download(timeout=60000) as dl_info:
            try:
                page.goto(url, referer=warm_url, timeout=60000)
            except Exception:
                pass
        dl_info.value.save_as(str(output_path))
        size_kb = Path(output_path).stat().st_size // 1024
        return True, f"ok  {size_kb} KB  →  {output_path}"

    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    _wait_cf_clear(page, timeout=60000)
    try:
        page.locator("#onetrust-accept-btn-handler").click(timeout=3000)
    except Exception:
        pass
    btn = page.locator(
        'a:has-text("Download This Paper"), a:has-text("Download"), '
        'a[href*="Delivery.cfm"], a[href*="/sol3/Delivery"]'
    ).first
    btn.wait_for(timeout=60000, state="visible")
    with page.expect_download(timeout=90000) as dl_info:
        btn.click()
    dl_info.value.save_as(str(output_path))
    size_kb = Path(output_path).stat().st_size // 1024
    return True, f"ok  {size_kb} KB  →  {output_path}"
