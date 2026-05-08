"""
Fix remaining bad titles (those without 'v.' pattern) using first meaningful line.
"""
import asyncio
import json
import re
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DB_URL = "postgresql+asyncpg://verdicto:verdicto_secret@db:5432/verdicto"
SEG_DIR = Path("/app/data/processed/segmented")


async def fix() -> None:
    engine = create_async_engine(DB_URL)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as s:
        r = await s.execute(text(
            "SELECT case_id FROM cases WHERE title NOT LIKE :p1 AND title NOT LIKE :p2 AND title NOT LIKE :p3"
        ), {"p1": "%v.%", "p2": "%vs.%", "p3": "%Vs.%"})
        bad_ids = [row[0] for row in r.fetchall()]
        print(f"Fixing {len(bad_ids)} titles")

        for cid in bad_ids:
            f = SEG_DIR / f"{cid}.json"
            if not f.exists():
                continue
            data = json.loads(f.read_text(encoding="utf-8"))

            new_title = None
            for field in ["reasoning", "outcome", "facts"]:
                text_block = (data.get(field) or "").strip()
                if not text_block:
                    continue
                lines = [l.strip() for l in text_block.split("\n") if l.strip()]
                for line in lines[:15]:
                    # Skip lines that are too short, too long, start with numbers/brackets
                    if 15 < len(line) < 150 and not line[0].isdigit() and not line.startswith("["):
                        clean = re.sub(r"\s+", " ", line).strip()
                        # Prefer lines that look like headings (contain uppercase words)
                        if re.search(r"[A-Z]{3,}", clean):
                            new_title = clean[:200]
                            break
                if new_title:
                    break

            if new_title:
                await s.execute(
                    text("UPDATE cases SET title = :t WHERE case_id = :c"),
                    {"t": new_title, "c": cid},
                )

        await s.commit()
        print("Done")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(fix())
