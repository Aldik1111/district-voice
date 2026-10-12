"""Versioned, approval-time SQLite snapshots and real CSV/XLSX exports."""
import csv
import hashlib
import io
import json
from collections import Counter
from datetime import date, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import ConfigDict, Field, model_validator
from sqlalchemy import DateTime, Integer, JSON, String, Text, UniqueConstraint, func, select, text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from .analysis_api import group_json, selected_run, stale_run, timestamp
from .analysis_models import AnalysisGroup, AnalysisRun, AppealAnalysis
from .group_actions import DEMO_ACTOR
from .models import Base, utcnow
from .privacy import mask
from .input_validation import SafeInputModel


class Summary(Base):
    __tablename__ = "summaries"
    __table_args__ = (UniqueConstraint("series_id", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    series_id: Mapped[str] = mapped_column(String(36), index=True)
    version: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    scope: Mapped[dict] = mapped_column(JSON)
    snapshot: Mapped[dict] = mapped_column(JSON)
    checksum: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    actor: Mapped[str] = mapped_column(String(80), default=DEMO_ACTOR)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Scope(SafeInputModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    start: date
    end: date
    territory: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def ordered(self):
        if self.start > self.end:
            raise ValueError("invalid period")
        return self


class CreateSummary(Scope):
    title: str = Field(default="Аналитическая сводка", min_length=3, max_length=160)
    previous_id: str | None = None


class EditSummary(SafeInputModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    revision: int = Field(ge=1)
    title: str = Field(min_length=3, max_length=160)
    body: str = Field(min_length=3, max_length=10000)


class ApproveSummary(SafeInputModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)


def calculated_snapshot(session, scope):
    run = selected_run(session, None)
    if not run or stale_run(session, run):
        raise HTTPException(409, "Для сводки нужен актуальный завершённый анализ.")
    if session.scalar(select(AnalysisRun.id).where(AnalysisRun.status == "running").limit(1)):
        raise HTTPException(409, "Дождитесь завершения анализа.")
    results = list(session.scalars(select(AppealAnalysis).where(AppealAnalysis.run_id == run.id).order_by(AppealAnalysis.appeal_id)))
    if scope.get("territory") is not None and scope["territory"] not in {item.data.get("territory") or "Территория неизвестна" for item in results}:
        raise HTTPException(422, "Выберите территорию из списка текущего анализа.")
    chosen = [item for item in results if scope["start"] <= item.appeal_snapshot["date"] <= scope["end"] and (scope.get("territory") is None or (item.data.get("territory") or "Территория неизвестна") == scope["territory"])]
    evidence = [{"id": item.appeal_id, "category": item.category, "duplicate_of": item.data.get("duplicate_of"),
                 "territory": item.data.get("territory"), "analysis_status": item.status, **item.appeal_snapshot} for item in chosen]
    groups = []
    active = list(session.scalars(select(AnalysisGroup).where(AnalysisGroup.run_id == run.id, AnalysisGroup.status != "archived").order_by(AnalysisGroup.id)))
    # Group-category edits do not silently rewrite original classification. A manual
    # case category is the effective category in this reviewed report's breakdown.
    effective = {}
    for group in active:
        if group.kind == "case":
            for appeal_id in group_json(session, group)["appeal_ids"]:
                effective[appeal_id] = group.data["category"]
        if group.status != "confirmed":
            continue
        value = group_json(session, group)
        scoped = [item for item in evidence if item["id"] in set(value["appeal_ids"])]
        if not scoped:
            continue
        value = {key: value[key] for key in ("id", "kind", "version", "category", "territory", "status", "case_ids", "explanations", "uncertainties")}
        value.update(title=group.data.get("title", group.data["category"]), appeal_ids=sorted(item["id"] for item in scoped),
                     message_count=len(scoped), source_count=len({item["source"] for item in scoped}), sources=sorted({item["source"] for item in scoped}),
                     start_date=min(item["date"] for item in scoped), end_date=max(item["date"] for item in scoped),
                     scope_clipped=len(scoped) != group.data["message_count"])
        groups.append(value)
    for item in evidence:
        item["category"] = effective.get(item["id"], item["category"])
    eligible = [item for item in evidence if item["analysis_status"] != "blocked"]
    return {"scope": scope, "run_id": run.id, "algorithm": run.algorithm,
            "total_messages": len(evidence), "unique_messages": len({item["duplicate_of"] or item["id"] for item in eligible}),
            "blocked_messages": len(evidence) - len(eligible), "confirmed_groups": len(groups),
            "confirmed_problems": sum(item["kind"] == "problem" for item in groups),
            "categories": dict(sorted(Counter(item["category"] for item in eligible).items())),
            "territories": dict(sorted(Counter(item["territory"] or "Территория неизвестна" for item in eligible).items())),
            "sources": dict(sorted(Counter(item["source"] for item in evidence).items())),
            "synthetic_messages": sum(item["source"].startswith("ДЕМО ·") for item in evidence),
            "groups": groups, "evidence": evidence,
            "counting_note": "Уникальные — семейства публикаций по текущему анализу, не число жителей. Заблокированные записи не входят в уникальные. Числа групп ограничены выбранным периодом и территорией; суммы по группам могут пересекаться (случай и проблема)."}


def summary_json(item):
    return {key: getattr(item, key) for key in ("id", "series_id", "version", "revision", "status", "title", "body", "scope", "snapshot", "checksum", "actor")} | {"created_at": timestamp(item.created_at), "approved_at": timestamp(item.approved_at)}


def safe_cell(value):
    value = "" if value is None else str(value)
    # Prevent spreadsheet formula execution, including leading whitespace/control chars.
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")) else value


def export_rows(item):
    data = item.snapshot
    header = ["Тип строки", "Версия сводки", "Время утверждения UTC", "Период с", "Период по", "Фильтр территории", "Всего сообщений", "Уникальных сообщений", "ID", "Название / текст", "Категория", "Территория", "Источники", "Подтверждающие ID", "Статус проверки", "Сообщений в группе", "Источников в группе", "Дата с", "Дата по", "SHA256 снимка"]
    prefix = [item.version, timestamp(item.approved_at), data["scope"]["start"], data["scope"]["end"], data["scope"].get("territory") or "Все территории", data["total_messages"], data["unique_messages"]]
    rows = [header, ["Сводка", *prefix, item.id, item.title + "\n" + item.body, json.dumps(data["categories"], ensure_ascii=False), json.dumps(data["territories"], ensure_ascii=False), json.dumps(data["sources"], ensure_ascii=False), "; ".join(entry["id"] for entry in data["evidence"]), "Утверждена", "", "", "", "", item.checksum]]
    for group in data["groups"]:
        rows.append(["Проблема" if group["kind"] == "problem" else "Случай", *prefix, group["id"], group["title"], group["category"], group["territory"], "; ".join(group["sources"]), "; ".join(group["appeal_ids"]), group["status"], group["message_count"], group["source_count"], group["start_date"], group["end_date"], item.checksum])
    for evidence in data["evidence"]:
        rows.append(["Обращение", *prefix, evidence["id"], evidence["text"], evidence["category"], evidence["territory"], evidence["source"], evidence["id"], evidence["analysis_status"], "", "", evidence["date"], evidence["date"], item.checksum])
    return [[safe_cell(value) for value in row] for row in rows]


def build_summary_router(session_factory):
    router = APIRouter(prefix="/api/summaries", tags=["summaries"])

    @router.get("/options")
    def options():
        with session_factory() as session:
            run = selected_run(session, None)
            results = list(session.scalars(select(AppealAnalysis).where(AppealAnalysis.run_id == run.id))) if run else []
            dates = sorted(item.appeal_snapshot["date"] for item in results)
            return {"start": dates[0] if dates else None, "end": dates[-1] if dates else None,
                    "territories": sorted({item.data.get("territory") or "Территория неизвестна" for item in results})}

    @router.post("/preview")
    def preview(payload: Scope):
        with session_factory() as session:
            return calculated_snapshot(session, payload.model_dump(mode="json"))

    @router.get("")
    def listing():
        with session_factory() as session:
            return [{key: value for key, value in summary_json(item).items() if key not in {"snapshot", "body"}} for item in session.scalars(select(Summary).order_by(Summary.created_at.desc(), Summary.version.desc()))]

    @router.post("")
    def create(payload: CreateSummary):
        if mask(payload.title).text != payload.title:
            raise HTTPException(422, "Уберите персональные сведения из заголовка.")
        with session_factory() as session:
            session.execute(sql_text("BEGIN IMMEDIATE"))
            scope = payload.model_dump(mode="json", include={"start", "end", "territory"})
            snapshot = calculated_snapshot(session, scope)
            previous = session.get(Summary, payload.previous_id) if payload.previous_id else None
            if payload.previous_id and not previous:
                raise HTTPException(404, "Предыдущая версия не найдена.")
            series = previous.series_id if previous else str(uuid4())
            version = (session.scalar(select(func.max(Summary.version)).where(Summary.series_id == series)) or 0) + 1
            item = Summary(id=str(uuid4()), series_id=series, version=version, title=payload.title,
                           body=previous.body if previous else "Сводка подготовлена по обезличенным обращениям. Подтверждённые группы и рассчитанные показатели приведены ниже. Причины событий и независимость авторов не установлены.",
                           scope=scope, snapshot=snapshot, checksum=digest(snapshot))
            session.add(item)
            session.commit()
            return summary_json(item)

    def get_item(session, summary_id, revision=None):
        item = session.get(Summary, summary_id)
        if not item:
            raise HTTPException(404, "Сводка не найдена.")
        if revision is not None and (item.status != "draft" or item.revision != revision):
            raise HTTPException(409, "Версия уже утверждена или изменена. Обновите страницу; утверждённую версию можно только скопировать в новый черновик.")
        return item

    @router.get("/{summary_id}")
    def get(summary_id: str):
        with session_factory() as session:
            return summary_json(get_item(session, summary_id))

    @router.patch("/{summary_id}")
    def edit(summary_id: str, payload: EditSummary):
        if any(mask(value).text != value for value in (payload.title, payload.body)):
            raise HTTPException(422, "Уберите персональные сведения из текста сводки.")
        with session_factory() as session:
            session.execute(sql_text("BEGIN IMMEDIATE"))
            item = get_item(session, summary_id, payload.revision)
            item.title, item.body = payload.title, payload.body
            item.revision += 1
            session.commit()
            return summary_json(item)

    @router.post("/{summary_id}/approve")
    def approve(summary_id: str, payload: ApproveSummary):
        with session_factory() as session:
            session.execute(sql_text("BEGIN IMMEDIATE"))
            item = get_item(session, summary_id, payload.revision)
            current = calculated_snapshot(session, item.scope)
            if digest(current) != digest(item.snapshot):
                raise HTTPException(409, "Данные изменились после создания черновика. Создайте новую версию, проверьте обновлённые показатели и утвердите её.")
            if not current["total_messages"] or not current["confirmed_groups"]:
                raise HTTPException(422, "В выбранном срезе нужны обращения и хотя бы одна подтверждённая группа.")
            item.snapshot = current
            item.status, item.approved_at = "approved", utcnow()
            item.revision += 1
            item.checksum = digest({"snapshot": current, "title": item.title, "body": item.body, "version": item.version, "approved_at": timestamp(item.approved_at), "actor": item.actor})
            session.commit()
            return summary_json(item)

    @router.get("/{summary_id}/export/{format}")
    def export(summary_id: str, format: str):
        if format not in {"csv", "xlsx"}:
            raise HTTPException(422, "Поддерживаются CSV и XLSX.")
        with session_factory() as session:
            item = get_item(session, summary_id)
            if item.status != "approved":
                raise HTTPException(409, "Сначала утвердите версию сводки.")
            rows = export_rows(item)
            if format == "csv":
                output = io.StringIO(newline="")
                csv.writer(output).writerows(rows)
                content, mime = output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8"
            else:
                from openpyxl import Workbook
                from openpyxl.styles import Font
                workbook = Workbook()
                sheet = workbook.active
                sheet.title = "Утверждённая сводка"
                for row in rows:
                    sheet.append(row)
                for cell in sheet[1]:
                    cell.font = Font(bold=True)
                sheet.freeze_panes = "A2"
                sheet.auto_filter.ref = sheet.dimensions
                output = io.BytesIO()
                workbook.save(output)
                content, mime = output.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            return Response(content, media_type=mime, headers={"Content-Disposition": f'attachment; filename="district-voice-summary-{item.id[:8]}-v{item.version}.{format}"'})

    return router
