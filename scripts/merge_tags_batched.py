"""分批 tag 合并：先按研究领域分类，再每类内合并，最后冲突检测。

中间产物：
  .tag_classify.json - 大类划分
  .tag_merge_per_domain.json - 每大类的合并提案
最终输出：
  .tag_merge_plan.json - 整合后的最终方案，供人工 review
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

TAGS_FILE = ROOT / ".tag_dump.txt"
CLASSIFY_FILE = ROOT / ".tag_classify.json"
PER_DOMAIN_FILE = ROOT / ".tag_merge_per_domain.json"
OUT_FILE = ROOT / ".tag_merge_plan.json"


def llm_json(system: str, user: str, max_tokens: int = 4096) -> dict | list:
    raw = chat_completion(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=max_tokens,
        temperature=0.1,
    )
    m = re.search(r"[\[\{][\s\S]*[\]\}]", raw)
    if not m:
        raise SystemExit(f"LLM did not return JSON. raw:\n{raw[:500]}")
    return json.loads(m.group())


# ---------- 阶段 1：分类 ----------
tags = [t.strip() for t in TAGS_FILE.read_text(encoding="utf-8").splitlines() if t.strip()]
print(f"[1] loaded {len(tags)} unique tags")

if CLASSIFY_FILE.exists():
    classify = json.loads(CLASSIFY_FILE.read_text(encoding="utf-8"))
    print(f"[1] reuse cached classify: {len(classify)} domains")
else:
    system = (
        "你是学术标签分类助手。把下面给你的 tag 全部分配到 10-15 个学术研究领域大类下，"
        "每个 tag 必须且只能进入一个大类。大类划分要：\n"
        "- 覆盖经济学/金融/管理/AI 与计算/方法论/社会/环境/医疗 等主要研究域\n"
        "- 大类名称用 2-6 个中文字\n"
        "- 实在不属于任何大类的放进 \"其他\" 大类\n\n"
        "输出 JSON（不要 markdown 围栏）：\n"
        "{\"domains\": [{\"name\": \"领域名\", \"tags\": [\"tag1\", \"tag2\", ...]}, ...]}\n"
        "tags 数组必须严格使用我提供的原文，不许新造、不许改字。"
    )
    user = "tag 列表：\n" + "\n".join(tags)
    print("[1] calling LLM to classify into domains...")
    obj = llm_json(system, user, max_tokens=8192)
    classify = obj.get("domains", [])
    # 校验
    seen = set()
    for d in classify:
        for t in d["tags"]:
            seen.add(t)
    missing = set(tags) - seen
    extra = seen - set(tags)
    if missing:
        # 漏掉的扔到"其他"
        other = next((d for d in classify if d["name"] == "其他"), None)
        if other is None:
            other = {"name": "其他", "tags": []}
            classify.append(other)
        other["tags"].extend(sorted(missing))
        print(f"[1] WARN: {len(missing)} tags missing → 补进\"其他\"")
    if extra:
        # 删掉幻觉
        for d in classify:
            d["tags"] = [t for t in d["tags"] if t in set(tags)]
        print(f"[1] WARN: {len(extra)} hallucinated tags removed: {sorted(extra)[:10]}")
    CLASSIFY_FILE.write_text(json.dumps(classify, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[1] classify → {CLASSIFY_FILE.name}: {len(classify)} domains")

print()
print("领域 → tag 数：")
for d in classify:
    print(f"  {d['name']}: {len(d['tags'])}")
print()

# ---------- 阶段 2：每大类内合并 ----------
if PER_DOMAIN_FILE.exists():
    per_domain = json.loads(PER_DOMAIN_FILE.read_text(encoding="utf-8"))
    print(f"[2] reuse cached per_domain: {len(per_domain)} domains")
else:
    per_domain = {}
    for d in classify:
        domain = d["name"]
        domain_tags = d["tags"]
        if len(domain_tags) < 3:
            per_domain[domain] = {"merges": []}
            print(f"[2] {domain}: only {len(domain_tags)} tags, skip merging")
            continue
        system = (
            f"你是学术标签归并助手。下面这些 tag 都属于 \"{domain}\" 领域，"
            "目前过于碎片化，请**积极合并**语义相同/高度近似/同根派生的 tag。\n\n"
            "✅ 必须合并的情况：\n"
            "1. 同义/近义：如 \"股市\"/\"股票\" 都指 \"股市\"\n"
            "2. 拼写变体：如 \"ABM\"/\"agent-based\"/\"多智能体\"/\"主体建模\" → \"智能体建模\"\n"
            "3. 同根派生 + 高度重合：如 \"股价预测\"/\"股票预测\" → \"股市预测\"；"
            "如 \"风险评估\"/\"风险预测\" → \"风险评估\"\n"
            "4. 修饰词差异：如 \"金融科技\"/\"数字金融\" → \"数字金融\"；如 \"绿色经济\"/\"低碳经济\" → \"绿色经济\"\n"
            "5. 同义动词/名词形式：如 \"创新\"/\"创新研究\" → \"创新\"\n\n"
            "❌ 不要合并的情况：\n"
            "1. 父子概念差异显著：\"金融市场\" 和 \"股市\" 粒度不同，不合（股市只是金融市场的一部分）\n"
            "2. 同领域但研究对象不同：\"信用风险\" 和 \"清算风险\" 不合（针对不同业务环节）\n"
            "3. 同根但概念独立：\"创新\" 和 \"创新政策\" 不合（一个是现象，一个是政策）\n\n"
            "原则：宁可多合（同义的就要合），但绝对不能错合（不同概念绝不合）。"
            "目标是把领域 tag 数减半。\n\n"
            "canonical 必须从下方列表里选一个最规范的（不能新造），尽量 2-4 中文字。\n"
            "输出 JSON（不要 markdown 围栏，不要解释）：\n"
            "{\"merges\": [{\"canonical\": \"...\", \"aliases\": [\"...\", \"...\"]}, ...]}\n"
            "aliases 列被合并到该 canonical 的原 tag（不含 canonical 本身）。未合并的 tag 不要出现。"
        )
        user = "本领域 tag：\n" + "\n".join(domain_tags)
        print(f"[2] merging {domain} ({len(domain_tags)} tags)...")
        try:
            obj = llm_json(system, user, max_tokens=4096)
        except Exception as e:
            print(f"[2] {domain} failed: {e}")
            per_domain[domain] = {"merges": []}
            continue
        merges = obj.get("merges", [])
        # 校验：alias 必须在 domain_tags 里
        dom_set = set(domain_tags)
        clean_merges = []
        for m in merges:
            canon = m.get("canonical", "").strip()
            aliases = [a.strip() for a in m.get("aliases", []) if a.strip()]
            aliases = [a for a in aliases if a in dom_set and a != canon]
            if canon and aliases:
                clean_merges.append({"canonical": canon, "aliases": aliases})
        per_domain[domain] = {"merges": clean_merges}
        print(f"[2] {domain}: {len(clean_merges)} merge groups")
    PER_DOMAIN_FILE.write_text(json.dumps(per_domain, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[2] saved per_domain → {PER_DOMAIN_FILE.name}")

# ---------- 阶段 3：冲突检测 + 整合 ----------
print()
all_merges = []
alias_to_canon = {}  # 用于检测冲突
conflicts = []

for domain, info in per_domain.items():
    for m in info["merges"]:
        canon = m["canonical"]
        for alias in m["aliases"]:
            if alias in alias_to_canon and alias_to_canon[alias] != canon:
                conflicts.append({
                    "alias": alias,
                    "canonicals": [alias_to_canon[alias], canon],
                })
            alias_to_canon[alias] = canon
        all_merges.append({"domain": domain, "canonical": canon, "aliases": m["aliases"]})

print(f"[3] total merge groups: {len(all_merges)}")
print(f"[3] aliases merged: {len(alias_to_canon)}")
print(f"[3] conflicts (alias appears in multiple canonicals): {len(conflicts)}")

final_canonicals = set(m["canonical"] for m in all_merges)
final_tag_count = len(set(tags) - set(alias_to_canon.keys())) + len(final_canonicals)
print(f"[3] estimated final pool size: {final_tag_count}")

out = {
    "input_tags": len(tags),
    "final_pool_size_estimate": final_tag_count,
    "total_merge_groups": len(all_merges),
    "total_aliases_merged": len(alias_to_canon),
    "conflicts": conflicts,
    "merges_by_domain": per_domain,
    "all_merges": all_merges,
    "mapping_flat": alias_to_canon,
}
OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"[3] wrote {OUT_FILE.name}")
