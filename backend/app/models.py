from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class ImportPreview(Base):
    __tablename__ = "import_previews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    rows: Mapped[list] = mapped_column(JSON)
    columns: Mapped[list] = mapped_column(JSON)
    mapping: Mapped[dict] = mapped_column(JSON)
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    accepted: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    conflicts: Mapped[int] = mapped_column(Integer, default=0)


class Appeal(Base):
    __tablename__ = "appeals"
    __table_args__ = (UniqueConstraint("source", "source_record_id", name="uq_appeal_source_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id"))
    source: Mapped[str] = mapped_column(String(120), index=True)
    source_record_id: Mapped[str] = mapped_column(String(160))
    date: Mapped[str] = mapped_column(String(10), index=True)
    text: Mapped[str] = mapped_column(Text)
    address: Mapped[str] = mapped_column(String(500), default="неизвестно")
    official_status: Mapped[str] = mapped_column(String(120), default="неизвестно")
    language: Mapped[str] = mapped_column(String(20))
    privacy_status: Mapped[str] = mapped_column(String(30), index=True)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    analysis_status: Mapped[str] = mapped_column(String(30), default="pending")
    original_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PrivacyAudit(Base):
    __tablename__ = "privacy_audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    appeal_id: Mapped[str] = mapped_column(ForeignKey("appeals.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    actor: Mapped[str] = mapped_column(String(80), default="local_operator")
    previous_status: Mapped[str] = mapped_column(String(30))
    new_status: Mapped[str] = mapped_column(String(30))
    previous_version: Mapped[int] = mapped_column(Integer)
    previous_text_hash: Mapped[str] = mapped_column(String(64))
    new_text_hash: Mapped[str] = mapped_column(String(64))
