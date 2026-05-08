"""
Fix case titles in the database by extracting proper case names from segmented JSON files.
Looks for "PARTY v. PARTY" patterns in the reasoning/outcome/facts text.

Usage (from Backend/ directory, inside Docker):
    python -m scripts.ingest.fix_titles --segmented-dir /app/data/processed/segmented
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Patterns to extract case titles
# Matches: "PARTY NAME v. OTHER PARTY" or "PARTY NAME vs. OTHER PARTY"
_TITLE_PATTERNS = [
    # Standard Supreme Court format: ALL CAPS v. ALL CAPS
    re.compile(r'([A-Z][A-Z\s&\.\(\),\-\']+?)\s+[Vv][Ss]?\.\s+([A-Z][A-Z\s&\.\(\),\-\']+?)(?:\n|$)', re.MULTILINE),
    # Mixed case with v. separator
    re.compile(r'([A-Z][a-zA-Z\s&\.\(\),\-\']{5,}?)\s+[Vv][Ss]?\.\s+([A-Z][a-zA-Z\s&\.\(\),\-\']{5,}?)(?:\n|$)', re.MULTILINE),
]


def _extract_title(data: dict) -> str | None:
    """Extract a proper case title from segmented JSON data."""
    # Search in order: reasoning (has headnotes), outcome, facts
    for field in ["reasoning", "outcome", "facts", "issues"]:
        text_block = data.get(field, "") or ""
        if not text_block:
            continue
        for pattern in _TITLE_PATTERNS:
            matches = pattern.findall(text_block)
            for petitioner, respondent in matches:
                petitioner = petitioner.strip().rstrip(".,")
                respondent = respondent.strip().rstrip(".,")
                # Filter out noise — must be at least 3 chars each and not just numbers
                if len(petitioner) >= 3 and len(respondent) >= 3:
                    title = f"{petitioner} v. {respondent}"
                    # Cap at 200 chars
                    return title[:200]
    return None


async def fix_titles(segmented_dir: Path, database_url: str) -> None:
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    json_files = sorted(segmented_dir.glob("*.json"))
    logger.info(f"Processing {len(json_files)} files")

    updated = 0
    skipped = 0
    no_title = 0

    async with async_session() as session:
        for json_file in json_files:
            case_id = json_file.stem
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                title = _extract_title(data)

                if not title:
                    no_title += 1
                    continue

                # Update only if the current title looks like garbage (starts with lowercase, number, or is very short)
                result = await session.execute(
                    text("SELECT title FROM cases WHERE case_id = :cid"),
                    {"cid": case_id},
                )
                row = result.fetchone()
                if not row:
                    skipped += 1
                    continue

                current_title = row[0] or ""
                # Replace if current title doesn't look like a proper case name
                needs_update = (
                    not re.search(r'\bv\.\s', current_title, re.IGNORECASE)
                    or len(current_title) < 10
                    or current_title[0].islower()
                    or current_title[0].isdigit()
                )

                if needs_update:
                    await session.execute(
                        text("UPDATE cases SET title = :title WHERE case_id = :cid"),
                        {"title": title, "cid": case_id},
                    )
                    updated += 1
                else:
                    skipped += 1

            except Exception as e:
                logger.error(f"Error processing {json_file.name}: {e}")
                continue

        await session.commit()

    logger.info(f"Done. Updated: {updated}, Skipped (already good): {skipped}, No title found: {no_title}")
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix case titles in the database")
    parser.add_argument("--segmented-dir", type=str, default="/app/data/processed/segmented")
    parser.add_argument(
        "--database-url",
        type=str,
        default="postgresql+asyncpg://verdicto:verdicto_secret@db:5432/verdicto",
    )
    args = parser.parse_args()

    segmented_dir = Path(args.segmented_dir)
    if not segmented_dir.exists():
        logger.error(f"Directory not found: {segmented_dir}")
        return

    asyncio.run(fix_titles(segmented_dir, args.database_url))


if __name__ == "__main__":
    main()
