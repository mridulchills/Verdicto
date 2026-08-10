"""
Shared reporting helper — every measurement script writes through this.

Design rules:
  * One JSON file per report, under <data-dir>/reports/, machine-readable.
  * One Markdown file alongside it, paste-ready for the paper.
  * Reports are additive: re-running a script overwrites only its own report.
  * Every report records the timestamp, the git commit, and the arguments used,
    so a number in the paper can always be traced back to the run that produced it.

Usage:
    from scripts.lib.report import Report
    rep = Report("corpus_stats", data_dir)
    rep.section("Corpus attrition")
    rep.stat("pdfs_downloaded", 41234, "PDFs in data/raw/pdfs")
    rep.table("Per-year counts", ["year", "n"], [[2024, 1201], [2023, 1150]])
    rep.note("Steps 4/5/6 must agree; a mismatch breaks the case_id -> FAISS mapping.")
    rep.save()
"""
from __future__ import annotations

import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _hardware() -> dict[str, Any]:
    """Best-effort hardware capture. Q67 requires this alongside any latency number."""
    info: dict[str, Any] = {
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "python": sys.version.split()[0],
    }
    try:
        import os
        info["cpu_count"] = os.cpu_count()
    except Exception:
        pass
    try:
        import psutil  # optional
        info["ram_gb"] = round(psutil.virtual_memory().total / 1024**3, 1)
    except Exception:
        info["ram_gb"] = None
    try:
        import torch  # optional
        info["cuda_available"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            info["gpu_name"] = torch.cuda.get_device_name(0)
            info["gpu_vram_gb"] = round(
                torch.cuda.get_device_properties(0).total_memory / 1024**3, 1
            )
    except Exception:
        info["cuda_available"] = None
    return info


class Report:
    """Collects stats/tables/notes and writes them as JSON + Markdown."""

    def __init__(self, name: str, data_dir: Path | str, args: Any = None) -> None:
        self.name = name
        self.data_dir = Path(data_dir)
        self.out_dir = self.data_dir / "reports"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.meta: dict[str, Any] = {
            "report": name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "git_commit": _git_commit(),
            "hardware": _hardware(),
            "args": vars(args) if args is not None and hasattr(args, "__dict__") else args,
        }
        self.blocks: list[dict[str, Any]] = []
        self.stats: dict[str, Any] = {}

    # ── builders ──────────────────────────────────────────────────────────
    def section(self, title: str) -> "Report":
        self.blocks.append({"type": "section", "title": title})
        return self

    def stat(self, key: str, value: Any, label: str | None = None) -> "Report":
        self.stats[key] = value
        self.blocks.append({"type": "stat", "key": key, "value": value, "label": label or key})
        return self

    def table(self, title: str, columns: list[str], rows: list[list[Any]]) -> "Report":
        self.blocks.append({"type": "table", "title": title, "columns": columns, "rows": rows})
        return self

    def note(self, text: str) -> "Report":
        self.blocks.append({"type": "note", "text": text})
        return self

    def raw(self, key: str, value: Any) -> "Report":
        """Attach bulk data to the JSON only (not rendered into Markdown)."""
        self.meta.setdefault("raw", {})[key] = value
        return self

    # ── output ────────────────────────────────────────────────────────────
    def _markdown(self) -> str:
        lines = [
            f"# Report — {self.name}",
            "",
            f"*Generated {self.meta['generated_at']} · commit `{self.meta['git_commit']}`*",
            "",
        ]
        hw = self.meta["hardware"]
        lines += [
            "**Hardware** (record this next to any latency figure — Q67): "
            f"{hw.get('platform')} · {hw.get('cpu_count')} cores · "
            f"{hw.get('ram_gb')} GB RAM · GPU: {hw.get('gpu_name', 'none detected')}",
            "",
        ]
        for b in self.blocks:
            t = b["type"]
            if t == "section":
                lines += ["", f"## {b['title']}", ""]
            elif t == "stat":
                lines.append(f"- **{b['label']}**: `{b['value']}`")
            elif t == "table":
                lines += ["", f"**{b['title']}**", ""]
                lines.append("| " + " | ".join(str(c) for c in b["columns"]) + " |")
                lines.append("|" + "|".join("---" for _ in b["columns"]) + "|")
                for row in b["rows"]:
                    lines.append("| " + " | ".join(str(c) for c in row) + " |")
                lines.append("")
            elif t == "note":
                lines += ["", f"> {b['text']}", ""]
        return "\n".join(lines) + "\n"

    def save(self, quiet: bool = False) -> tuple[Path, Path]:
        json_path = self.out_dir / f"{self.name}.json"
        md_path = self.out_dir / f"{self.name}.md"
        payload = {**self.meta, "stats": self.stats, "blocks": self.blocks}
        json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        md_path.write_text(self._markdown(), encoding="utf-8")
        if not quiet:
            print(f"\n[report] {json_path}")
            print(f"[report] {md_path}")
        return json_path, md_path


class EventLog:
    """
    Append-only JSONL log for per-item outcomes (one line per document).
    Used by the ingestion scripts so per-file failures are recoverable after the fact
    instead of scrolling past in the console.
    """

    def __init__(self, name: str, data_dir: Path | str, reset: bool = True) -> None:
        self.path = Path(data_dir) / "reports" / f"{name}.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if reset and self.path.exists():
            self.path.unlink()
        self._fh = open(self.path, "a", encoding="utf-8")

    def write(self, **fields: Any) -> None:
        self._fh.write(json.dumps(fields, default=str) + "\n")
        self._fh.flush()

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass

    def __enter__(self) -> "EventLog":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
