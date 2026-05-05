"""
SQLAlchemy ORM models for the cases and citations tables.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    ARRAY,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Case(Base):
    """ORM model for the `cases` table."""

    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    case_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    bench: Mapped[str | None] = mapped_column(Text, nullable=True)
    petitioner: Mapped[str | None] = mapped_column(Text, nullable=True)
    respondent: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    disposal_nature: Mapped[str | None] = mapped_column(String(100), nullable=True)
    acts_sections: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text), nullable=True
    )
    citation: Mapped[str | None] = mapped_column(String(200), nullable=True)
    full_text_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Segmented text sections
    facts_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    issues_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Relationships
    citing: Mapped[list[Citation]] = relationship(
        "Citation",
        foreign_keys="Citation.citing_case_id",
        back_populates="citing_case",
        lazy="selectin",
    )
    cited_by: Mapped[list[Citation]] = relationship(
        "Citation",
        foreign_keys="Citation.cited_case_id",
        back_populates="cited_case",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_cases_year", "year"),
    )


class Citation(Base):
    """ORM model for the `citations` table — tracks which cases cite which."""

    __tablename__ = "citations"

    citing_case_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("cases.case_id"),
        primary_key=True,
    )
    cited_case_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("cases.case_id"),
        primary_key=True,
    )
    citation_count: Mapped[int] = mapped_column(Integer, default=1)

    citing_case: Mapped[Case] = relationship(
        "Case",
        foreign_keys=[citing_case_id],
        back_populates="citing",
    )
    cited_case: Mapped[Case] = relationship(
        "Case",
        foreign_keys=[cited_case_id],
        back_populates="cited_by",
    )


class QueryRecord(Base):
    """Stores query history and results for async retrieval and analytics."""

    __tablename__ = "query_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending"
    )  # pending, processing, complete, failed
    filters: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    options: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    result: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    agent_trace: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
