"""
本地 pre-commit hook：拦截敏感信息泄露。

扫描 staged 改动（git diff --cached -U0），匹配到以下任一种就阻止提交：
  1. 已知 token / 邮箱授权码字面值
  2. 项目内 IP / 邮箱 / SSH key 名
  3. 真实公网 IPv4（白名单文档示例 + RFC1918 + 回环 + 链路本地除外）
  4. 高熵 base64-urlsafe / hex 字符串（可能是 token）
  5. .env / *.key / *.pem / credentials.* 之类的敏感文件

不阻止提交 → 退出 0；命中 → 打印 "什么 + 在哪 + 怎么办" + 退出 1。
绕过：commit 时加 --no-verify（不推荐，除非你确认是误报）。

安装：bash deploy/install-hooks.sh
"""
from __future__ import annotations
import os
import re
import subprocess
import sys
from typing import Iterable

# ─────────────────────────────────────────────────────────────────────
# 黑名单：项目特定的已知敏感值（一次性枚举，命中即拦）
# ─────────────────────────────────────────────────────────────────────
PROJECT_DENY: list[tuple[str, str]] = [
    # (人类可读名, 字面值)
    ("163 邮箱授权码", "JMkxr4XYmxvWbpmQ"),
    ("Welkin 163 邮箱", "asd1334119588@"),
    ("Welkin Gmail", "harveyxiacn@"),
    ("ECS root SSH key 名", "id_ed25519_nopass"),
    ("客户 ECS 公网 IP", "8.163.93.142"),
    ("本地代理出口 IP", "183.63.119.93"),
]

# ─────────────────────────────────────────────────────────────────────
# 通用规则
# ─────────────────────────────────────────────────────────────────────
# 真实公网 IPv4（粗筛后再过滤白名单）
IP_RE = re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b")

# IPv4 白名单：不算泄露的
def _ip_is_safe(ip: str) -> bool:
    try:
        parts = [int(p) for p in ip.split(".")]
        if len(parts) != 4 or any(p < 0 or p > 255 for p in parts):
            return True  # 不合法 IP，跳过
    except ValueError:
        return True
    a, b, c, d = parts
    # 回环
    if a == 127:
        return True
    # RFC1918 私网
    if a == 10:
        return True
    if a == 172 and 16 <= b <= 31:
        return True
    if a == 192 and b == 168:
        return True
    # 链路本地
    if a == 169 and b == 254:
        return True
    # 全 0 / 全 1
    if (a, b, c, d) == (0, 0, 0, 0) or (a, b, c, d) == (255, 255, 255, 255):
        return True
    # 多播 / 保留
    if a >= 224:
        return True
    # 文档示例（RFC 5737 / RFC 6890 + 通俗 1.2.3.4）
    if (a, b) == (192, 0) and c == 2:
        return True
    if (a, b) == (198, 51) and c == 100:
        return True
    if (a, b) == (203, 0) and c == 113:
        return True
    if (a, b, c, d) == (1, 2, 3, 4):
        return True
    if (a, b, c, d) == (8, 8, 8, 8):  # Google DNS 文档常用
        return True
    return False

# 真实公网邮箱（noreply / example.com / 占位符除外）
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

def _email_is_safe(addr: str) -> bool:
    a = addr.lower()
    if "noreply" in a or "no-reply" in a or "donotreply" in a:
        return True
    if "@example.com" in a or "@example.org" in a:
        return True
    # 测试 fixture 常用域名（RFC 2606 + 习惯用法）
    if "@test.com" in a or "@test.local" in a or "@test.test" in a or "@localhost" in a:
        return True
    if "user@" in a or "your-email@" in a or "replace" in a:
        return True
    # 学术 API 标识邮箱（unpaywall / openalex mailto 占位）—— 用 .env 注入，正文出现说明是文档示例
    if "@institution" in a or "@your-domain" in a:
        return True
    return False

# 高熵随机串：base64-urlsafe 36+ 字符 或 hex 40+ 字符
HIGH_ENTROPY_BASE64 = re.compile(r"\b[A-Za-z0-9_\-]{36,}\b")
HIGH_ENTROPY_HEX = re.compile(r"\b[a-f0-9]{40,}\b")

# 高熵字符串白名单（git 对象 hash、npm hash、知名常量、长测试/函数名）
ENTROPY_SAFE_CONTEXT = re.compile(
    r"(sha256:|sha512:|sha384:|integrity\s*=|"
    r"# noqa:|# type:|googletagmanager|cloudflare|"
    r"^[+-]\s*//|^[+-]\s*#|"  # 注释行
    r"\bdef\s+test_|\bdef\s+\w+_test|\bclass\s+Test\w+|"  # pytest 命名
    r"\basync\s+def\s+test_)",
    re.IGNORECASE,
)

# 敏感文件名（不允许 stage）
SENSITIVE_FILE_PATTERNS = [
    re.compile(p)
    for p in [
        r"^\.env$",
        r"^\.env\.local$",
        r"^\.env\.production$",
        r".*\.pem$",
        r".*\.key$",
        r".*_rsa$",
        r".*_ed25519$",
        r".*credentials\..*",
        r".*secrets\..*",
    ]
]

# 文件后缀白名单：不扫的（二进制/产物）
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".tar", ".gz",
            ".db", ".sqlite", ".sqlite3", ".woff", ".woff2", ".ttf",
            ".lock", ".lockb"}

# 路径白名单：不扫的（自身就是规则定义文件，会有"敏感"字面量）
SKIP_PATHS = {
    "deploy/git-hooks/pre-commit",
    "deploy/git-hooks/pre-commit.py",
    "deploy/install-hooks.sh",
}


def _run(*args: str) -> str:
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    return r.stdout


def _staged_files() -> list[str]:
    out = _run("git", "diff", "--cached", "--name-only", "--diff-filter=AM")
    return [p for p in out.splitlines() if p]


def _staged_added_lines(path: str) -> Iterable[tuple[int, str]]:
    """yield (line_no_in_new, added_line_text) for given staged file."""
    out = _run("git", "diff", "--cached", "-U0", "--", path)
    cur_line = 0
    for raw in out.splitlines():
        if raw.startswith("@@"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw)
            if m:
                cur_line = int(m.group(1))
            continue
        if raw.startswith("+++") or raw.startswith("---"):
            continue
        if raw.startswith("+"):
            yield cur_line, raw[1:]
            cur_line += 1
        elif raw.startswith(" "):
            cur_line += 1
        elif raw.startswith("-"):
            pass  # 删除不算


def _check_file(path: str) -> list[str]:
    """检查单个 staged 文件，返回违规消息列表（空 = 干净）。"""
    violations: list[str] = []

    if path in SKIP_PATHS:
        return violations
    ext = os.path.splitext(path)[1].lower()
    if ext in SKIP_EXT:
        return violations

    # 1. 敏感文件名
    for pat in SENSITIVE_FILE_PATTERNS:
        if pat.match(os.path.basename(path)) or pat.match(path):
            violations.append(
                f"  ✘ {path}: 敏感文件名命中规则 `{pat.pattern}`。"
                f" 如果是占位模板，加 .example 后缀或换路径"
            )
            return violations  # 文件名命中后内容不必再扫

    # 2. 内容扫描
    for line_no, text in _staged_added_lines(path):
        # 2a. 项目特定黑名单
        for label, lit in PROJECT_DENY:
            if lit in text:
                violations.append(
                    f"  ✘ {path}:{line_no}: 命中 {label} `{lit[:20]}...`。"
                    f" 改为占位符或放 .env"
                )
        # 2b. 公网 IPv4
        for ip in IP_RE.findall(text):
            if not _ip_is_safe(ip):
                violations.append(
                    f"  ✘ {path}:{line_no}: 公网 IPv4 `{ip}`。"
                    f" 占位写法：<YOUR_HOST_IP>、example.com、1.2.3.4、192.0.2.x"
                )
        # 2c. 真实邮箱
        for addr in EMAIL_RE.findall(text):
            if not _email_is_safe(addr):
                # 排除 git author（commit message 不在 diff 里，所以这里只会扫到文件内的邮箱）
                violations.append(
                    f"  ✘ {path}:{line_no}: 真实邮箱 `{addr}`。"
                    f" 用 noreply@... / your-email@example.com / 占位符"
                )
        # 2d. 高熵随机串
        if not ENTROPY_SAFE_CONTEXT.search(text):
            for tok in HIGH_ENTROPY_BASE64.findall(text):
                # 排除明显是 hash / git sha 的（40 字符 hex 是 git sha，单独走 hex 规则）
                if not re.fullmatch(r"[a-f0-9]+", tok):
                    violations.append(
                        f"  ✘ {path}:{line_no}: 高熵 base64-urlsafe 串 `{tok[:16]}...`"
                        f"（{len(tok)} 字符），疑似 token。如确实是非密文，加注释 `# noqa: secrets`"
                    )

    return violations


def main() -> int:
    files = _staged_files()
    if not files:
        return 0

    all_violations: list[str] = []
    for path in files:
        all_violations.extend(_check_file(path))

    if not all_violations:
        return 0

    print("\n" + "=" * 70, file=sys.stderr)
    print("[pre-commit] ❌ 拦截：staged 改动中发现敏感信息：", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    for v in all_violations:
        print(v, file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(
        "处理方式：\n"
        "  • 真实凭证 → 移到 .env（已 gitignore），代码读 os.environ.get(...)\n"
        "  • 真实 IP → 替换为占位符（<ECS_HOST> / 1.2.3.4 / example.com）\n"
        "  • 真实邮箱 → noreply@... 或 your-email@example.com\n"
        "  • 误报 → 在该行末加注释 `# noqa: secrets`（仅高熵串规则尊重）\n"
        "  • 紧急绕过（不推荐）→ git commit --no-verify",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
