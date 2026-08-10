"""
Segment extracted text into: facts, issues, reasoning, outcome.
Uses regex heuristics first, falls back to Gemini-assisted segmentation.
Idempotent — skips already segmented files.

Usage:
    python -m scripts.ingest.segment_text --input-dir ./data/processed --output-dir ./data/processed/segmented
"""
from __future__ import annotations
import argparse
import json
import logging
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Regex patterns for common section headings in SC judgments
SECTION_PATTERNS = {
    "facts": [
        r"(?i)\b(?:FACTS|FACTUAL\s+(?:MATRIX|BACKGROUND)|BACKGROUND|BRIEF\s+FACTS)\b",
        r"(?i)\bFACTS\s+(?:OF|IN)\s+(?:THE|THIS)\s+CASE\b",
    ],
    "issues": [
        r"(?i)\b(?:ISSUES?|QUESTIONS?\s+(?:OF|FOR)\s+(?:LAW|CONSIDERATION))\b",
        r"(?i)\bPOINTS?\s+FOR\s+(?:DETERMINATION|CONSIDERATION)\b",
    ],
    "reasoning": [
        r"(?i)\b(?:REASONING|ANALYSIS|DISCUSSION|CONSIDERATION|HELD|JUDGMENT)\b",
        r"(?i)\bOUR\s+(?:VIEW|ANALYSIS|CONSIDERATION)\b",
    ],
    "outcome": [
        r"(?i)\b(?:ORDER|CONCLUSION|RESULT|DISPOSITION|OPERATIVE\s+(?:PART|ORDER))\b",
        r"(?i)\b(?:APPEAL\s+(?:IS|ALLOWED|DISMISSED))\b",
    ],
}


def segment_with_regex(text: str) -> dict[str, str] | None:
    """Try to segment text using regex-based heuristics."""
    lines = text.split("\n")
    sections: dict[str, list[int]] = {}

    for i, line in enumerate(lines):
        stripped = line.strip()
        if len(stripped) < 3 or len(stripped) > 200:
            continue
        for section_name, patterns in SECTION_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, stripped):
                    if section_name not in sections:
                        sections[section_name] = []
                    sections[section_name].append(i)
                    break

    if len(sections) < 2:
        return None  # Not enough sections found — fall back

    # Extract text between section markers
    all_markers = []
    for name, positions in sections.items():
        for pos in positions:
            all_markers.append((pos, name))
    all_markers.sort()

    result: dict[str, str] = {"facts": "", "issues": "", "reasoning": "", "outcome": ""}
    for idx, (start_line, name) in enumerate(all_markers):
        end_line = all_markers[idx + 1][0] if idx + 1 < len(all_markers) else len(lines)
        section_text = "\n".join(lines[start_line:end_line]).strip()
        if result[name]:
            result[name] += "\n\n" + section_text
        else:
            result[name] = section_text

    # Fill in any missing sections with heuristic splits
    if not result["facts"] and not result["reasoning"]:
        third = len(text) // 3
        result["facts"] = text[:third]
        result["reasoning"] = text[third:2*third]
        result["outcome"] = text[2*third:]

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Segment judgment texts")
    parser.add_argument("--input-dir", type=str, default="./data/processed")
    parser.add_argument("--output-dir", type=str, default="./data/processed/segmented")
    parser.add_argument("--data-dir", type=str, default="../data",
                        help="Root data directory; reports go to <data-dir>/reports/")
    parser.add_argument("--rescan", action="store_true",
                        help="recount already-segmented files without re-segmenting "
                             "(use this to produce the Q5 report on an existing corpus)")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        from scripts.lib.report import EventLog, Report
        report_enabled = True
    except Exception:
        report_enabled = False
        logger.warning("scripts.lib.report unavailable — running without file reporting")

    from collections import Counter
    methods: Counter[str] = Counter()
    empty_sections: Counter[str] = Counter()
    section_chars: dict[str, list[int]] = {k: [] for k in ("facts", "issues", "reasoning", "outcome")}

    def _tally(data: dict) -> None:
        methods[data.get("segmentation_method", "missing")] += 1
        for k in section_chars:
            v = (data.get(k) or "").strip()
            section_chars[k].append(len(v))
            if not v:
                empty_sections[k] += 1

    # --rescan: read what already exists and report on it, segmenting nothing.
    if args.rescan:
        existing = sorted(output_dir.glob("*.json"))
        logger.info(f"Rescanning {len(existing)} already-segmented files")
        for p in existing:
            try:
                _tally(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                methods["unreadable"] += 1
    else:
        txt_files = sorted(input_dir.glob("*.txt"))
        logger.info(f"Found {len(txt_files)} text files to segment")

        log = EventLog("segment_text_per_doc", args.data_dir) if report_enabled else None
        for txt_path in txt_files:
            output_path = output_dir / txt_path.with_suffix(".json").name
            if output_path.exists():
                try:
                    _tally(json.loads(output_path.read_text(encoding="utf-8")))
                except Exception:
                    methods["unreadable"] += 1
                continue

            text = txt_path.read_text(encoding="utf-8")
            segments = segment_with_regex(text)

            if segments:
                method = "regex"
            else:
                # Fallback: blind positional split into four equal quarters.
                # A document that lands here presents its arbitrary second quarter
                # to the Debate agent as "the legal issues of the case" (Q6).
                third = len(text) // 4
                segments = {
                    "facts": text[:third],
                    "issues": text[third:2*third],
                    "reasoning": text[2*third:3*third],
                    "outcome": text[3*third:],
                }
                method = "heuristic_fallback"

            output_data = {**segments, "segmentation_method": method, "source_file": txt_path.name}
            output_path.write_text(json.dumps(output_data, indent=2, ensure_ascii=False), encoding="utf-8")
            _tally(output_data)
            if log:
                log.write(case_id=txt_path.stem, method=method, source_chars=len(text))
            logger.info(f"Segmented: {txt_path.name} (method={method})")
        if log:
            log.close()

    total = sum(methods.values())
    regex_count = methods.get("regex", 0)
    fallback_count = methods.get("heuristic_fallback", 0)
    logger.info(f"Done. Regex: {regex_count}, Fallback: {fallback_count}, Total: {total}")

    if report_enabled and total:
        import statistics as _st
        rep = Report("segment_text", args.data_dir, args)
        rep.section("Segmentation quality (Q5) — publishable, no annotation required")
        rep.stat("documents", total)
        rep.stat("regex_segmented", regex_count)
        rep.stat("positional_fallback", fallback_count)
        rep.stat("fallback_rate_pct", round(100 * fallback_count / total, 2),
                 "THE number: share of the corpus cut into equal quarters, not segmented")
        rep.table("Segmentation method", ["method", "documents", "share"],
                  [[k, v, f"{100*v/total:.1f}%"] for k, v in methods.most_common()])
        rep.table("Empty sections",
                  ["section", "documents empty", "share", "median chars"],
                  [[k, empty_sections.get(k, 0), f"{100*empty_sections.get(k,0)/total:.1f}%",
                    round(_st.median(section_chars[k]), 0) if section_chars[k] else 0]
                   for k in section_chars])
        rep.note("The fallback rate is the honest ceiling on structural quality, and it "
                 "caps three things at once: the embedding input, the lexical index "
                 "(title + facts + issues only), and the debate prompts.")
        rep.note("For a true accuracy figure, hand-check 50 documents stratified across "
                 "both methods, scoring each section correct / boundary-off / wrong-content "
                 "/ absent. Two people scoring the same 20 gives an agreement figure.")
        rep.save()


if __name__ == "__main__":
    main()
