import hashlib
from datetime import timedelta
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ConfigDict, Field
from sqlalchemy import delete, func, or_, select, text as sql_text
from starlette.formparsers import MultiPartParser

from .database import setup_database
from .workspace_api import build_workspace_router
from .group_actions import build_group_actions_router
from .summary_api import build_summary_router
from .analysis_api import build_analysis_router
from .importer import MAX_FILE_BYTES, MAX_TEXT, PREVIEW_TTL_HOURS, build_rows, get_mapping, read_file, safe_filename
from .models import Appeal, ImportBatch, ImportPreview, PrivacyAudit, utcnow
from .privacy import detect_language, mask
from .input_validation import SafeInputModel

ALLOWED_ORIGINS = {"http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000", "http://127.0.0.1:8000"}
MAX_REQUEST_BYTES = MAX_FILE_BYTES + 100_000
# The request stream is capped below, so all accepted original uploads stay in memory.
MultiPartParser.spool_max_size = MAX_REQUEST_BYTES


class RequestBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > MAX_REQUEST_BYTES:
                    raise HTTPException(413, "Максимальный размер файла — 5 МБ.")
            return message

        await self.app(scope, limited_receive, send)


class ConfirmRequest(SafeInputModel):
    model_config = ConfigDict(extra="forbid")
    preview_id: str = Field(min_length=1, max_length=36)


class PrivacyUpdate(SafeInputModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=MAX_TEXT)
    address: str = Field(default="неизвестно", max_length=500)
    version: int = Field(ge=1)


def appeal_json(appeal: Appeal) -> dict:
    return {field: getattr(appeal, field) for field in ("id", "source", "source_record_id", "date", "text", "address", "official_status", "language", "privacy_status", "warnings", "analysis_status", "version")} | {"created_at": appeal.created_at.isoformat() + "Z"}


def batch_json(batch: ImportBatch) -> dict:
    return {field: getattr(batch, field) for field in ("id", "filename", "accepted", "rejected", "duplicates", "conflicts")} | {"created_at": batch.created_at.isoformat() + "Z"}


def confirmed_json(batch: ImportBatch) -> dict:
    return {"batch_id": batch.id, "accepted": batch.accepted, "rejected": batch.rejected, "duplicates": batch.duplicates, "conflicts": batch.conflicts}


def create_app(database_url: str | None = None) -> FastAPI:
    engine, session_factory = setup_database(database_url)
    application = FastAPI(title="Голос района", version="0.2.0", description="Локальный импорт, обезличивание и проверяемый анализ обращений.")
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.include_router(build_analysis_router(session_factory))
    application.include_router(build_workspace_router(session_factory, appeal_json))
    application.include_router(build_group_actions_router(session_factory))
    application.include_router(build_summary_router(session_factory))
    application.add_middleware(RequestBodyLimit)
    application.add_middleware(CORSMiddleware, allow_origins=sorted(ALLOWED_ORIGINS), allow_methods=["GET", "POST", "PATCH"], allow_headers=["Content-Type"])

    @application.middleware("http")
    async def local_request_guard(request: Request, call_next):
        if request.url.hostname not in {"localhost", "127.0.0.1", "testserver"}:
            return JSONResponse(status_code=400, content={"detail": "Используйте локальный адрес localhost или 127.0.0.1."})
        origin = request.headers.get("origin")
        if origin and origin not in ALLOWED_ORIGINS:
            return JSONResponse(status_code=403, content={"detail": "Запросы разрешены только из локального интерфейса."})
        length = request.headers.get("content-length")
        if length:
            try:
                if int(length) > MAX_REQUEST_BYTES:
                    return JSONResponse(status_code=413, content={"detail": "Максимальный размер файла — 5 МБ."})
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Некорректный размер запроса."})
        return await call_next(request)

    @application.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _error: RequestValidationError):
        # Pydantic's normal response includes input values, which may contain personal data.
        return JSONResponse(status_code=422, content={"detail": "Некорректные параметры запроса. Проверьте обязательные поля, длину текста и номер версии."})

    @application.get("/api/health")
    def health():
        with session_factory() as session:
            session.execute(sql_text("SELECT 1"))
        return {"status": "ok", "database": "ok"}

    @application.post("/api/imports/preview")
    def preview(file: UploadFile = File(...), mapping: str | None = Form(default=None)):
        try:
            content = file.file.read(MAX_FILE_BYTES + 1)
            frame = read_file(content, file.filename or "")
        finally:
            file.file.close()
        columns = list(frame.columns)
        chosen_mapping = get_mapping(columns, mapping)
        with session_factory.begin() as session:
            known = {(source, record_id): digest for source, record_id, digest in session.execute(select(Appeal.source, Appeal.source_record_id, Appeal.original_hash))}
            rows = build_rows(frame, chosen_mapping, known)
            session.execute(delete(ImportPreview).where(ImportPreview.created_at < utcnow() - timedelta(hours=PREVIEW_TTL_HOURS), ImportPreview.batch_id.is_(None)))
            record = ImportPreview(id=str(uuid4()), filename=safe_filename(file.filename), rows=rows, columns=columns, mapping=chosen_mapping)
            session.add(record)
            session.flush()
            return {"preview_id": record.id, "filename": record.filename, "columns": columns, "mapping": chosen_mapping, "rows": [{key: value for key, value in row.items() if key != "original_hash"} for row in rows], "total_rows": len(rows), "valid_rows": sum(not row["errors"] for row in rows), "invalid_rows": sum(bool(row["errors"]) for row in rows), "duplicate_rows": sum(row["duplicate_status"] == "duplicate" for row in rows), "conflict_rows": sum(row["duplicate_status"] == "conflict" for row in rows)}

    @application.post("/api/imports/confirm")
    def confirm(payload: ConfirmRequest):
        with session_factory() as session:
            # Serialize imports before reading the preview and unique keys, including repeated clicks.
            session.execute(sql_text("BEGIN IMMEDIATE"))
            record = session.get(ImportPreview, payload.preview_id)
            if record is None:
                raise HTTPException(404, "Предпросмотр не найден. Загрузите файл повторно.")
            if record.batch_id:
                return confirmed_json(session.get(ImportBatch, record.batch_id))
            if record.created_at < utcnow() - timedelta(hours=PREVIEW_TTL_HOURS):
                raise HTTPException(410, "Срок предпросмотра истёк. Загрузите файл повторно.")
            batch = ImportBatch(id=str(uuid4()), filename=record.filename, accepted=0, rejected=0, duplicates=0, conflicts=0)
            session.add(batch)
            session.flush()
            known = {(source, record_id): digest for source, record_id, digest in session.execute(select(Appeal.source, Appeal.source_record_id, Appeal.original_hash))}
            for row in record.rows:
                if row["errors"]:
                    batch.rejected += 1
                    continue
                key = (row["source"], row["source_record_id"])
                if key in known:
                    if known[key] == row["original_hash"]:
                        batch.duplicates += 1
                    else:
                        batch.conflicts += 1
                    continue
                session.add(Appeal(id=str(uuid4()), batch_id=batch.id, **{field: row[field] for field in ("source", "source_record_id", "date", "text", "address", "official_status", "language", "privacy_status", "warnings", "original_hash")}))
                known[key] = row["original_hash"]
                batch.accepted += 1
            record.batch_id = batch.id
            record.rows = []
            session.commit()
            return confirmed_json(batch)

    @application.get("/api/appeals")
    def appeals(q: str = Query(default="", max_length=200), privacy_status: Literal["clear", "masked", "review_required"] | None = None, page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100)):
        conditions = []
        if q.strip():
            query = q.strip().casefold()
            conditions.append(or_(*(func.casefold(column).contains(query, autoescape=True) for column in (Appeal.text, Appeal.address, Appeal.source, Appeal.source_record_id))))
        if privacy_status:
            conditions.append(Appeal.privacy_status == privacy_status)
        with session_factory() as session:
            total = session.scalar(select(func.count()).select_from(Appeal).where(*conditions))
            items = session.scalars(select(Appeal).where(*conditions).order_by(Appeal.created_at.desc(), Appeal.id).offset((page - 1) * page_size).limit(page_size)).all()
            return {"items": [appeal_json(item) for item in items], "total": total, "page": page, "page_size": page_size}

    @application.get("/api/imports")
    def imports():
        with session_factory() as session:
            return [batch_json(batch) for batch in session.scalars(select(ImportBatch).order_by(ImportBatch.created_at.desc(), ImportBatch.id)).all()]

    @application.get("/api/stats")
    def stats():
        with session_factory() as session:
            def grouped(column, key="name"):
                return [{key: value, "count": count} for value, count in session.execute(select(column, func.count(Appeal.id)).group_by(column).order_by(column))]
            return {"total_appeals": session.scalar(select(func.count()).select_from(Appeal)), "total_batches": session.scalar(select(func.count()).select_from(ImportBatch)), "review_required": session.scalar(select(func.count()).select_from(Appeal).where(Appeal.privacy_status == "review_required")), "masked": session.scalar(select(func.count()).select_from(Appeal).where(Appeal.privacy_status == "masked")), "by_source": grouped(Appeal.source), "by_date": grouped(Appeal.date, "date"), "by_territory": grouped(Appeal.address)}

    @application.patch("/api/appeals/{appeal_id}/privacy")
    def review_privacy(appeal_id: str, payload: PrivacyUpdate):
        text_result, address_result = mask(payload.text), mask(payload.address or "неизвестно")
        if text_result.text != payload.text or address_result.text != (payload.address or "неизвестно"):
            raise HTTPException(422, "В правке обнаружены персональные сведения. Удалите их перед подтверждением проверки.")
        with session_factory() as session:
            session.execute(sql_text("BEGIN IMMEDIATE"))
            appeal = session.get(Appeal, appeal_id)
            if appeal is None:
                raise HTTPException(404, "Обращение не найдено.")
            if appeal.version != payload.version:
                raise HTTPException(409, "Обращение уже изменилось. Обновите список и повторите проверку.")
            session.add(PrivacyAudit(id=str(uuid4()), appeal_id=appeal.id, previous_status=appeal.privacy_status, new_status="clear", previous_version=appeal.version, previous_text_hash=hashlib.sha256((appeal.text + "\n" + appeal.address).encode()).hexdigest(), new_text_hash=hashlib.sha256((payload.text + "\n" + (payload.address or "неизвестно")).encode()).hexdigest()))
            appeal.text = payload.text
            appeal.address = payload.address or "неизвестно"
            appeal.privacy_status = "clear"
            appeal.language = detect_language(payload.text)
            appeal.warnings = ["Обезличивание проверено локальным оператором. Полнота автоматического обнаружения не гарантируется."]
            appeal.version += 1
            appeal.analysis_status = "pending"
            session.commit()
            return appeal_json(appeal)

    return application


app = create_app()
