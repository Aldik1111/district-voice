"""Additive analysis tables: importing them registers metadata without altering appeals."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base, utcnow


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    mode: Mapped[str] = mapped_column(String(20))
    rerun_of: Mapped[str | None] = mapped_column(ForeignKey("analysis_runs.id"), nullable=True)
    algorithm: Mapped[dict] = mapped_column(JSON, default=dict)
    snapshot: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    analyzed: Mapped[int] = mapped_column(Integer, default=0)
    blocked: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    uncertainties_count: Mapped[int] = mapped_column(Integer, default=0)
    case_count: Mapped[int] = mapped_column(Integer, default=0)
    problem_count: Mapped[int] = mapped_column(Integer, default=0)
    stale: Mapped[bool] = mapped_column(Boolean, default=False)


class AppealAnalysis(Base):
    __tablename__ = "appeal_analyses"
    __table_args__ = (UniqueConstraint("run_id", "appeal_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    appeal_id: Mapped[str] = mapped_column(ForeignKey("appeals.id"), index=True)
    input_version: Mapped[int] = mapped_column(Integer)
    input_override_version: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30))
    data: Mapped[dict] = mapped_column(JSON)
    appeal_snapshot: Mapped[dict] = mapped_column(JSON)


class AnalysisGroup(Base):
    __tablename__ = "analysis_groups"
    __table_args__ = (UniqueConstraint("run_id", "kind", "group_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    group_key: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    version: Mapped[int] = mapped_column(Integer, default=1)
    data: Mapped[dict] = mapped_column(JSON)


class GroupMembership(Base):
    __tablename__ = "analysis_group_memberships"
    group_id: Mapped[str] = mapped_column(ForeignKey("analysis_groups.id"), primary_key=True)
    appeal_id: Mapped[str] = mapped_column(ForeignKey("appeals.id"), primary_key=True)


class ProblemCase(Base):
    __tablename__ = "analysis_problem_cases"
    problem_id: Mapped[str] = mapped_column(ForeignKey("analysis_groups.id"), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("analysis_groups.id"), primary_key=True)


class CategoryOverride(Base):
    __tablename__ = "category_overrides"
    appeal_id: Mapped[str] = mapped_column(ForeignKey("appeals.id"), primary_key=True)
    category: Mapped[str] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer, default=1)
    reason: Mapped[str] = mapped_column(String(500))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CategoryAudit(Base):
    __tablename__ = "category_audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    appeal_id: Mapped[str] = mapped_column(ForeignKey("appeals.id"), index=True)
    previous_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(500))
    actor: Mapped[str] = mapped_column(String(80), default="local_operator")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
