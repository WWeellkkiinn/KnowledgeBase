"""一次性脚本：LLM 归并现有 tag，输出映射表供人工审核。

只生成 .tag_merge_plan.json，不修改数据库。
人工确认后再跑 apply_tags_merge.py（后续单独写）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 加载 .env
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    import os as _os
    _os.environ.setdefault(k.strip(), v.strip())

from services.llm_client import chat_completion  # noqa: E402

TAGS_FILE = ROOT / ".tag_dump.txt"
OUT_FILE = ROOT / ".tag_merge_plan.json"

if not TAGS_FILE.exists():
    raise SystemExit(f"missing {TAGS_FILE}")

tags = [t.strip() for t in TAGS_FILE.read_text(encoding="utf-8").splitlines() if t.strip()]
print(f"loaded {len(tags)} unique tags")

system = (
    "你是学术标签归并助手。下面给你一批论文 tag（中文为主），由不同次 LLM 调用生成，"
    "存在大量同义、拼写变体、粒度不一、过于细碎的问题。**积极合并**，目标是把同一研究方向"
    "的 tag 收敛到统一的 canonical 名称下。当前池子过于碎片化，必须大幅压缩。\n\n"
    "归并规则（积极模式）：\n"
    "1. 同义/近义都合并：例如 \"ABM\" / \"agent-based\" / \"多智能体\" / \"主体建模\" / \"智能体仿真\" → \"智能体建模\"\n"
    "2. 子领域并入上位概念（除非该子领域足够独立）：例如 \"股价预测\" / \"股市预测\" / \"股票预测\" → \"股市\"\n"
    "3. 拼写、修饰词差异、词序差异统统合并：例如 \"金融科技\" / \"数字金融\" / \"金融数字化\" → \"数字金融\"\n"
    "4. 同概念不同侧面：例如 \"行为经济\" / \"行为金融\" 都属于 \"行为经济\"，可合并\n"
    "5. 近义形容词差异合并：例如 \"绿色经济\" / \"低碳经济\" / \"可持续发展\" → \"可持续发展\"\n"
    "6. 但不要跨学科强合：\"金融\" 不合并到 \"经济\"；\"环境政策\" 不合并到 \"经济政策\"\n"
    "7. canonical 名称尽量 2-4 个中文字，最规范、最常用的那个\n"
    "8. 目标：把 450 个 tag 压到 100-150 个左右，要敢于合\n\n"
    "输出 JSON（不要 markdown 围栏，不要解释）：\n"
    "{\"merges\": [{\"canonical\": \"...\", \"aliases\": [\"...\", \"...\"]}, ...]}\n\n"
    "aliases 列出所有应合并到该 canonical 的原 tag（不含 canonical 本身）。未合并的 tag 不要出现。"
)

user = "tag 列表（每行一个）：\n" + "\n".join(tags)

print("calling LLM...")
raw = chat_completion(
    [{"role": "system", "content": system}, {"role": "user", "content": user}],
    max_tokens=8192,
    temperature=0.2,
)

import re
m = re.search(r"\{[\s\S]*\}", raw)
if not m:
    raise SystemExit(f"LLM did not return JSON. raw:\n{raw[:500]}")

data = json.loads(m.group())
merges = data.get("merges", [])

# 构建反向映射：alias -> canonical
mapping = {}
for entry in merges:
    canon = entry["canonical"].strip()
    for alias in entry.get("aliases", []):
        alias = alias.strip()
        if alias and alias != canon:
            mapping[alias] = canon

# 校验：所有 alias 是否都在原 tag 列表里
tags_set = set(tags)
invalid_aliases = [a for a in mapping if a not in tags_set]
hallucinated_canonicals = [m["canonical"] for m in merges if m["canonical"] not in tags_set and m["canonical"] not in mapping.values()]

out = {
    "total_input_tags": len(tags),
    "merge_groups_count": len(merges),
    "total_aliases_to_merge": len(mapping),
    "tags_left_unmerged": len(tags) - len(mapping) - sum(1 for m in merges if m["canonical"] in tags_set),
    "invalid_aliases_in_llm_output": invalid_aliases,
    "canonicals_not_in_original_tags": hallucinated_canonicals,
    "merges": merges,
    "mapping_flat": mapping,
}

OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"wrote {OUT_FILE}")
print(f"summary: {len(merges)} merge groups, {len(mapping)} aliases merged, "
      f"{out['tags_left_unmerged']} tags unmerged")
if invalid_aliases:
    print(f"WARN: {len(invalid_aliases)} alias not in original tags (LLM 幻觉)")
if hallucinated_canonicals:
    print(f"WARN: {len(hallucinated_canonicals)} canonical not in original tags")
