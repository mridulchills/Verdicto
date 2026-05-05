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
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    txt_files = sorted(input_dir.glob("*.txt"))
    logger.info(f"Found {len(txt_files)} text files to segment")

    regex_count = 0
    fallback_count = 0

    for txt_path in txt_files:
        output_path = output_dir / txt_path.with_suffix(".json").name
        if output_path.exists():
            continue

        text = txt_path.read_text(encoding="utf-8")
        segments = segment_with_regex(text)

        if segments:
            method = "regex"
            regex_count += 1
        else:
            # Fallback: simple positional split
            third = len(text) // 4
            segments = {
                "facts": text[:third],
                "issues": text[third:2*third],
                "reasoning": text[2*third:3*third],
                "outcome": text[3*third:],
            }
            method = "heuristic_fallback"
            fallback_count += 1

        output_data = {**segments, "segmentation_method": method, "source_file": txt_path.name}
        output_path.write_text(json.dumps(output_data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"Segmented: {txt_path.name} (method={method})")

    logger.info(f"Done. Regex: {regex_count}, Fallback: {fallback_count}")


if __name__ == "__main__":
    main()
