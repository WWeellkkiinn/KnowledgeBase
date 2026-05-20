"""第二轮加强：针对漏合严重的领域单独再跑 LLM，且 prompt 内嵌具体示例。
直接更新 .tag_merge_per_domain.json 并重新计算 .tag_merge_plan.json。
"""
from __future__ import annotations

import json
import os as _os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    _os.environ.setdefault(k.strip(), v.strip())

from services.llm_client import chat_completion  # noqa: E402

CLASSIFY = json.loads((ROOT / ".tag_classify.json").read_text(encoding="utf-8"))
PER_DOMAIN = json.loads((ROOT / ".tag_merge_per_domain.json").read_text(encoding="utf-8"))
TAGS = [t.strip() for t in (ROOT / ".tag_dump.txt").read_text(encoding="utf-8").splitlines() if t.strip()]


def llm_json(system: str, user: str, max_tokens: int = 4096) -> dict:
    raw = chat_completion(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
        temperature=0.1,
    )
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        raise SystemExit(f"LLM did not return JSON. raw:\n{raw[:500]}")
    return json.loads(m.group())


TARGET_DOMAINS = ["管理产业", "政策治理", "农业食品", "城市交通", "社会教育", "医疗生命"]

for d in CLASSIFY:
    name = d["name"]
    if name not in TARGET_DOMAINS:
        continue
    tags = d["tags"]
    if len(tags) < 3:
        continue
    system = (
        f"你是学术标签积极归并助手。下面是 \"{name}\" 领域的 tag 池，目前**严重碎片化**，"
        "之前的 LLM 调用过于保守几乎没合并。你的任务是把语义相同/高度近似/同根派生的"
        "tag 大胆合并起来，目标减少 30-50%。\n\n"
        "**典型合并案例**（务必学习这种力度）：\n"
        "- \"创新\" / \"创新研究\" / \"数字创新\" → 都并入 \"创新\"\n"
        "- \"创新政策\" 独立保留（政策是不同概念）\n"
        "- \"企业\" / \"企业协作\" / \"中小企业\" / \"建筑企业\" → 都并入 \"企业\"\n"
        "- \"工业\" / \"工业4.0\" / \"工业AI\" / \"制造业\" / \"能源制造\" → 并入 \"制造业\"\n"
        "- \"政策\" / \"政策分析\" / \"政策评估\" / \"政策仿真\" → 并入 \"政策分析\"\n"
        "- \"治理\" / \"算法治理\" / \"生态治理\" → 子领域独立时不合，但 \"治理\" 和 \"公共管理\" 可以合\n"
        "- \"医疗\" / \"健康\" / \"健康经济\" / \"公共健康\" / \"临床\" → 大多合并到 \"医疗健康\"\n"
        "- \"交通\" / \"公共交通\" / \"城市交通\" / \"出行\" / \"共享出行\" → 并入 \"交通\"\n"
        "- \"农业\" / \"林业\" / \"渔民\" / \"牧区\" → \"农业\" 这个 canonical 下\n"
        "- \"传染病\" / \"疫情\" / \"病毒\" / \"病毒传播\" / \"疾病传播\" → \"传染病\"\n\n"
        "**不要合的情况**：\n"
        "- 不同领域：如 \"AI治理\" 和 \"环境治理\" 不合\n"
        "- 父子粒度差大：\"金融\" 和 \"股市\" 不合\n"
        "- 政策 vs 现象：\"创新\" 和 \"创新政策\" 不合\n\n"
        "宁可多合（同义就该合），不要错合（跨领域绝不合）。要敢于减半。\n"
        "canonical 必须从给定 tag 列表里选一个最规范的（不能新造）。\n"
        "输出 JSON（不要 markdown，不要解释）：\n"
        "{\"merges\": [{\"canonical\": \"...\", \"aliases\": [...]}, ...]}\n"
        "aliases 列被合并的原 tag（不含 canonical 本身）。未合并的 tag 不出现。"
    )
    user = "本领域 tag：\n" + "\n".join(tags)
    print(f"[round2] {name} ({len(tags)} tags)...")
    try:
        obj = llm_json(system, user, max_tokens=4096)
    except Exception as e:
        print(f"[round2] {name} failed: {e}")
        continue
    merges = obj.get("merges", [])
    dom_set = set(tags)
    clean = []
    for m in merges:
        canon = m.get("canonical", "").strip()
        aliases = [a.strip() for a in m.get("aliases", []) if a.strip()]
        aliases = [a for a in aliases if a in dom_set and a != canon]
        if canon in dom_set and aliases:
            clean.append({"canonical": canon, "aliases": aliases})
    PER_DOMAIN[name] = {"merges": clean}
    print(f"[round2] {name}: {len(clean)} merge groups, {sum(len(m['aliases']) for m in clean)} aliases")

(ROOT / ".tag_merge_per_domain.json").write_text(json.dumps(PER_DOMAIN, ensure_ascii=False, indent=2), encoding="utf-8")

# 重新整合
all_merges = []
alias_to_canon = {}
conflicts = []
for domain, info in PER_DOMAIN.items():
    for m in info["merges"]:
        canon = m["canonical"]
        for alias in m["aliases"]:
            if alias in alias_to_canon and alias_to_canon[alias] != canon:
                conflicts.append({"alias": alias, "canonicals": [alias_to_canon[alias], canon]})
            alias_to_canon[alias] = canon
        all_merges.append({"domain": domain, "canonical": canon, "aliases": m["aliases"]})

real_final = len(TAGS) - len(alias_to_canon)
out = {
    "input_tags": len(TAGS),
    "final_pool_size": real_final,
    "total_merge_groups": len(all_merges),
    "total_aliases_merged": len(alias_to_canon),
    "conflicts": conflicts,
    "merges_by_domain": PER_DOMAIN,
    "all_merges": all_merges,
    "mapping_flat": alias_to_canon,
}
(ROOT / ".tag_merge_plan.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print()
print(f"final: 453 → {real_final} (合并 {len(alias_to_canon)} 个 alias，冲突 {len(conflicts)})")
