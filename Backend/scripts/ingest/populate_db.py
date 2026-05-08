"""
Populate the PostgreSQL `cases` table from segmented JSON files.

Each segmented JSON file (e.g. 2024_1_1_10_EN.json) maps directly to a
case_id in the FAISS index. This script reads those files and inserts
case records into the database so the retriever can fetch metadata.

Usage (from Backend/ directory):
    python -m scripts.ingest.populate_db --segmented-dir ../../data/processed/segmented
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import uuid
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _parse_year_from_case_id(case_id: str) -> int:
    """Extract year from case_id like '2024_1_1_10_EN' → 2024."""
    match = re.match(r"^(\d{4})_", case_id)
    if match:
        return int(match.group(1))
    return 2024


def _build_title(case_id: str, facts: str, issues: str) -> str:
    """Build a reasonable title from available text."""
    # Try to extract a title from the first line of facts or issues
    for text_block in [facts, issues]:
        if text_block:
            first_line = text_block.strip().split("\n")[0].strip()
            if 10 < len(first_line) < 200:
                return first_line[:200]
    return f"Case {case_id}"


async def populate(segmented_dir: Path, database_url: str, batch_size: int = 100) -> None:
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    json_files = sorted(segmented_dir.glob("*.json"))
    logger.info(f"Found {len(json_files)} segmented JSON files")

    inserted = 0
    skipped = 0
    errors = 0

    async with async_session() as session:
        # Check existing case_ids to avoid duplicates
        result = await session.execute(text("SELECT case_id FROM cases"))
        existing_ids: set[str] = {row[0] for row in result.fetchall()}
        logger.info(f"Found {len(existing_ids)} existing cases in DB")

        batch: list[dict] = []

        for json_file in json_files:
            case_id = json_file.stem  # e.g. "2024_1_1_10_EN"

            if case_id in existing_ids:
                skipped += 1
                continue

            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                facts = data.get("facts", "") or ""
                issues = data.get("issues", "") or ""
                reasoning = data.get("reasoning", "") or ""
                outcome = data.get("outcome", "") or ""

                year = _parse_year_from_case_id(case_id)
                title = _build_title(case_id, facts, issues)

                batch.append({
                    "id": str(uuid.uuid4()),
                    "case_id": case_id,
                    "year": year,
                    "title": title,
                    "facts_text": facts[:10000] if facts else None,
                    "issues_text": issues[:5000] if issues else None,
                    "reasoning_text": reasoning[:10000] if reasoning else None,
                    "outcome_text": outcome[:5000] if outcome else None,
                })

                if len(batch) >= batch_size:
                    await _insert_batch(session, batch)
                    inserted += len(batch)
                    logger.info(f"Inserted {inserted} cases so far...")
                    batch = []

            except Exception as e:
                logger.error(f"Failed to process {json_file.name}: {e}")
                errors += 1
                continue

        # Insert remaining
        if batch:
            await _insert_batch(session, batch)
            inserted += len(batch)

    logger.info(f"Done. Inserted: {inserted}, Skipped (already existed): {skipped}, Errors: {errors}")
    await engine.dispose()


async def _insert_batch(session: AsyncSession, batch: list[dict]) -> None:
    """Insert a batch of case records using raw SQL for speed."""
    if not batch:
        return

    values_sql = ", ".join(
        f"('{r['id']}', '{r['case_id']}', {r['year']}, :title_{i}, :facts_{i}, :issues_{i}, :reasoning_{i}, :outcome_{i})"
        for i, r in enumerate(batch)
    )

    params: dict = {}
    for i, r in enumerate(batch):
        params[f"title_{i}"] = r["title"]
        params[f"facts_{i}"] = r["facts_text"]
        params[f"issues_{i}"] = r["issues_text"]
        params[f"reasoning_{i}"] = r["reasoning_text"]
        params[f"outcome_{i}"] = r["outcome_text"]

    sql = text(f"""
        INSERT INTO cases (id, case_id, year, title, facts_text, issues_text, reasoning_text, outcome_text)
        VALUES {values_sql}
        ON CONFLICT (case_id) DO NOTHING
    """)

    await session.execute(sql, params)
    await session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Populate cases table from segmented JSON files")
    parser.add_argument(
        "--segmented-dir",
        type=str,
        default="../../data/processed/segmented",
        help="Directory containing segmented JSON files",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default="postgresql+asyncpg://verdicto:verdicto_secret@localhost:5433/verdicto",
        help="PostgreSQL async connection URL",
    )
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()

    segmented_dir = Path(args.segmented_dir)
    if not segmented_dir.exists():
        logger.error(f"Segmented directory not found: {segmented_dir}")
        return

    asyncio.run(populate(segmented_dir, args.database_url, args.batch_size))


if __name__ == "__main__":
    main()
