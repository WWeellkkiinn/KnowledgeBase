"""extract_refs.py — Extract structured references from a Markdown file.

Supports both numbered ([1] Author...) and APA (Author, Year. Title...) styles.

Usage:
  python scripts/extract_refs.py <md_path>                  # whole file
  python scripts/extract_refs.py <md_path> --section <id>   # one section
Output (stdout): JSON array of reference objects
"""
import argparse
import json
import re
import sys
from pathlib import Path

# ── Numbered style: [1] ..., [2] ... ────────────────────────────────────────
_BRACKET_CITE_RE = re.compile(r"\[(\d[\d,\s\-]*)\]")
_NUMBERED_ENTRY_RE = re.compile(r"^\[(\d+)\]\s*(.*)")

# ── APA style: (Author, Year) or (Author et al., Year) ──────────────────────
_APA_CITE_RE = re.compile(
    r"\(([A-ZÁÉÍÓÚÀÂÄÇÈÊËÎÏÔÙÛÜ][A-Za-záéíóúàâäçèêëîïôùûü\-']+)"
    r"(?:\s+et\s+al\.)?(?:\s+[&and]+\s+[A-Z][a-z]+)*"
    r",\s+(\d{4}[a-z]?)\)"
)
_APA_ENTRY_RE = re.compile(
    r"^([A-ZÁÉÍÓÚ][A-Za-záéíóúàâäçèêëîïôùûüÁÉÍÓÚÀÂÄÇÈÊËÎÏÔÙÛÜ\-',\.&\s]+?)"
    r"\s*\((\d{4}[a-z]?)\)\.\s*(.*)"
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("md_path")
    parser.add_argument("--section", type=int, default=None)
    args = parser.parse_args()

    md_path = Path(args.md_path)
    if not md_path.exists():
        print(json.dumps({"error": f"File not found: {md_path}"}))
        sys.exit(1)

    if args.section is not None:
        text = _read_section(md_path, args.section)
        if text == "":
            print(json.dumps({"error": f"section_id {args.section} out of range"}))
            sys.exit(1)
    else:
        text = md_path.read_text(encoding="utf-8")

    all_lines = md_path.read_text(encoding="utf-8").splitlines()
    ref_lines = _get_ref_section_lines(all_lines)
    style = _detect_style(ref_lines)

    if style == "numbered":
        ref_map = _build_numbered_map(ref_lines)
        cited = _collect_numbered_indices(text)
        results = []
        for idx in sorted(cited):
            raw = ref_map.get(idx, "")
            if raw:
                parsed = _parse_ref_line(raw)
                parsed.update({"index": idx, "raw": raw})
                results.append(parsed)
    else:
        ref_entries = _build_apa_entries(ref_lines)
        cited_keys = _collect_apa_keys(text)
        results = []
        for i, entry in enumerate(ref_entries):
            key = (entry["_lastname"], entry["year"])
            if args.section is None or key in cited_keys:
                entry.pop("_lastname", None)
                entry["index"] = i + 1
                results.append(entry)

    print(json.dumps(results, ensure_ascii=False, indent=2))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _read_section(md_path: Path, section_id: int) -> str:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    sections = [i for i, l in enumerate(lines) if re.match(r"^#{1,3}\s+", l)]
    if section_id < 0 or section_id >= len(sections):
        return ""
    start = sections[section_id]
    end = sections[section_id + 1] if section_id + 1 < len(sections) else len(lines)
    return "\n".join(lines[start:end])


def _get_ref_section_lines(lines: list[str]) -> list[str]:
    ref_start = None
    for i, line in enumerate(lines):
        if re.match(r"^#{1,3}\s*(references|bibliography|参考文献)", line, re.IGNORECASE):
            ref_start = i + 1
            break
    if ref_start is None:
        return []
    result = []
    for line in lines[ref_start:]:
        if re.match(r"^#{1,3}\s+", line):
            break
        result.append(line)
    return result


def _detect_style(ref_lines: list[str]) -> str:
    for line in ref_lines[:15]:
        if _NUMBERED_ENTRY_RE.match(line.strip()):
            return "numbered"
        if _APA_ENTRY_RE.match(line.strip()):
            return "apa"
    return "numbered"


# ── Numbered style ────────────────────────────────────────────────────────────

def _build_numbered_map(ref_lines: list[str]) -> dict[int, str]:
    ref_map: dict[int, str] = {}
    current_idx = None
    current_lines: list[str] = []
    for line in ref_lines:
        m = _NUMBERED_ENTRY_RE.match(line)
        if m:
            if current_idx is not None:
                ref_map[current_idx] = " ".join(current_lines).strip()
            current_idx = int(m.group(1))
            current_lines = [m.group(2)]
        elif current_idx is not None and line.strip():
            current_lines.append(line.strip())
    if current_idx is not None:
        ref_map[current_idx] = " ".join(current_lines).strip()
    return ref_map


def _collect_numbered_indices(text: str) -> set[int]:
    indices = set()
    for m in _BRACKET_CITE_RE.finditer(text):
        for part in re.split(r",", m.group(1)):
            part = part.strip()
            if "-" in part:
                try:
                    a, b = part.split("-", 1)
                    indices.update(range(int(a.strip()), int(b.strip()) + 1))
                except ValueError:
                    pass
            else:
                try:
                    indices.add(int(part))
                except ValueError:
                    pass
    return indices


# ── APA style ─────────────────────────────────────────────────────────────────

def _build_apa_entries(ref_lines: list[str]) -> list[dict]:
    entries = []
    current_raw: list[str] = []

    def flush():
        if current_raw:
            raw = " ".join(current_raw).strip()
            e = _parse_apa_entry(raw)
            if e:
                entries.append(e)

    for line in ref_lines:
        if not line.strip():
            continue
        if _APA_ENTRY_RE.match(line.strip()):
            flush()
            current_raw = [line.strip()]
        elif current_raw:
            current_raw.append(line.strip())

    flush()
    return entries


def _parse_apa_entry(raw: str) -> dict | None:
    m = _APA_ENTRY_RE.match(raw)
    if not m:
        return None
    authors_raw = m.group(1).strip().rstrip(".,")
    year = m.group(2)
    rest = m.group(3)

    # lastname of first author (for citation key matching)
    lastname = authors_raw.split(",")[0].strip()

    # title: up to first period after a capital-letter word sequence
    title_m = re.match(r"^(.+?)\.\s+", rest)
    title = title_m.group(1).strip() if title_m else rest[:120]

    # DOI
    doi_m = re.search(r"https?://doi\.org/(\S+)", raw)
    doi = doi_m.group(1).rstrip(".,) ") if doi_m else ""

    return {
        "_lastname": lastname.lower(),
        "title": title,
        "authors": authors_raw,
        "year": year,
        "doi": doi,
        "pdf_url": "",
        "raw": raw,
    }


def _collect_apa_keys(text: str) -> set[tuple[str, str]]:
    keys = set()
    for m in _APA_CITE_RE.finditer(text):
        lastname = m.group(1).lower()
        year = m.group(2)
        keys.add((lastname, year))
    return keys


# ── Shared ref line parser (numbered style) ───────────────────────────────────

def _parse_ref_line(raw: str) -> dict:
    year_m = re.search(r"\b(19|20)\d{2}\b", raw)
    year = year_m.group(0) if year_m else ""
    doi_m = re.search(r"10\.\d{4,}/\S+", raw)
    doi = doi_m.group(0).rstrip(".,)") if doi_m else ""
    title_m = re.search(r'[""](.*?)["""]', raw) or re.search(r"\*(.+?)\*", raw)
    title = title_m.group(1) if title_m else _guess_title(raw)
    authors = raw[:year_m.start()].strip().rstrip(".,") if year_m else ""
    return {"title": title, "authors": authors, "year": year, "doi": doi, "pdf_url": ""}


def _guess_title(raw: str) -> str:
    parts = [p.strip() for p in raw.split(".") if len(p.strip()) > 20]
    return parts[0] if parts else raw[:100]


if __name__ == "__main__":
    main()
