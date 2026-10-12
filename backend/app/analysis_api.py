"""Local analysis API. Runs and evidence are immutable snapshots; overrides are separate."""
from contextlib import asynccontextmanager
from copy import deepcopy
from math import isfinite
from threading import Lock
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import ConfigDict, Field
from sqlalchemy import func, select, text as sql_text

from .analysis_models import AnalysisGroup, AnalysisRun, AppealAnalysis, CategoryAudit, CategoryOverride, GroupMembership, ProblemCase
from .models import Appeal, utcnow
from .privacy import mask
from .input_validation import SafeInputModel

MAX_ANALYSIS_APPEALS = 500
_DATABASE_LOCKS: dict[str, Lock] = {}
_LOCK_REGISTRY_GUARD = Lock()


class RunRequest(SafeInputModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["auto", "tfidf"] = "auto"


class CategoryRequest(SafeInputModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    category: str = Field(min_length=1, max_length=100)
    version: int = Field(ge=1)
    reason: str = Field(default="Правка аналитика", min_length=3, max_length=500)


def get_engine():
    try:
        from .ai import engine
    except ImportError:
        raise HTTPException(503, "Не установлены зависимости локального анализа. Выполните инструкции установки из README проекта.") from None
    return engine


def categories() -> list[str]:
    return list(get_engine().CATEGORIES)


def safe_data(value):
    """Defence in depth for engine explanations and manually supplied reasons."""
    if isinstance(value, str):
        return mask(value).text
    if isinstance(value, list):
        return [safe_data(item) for item in value]
    if isinstance(value, dict):
        identities = {"id", "appeal_id", "run_id", "key", "duplicate_of", "appeal_ids", "case_keys"}
        return {key: item if key in identities else safe_data(item) for key, item in value.items()}
    return value


def timestamp(value):
    return value.isoformat() + "Z" if value else None


def snapshot_state(session) -> list[dict]:
    overrides = dict(session.execute(select(CategoryOverride.appeal_id, CategoryOverride.version)).all())
    return [{"id": appeal_id, "version": version, "override_version": overrides.get(appeal_id, 0)} for appeal_id, version in session.execute(select(Appeal.id, Appeal.version).order_by(Appeal.id))]


def stale_run(session, run: AnalysisRun) -> bool:
    return run.stale or run.snapshot != snapshot_state(session)


def run_json(session, run: AnalysisRun) -> dict:
    counts = dict(session.execute(select(AnalysisGroup.kind, func.count()).where(AnalysisGroup.run_id == run.id, AnalysisGroup.status != "archived").group_by(AnalysisGroup.kind)).all())
    return {field: getattr(run, field) for field in ("id", "status", "mode", "rerun_of", "algorithm", "total", "analyzed", "blocked", "error_count", "errors", "uncertainties_count")} | {"case_count": counts.get("case", 0), "problem_count": counts.get("problem", 0), "created_at": timestamp(run.created_at), "finished_at": timestamp(run.finished_at), "stale": stale_run(session, run)}


def selected_run(session, run_id: str | None) -> AnalysisRun | None:
    if run_id:
        run = session.get(AnalysisRun, run_id)
        if run is None:
            raise HTTPException(404, "Запуск анализа не найден.")
        return run
    return session.scalar(select(AnalysisRun).where(AnalysisRun.status == "completed").order_by(AnalysisRun.created_at.desc(), AnalysisRun.id).limit(1))


def result_json(session, result: AppealAnalysis) -> dict:
    override = session.get(CategoryOverride, result.appeal_id)
    appeal = session.get(Appeal, result.appeal_id)
    override_version = override.version if override else 0
    return result.data | result.appeal_snapshot | {
        "id": result.id, "run_id": result.run_id, "appeal_id": result.appeal_id,
        "version": override_version + 1, "input_version": result.input_version,
        "override_category": override.category if override else None,
        "requires_reanalysis": override_version != result.input_override_version or appeal.version != result.input_version,
    }


def group_json(session, group: AnalysisGroup) -> dict:
    appeal_ids = list(session.scalars(select(GroupMembership.appeal_id).where(GroupMembership.group_id == group.id).order_by(GroupMembership.appeal_id)))
    case_ids = list(session.scalars(select(ProblemCase.case_id).where(ProblemCase.problem_id == group.id).order_by(ProblemCase.case_id)))
    return group.data | {"id": group.id, "run_id": group.run_id, "kind": group.kind, "status": group.status, "version": group.version, "appeal_ids": appeal_ids, "case_ids": case_ids, "stale": stale_run(session, session.get(AnalysisRun, group.run_id))}


def validate_output(output: dict, records: list[dict]) -> None:
    """Reject invalid identities/counts instead of persisting unverifiable evidence."""
    allowed = set(categories())
    record_map = {item["id"]: item for item in records}
    if not isinstance(output, dict) or not isinstance(output.get("algorithm"), dict):
        raise ValueError("invalid engine output")
    algorithm = output["algorithm"]
    if not isinstance(algorithm.get("name"), str) or not isinstance(algorithm.get("label"), str) or not isinstance(algorithm.get("semantic"), bool):
        raise ValueError("invalid algorithm metadata")
    results = output.get("results")
    if not isinstance(results, list) or len(results) != len(records):
        raise ValueError("incomplete results")
    result_map = {}
    for result in results:
        appeal_id = result.get("appeal_id")
        if appeal_id not in record_map or appeal_id in result_map:
            raise ValueError("invalid result identity")
        if result.get("category") not in allowed or result.get("proposed_category") not in allowed:
            raise ValueError("invalid category")
        if result.get("status") not in {"analyzed", "review_required", "blocked"}:
            raise ValueError("invalid status")
        if record_map[appeal_id]["privacy_status"] == "review_required" and result["status"] != "blocked":
            raise ValueError("privacy blocker bypassed")
        if result.get("input_version") != record_map[appeal_id]["version"]:
            raise ValueError("invalid input version")
        if result.get("duplicate_kind") not in {"independent", "republication_candidate"}:
            raise ValueError("invalid duplicate kind")
        if result.get("duplicate_of") is not None and (result["duplicate_of"] not in record_map or result["duplicate_of"] == appeal_id):
            raise ValueError("invalid duplicate reference")
        if not isinstance(result.get("uncertainties"), list) or not isinstance(result.get("explanations"), list):
            raise ValueError("invalid explanation")
        if any(not isinstance(item, str) for item in result["uncertainties"] + result["explanations"]):
            raise ValueError("invalid explanation text")
        if not isinstance(result.get("classification_method"), str):
            raise ValueError("invalid classification method")
        score = result.get("score")
        if not isinstance(score, (int, float)) or not isfinite(score) or not 0 <= score <= 1:
            raise ValueError("invalid score")
        if result.get("territory") is not None and not isinstance(result["territory"], str):
            raise ValueError("invalid territory")
        result_map[appeal_id] = result
    for appeal_id, result in result_map.items():
        reference = result.get("duplicate_of")
        if (result["duplicate_kind"] == "independent") != (reference is None):
            raise ValueError("inconsistent duplicate metadata")
        if reference is not None:
            anchor = result_map[reference]
            if anchor["status"] == "blocked" or anchor.get("duplicate_of") is not None or anchor["category"] != result["category"] or anchor.get("territory") != result.get("territory"):
                raise ValueError("invalid publication anchor")
    case_map = {}
    case_members = set()
    for kind, groups in (("case", output.get("cases")), ("problem", output.get("problems"))):
        if not isinstance(groups, list):
            raise ValueError("invalid groups")
        seen_keys = set()
        for group in groups:
            key = group.get("key")
            if not isinstance(key, str) or not key or len(key) > 200 or key in seen_keys:
                raise ValueError("invalid group key")
            seen_keys.add(key)
            ids = group.get("appeal_ids")
            if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids) or any(item not in record_map for item in ids):
                raise ValueError("invalid evidence ids")
            if any(result_map[item]["status"] == "blocked" for item in ids):
                raise ValueError("blocked evidence")
            if group.get("category") not in allowed or group.get("status") != "proposed":
                raise ValueError("invalid group category/status")
            if group.get("message_count") != len(ids) or group.get("source_count") != len({record_map[item]["source"] for item in ids}):
                raise ValueError("invalid evidence counts")
            evidence_count = group.get("independent_evidence_count")
            potential_originals = sum(result_map[item].get("duplicate_of") is None for item in ids)
            if not isinstance(evidence_count, int) or evidence_count != potential_originals:
                raise ValueError("invalid independent evidence count")
            if any(result_map[item]["category"] != group["category"] or result_map[item].get("territory") != group.get("territory") for item in ids):
                raise ValueError("group location/category mismatch")
            similarity = group.get("minimum_similarity")
            if not isinstance(similarity, (int, float)) or not isfinite(similarity) or not 0 <= similarity <= 1:
                raise ValueError("invalid similarity")
            if not isinstance(group.get("explanations"), list) or not isinstance(group.get("uncertainties"), list) or any(not isinstance(item, str) for item in group["explanations"] + group["uncertainties"]):
                raise ValueError("invalid group explanations")
            if group.get("start_date") != min(record_map[item]["date"] for item in ids) or group.get("end_date") != max(record_map[item]["date"] for item in ids):
                raise ValueError("invalid evidence dates")
            if kind == "case":
                if case_members.intersection(ids):
                    raise ValueError("overlapping concrete cases")
                case_members.update(ids)
                case_map[key] = group
            else:
                case_keys = group.get("case_keys")
                if not isinstance(case_keys, list) or len(case_keys) < 2 or len(set(case_keys)) != len(case_keys) or any(item not in case_map for item in case_keys):
                    raise ValueError("invalid case references")
                if set(ids) != {item for case_key in case_keys for item in case_map[case_key]["appeal_ids"]}:
                    raise ValueError("problem evidence mismatch")
    if case_members != {appeal_id for appeal_id, result in result_map.items() if result["status"] != "blocked"}:
        raise ValueError("incomplete concrete case evidence")


def build_analysis_router(session_factory) -> APIRouter:
    database_engine = session_factory.kw["bind"]
    lock_key = str(database_engine.url)
    if lock_key in {"sqlite://", "sqlite:///:memory:"}:
        lock_key += str(id(database_engine))
    with _LOCK_REGISTRY_GUARD:
        analysis_lock = _DATABASE_LOCKS.setdefault(lock_key, Lock())
    # This application is run as one local process. A process restart must not leave
    # persisted 'running' records permanently blocking retry. Live runs in another
    # app instance in this same process hold the shared database lock.
    @asynccontextmanager
    async def analysis_lifespan(_app):
        if analysis_lock.acquire(blocking=False):
            try:
                with session_factory() as session:
                    session.execute(sql_text("BEGIN IMMEDIATE"))
                    interrupted = session.scalars(select(AnalysisRun).where(AnalysisRun.status == "running")).all()
                    for previous in interrupted:
                        previous.status = "failed"
                        previous.finished_at = utcnow()
                        previous.error_count = 1
                        previous.errors = [{"kind": "interrupted", "message": "Предыдущий запуск прерван остановкой сервера. Данные сохранены; можно повторить анализ."}]
                        for appeal in session.scalars(select(Appeal).where(Appeal.id.in_([item["id"] for item in previous.snapshot]))):
                            appeal.analysis_status = "error"
                    session.commit()
            finally:
                analysis_lock.release()
        yield

    router = APIRouter(prefix="/api", tags=["analysis"], lifespan=analysis_lifespan)

    def perform_run(mode: str, rerun_of: str | None = None):
        if not analysis_lock.acquire(blocking=False):
            raise HTTPException(409, "Анализ уже выполняется. Дождитесь окончания текущего запуска.")
        run_id = None
        try:
            with session_factory() as session:
                session.execute(sql_text("BEGIN IMMEDIATE"))
                appeal_count = session.scalar(select(func.count()).select_from(Appeal))
                if not appeal_count:
                    raise HTTPException(422, "Сначала импортируйте обращения.")
                if appeal_count > MAX_ANALYSIS_APPEALS:
                    raise HTTPException(422, f"Локальный анализ поддерживает не более {MAX_ANALYSIS_APPEALS} обращений. Данные не были усечены или изменены.")
                appeals = session.scalars(select(Appeal).order_by(Appeal.id)).all()
                if session.scalar(select(AnalysisRun.id).where(AnalysisRun.status == "running").limit(1)):
                    raise HTTPException(409, "В базе есть выполняющийся анализ. Дождитесь завершения или перезапустите сервер после сбоя.")
                overrides = {item.appeal_id: item for item in session.scalars(select(CategoryOverride))}
                snapshot = snapshot_state(session)
                records = []
                for appeal in appeals:
                    record = {field: getattr(appeal, field) for field in ("id", "source", "source_record_id", "date", "text", "address", "privacy_status", "version", "language")}
                    record["override_category"] = overrides[appeal.id].category if appeal.id in overrides else None
                    records.append(record)
                    appeal.analysis_status = "running"
                run = AnalysisRun(id=str(uuid4()), status="running", mode=mode, rerun_of=rerun_of, snapshot=snapshot, total=len(records), algorithm={"name": "pending", "label": "Алгоритм ещё не определён", "semantic": False, "model_id": None, "fallback_reason": None})
                run_id = run.id
                session.add(run)
                session.commit()
            try:
                output = get_engine().analyze(deepcopy(records), mode=mode)
                validate_output(output, records)
                output = safe_data(output)
                with session_factory() as session:
                    session.execute(sql_text("BEGIN IMMEDIATE"))
                    run = session.get(AnalysisRun, run_id)
                    if snapshot_state(session) != snapshot:
                        run.status = "failed"
                        run.stale = True
                        run.finished_at = utcnow()
                        run.error_count = 1
                        run.errors = [{"kind": "stale_snapshot", "message": "Обращения изменились во время анализа. Запустите анализ повторно; предыдущие результаты сохранены."}]
                        for item in session.scalars(select(Appeal).where(Appeal.id.in_([record["id"] for record in records]))):
                            item.analysis_status = "pending"
                        session.commit()
                        return run_json(session, run)
                    record_map = {record["id"]: record for record in records}
                    snapshot_map = {item["id"]: item for item in snapshot}
                    for result in output["results"]:
                        appeal_id = result["appeal_id"]
                        record = record_map[appeal_id]
                        session.add(AppealAnalysis(id=str(uuid4()), run_id=run_id, appeal_id=appeal_id, input_version=result["input_version"], input_override_version=snapshot_map[appeal_id]["override_version"], category=result["category"], status=result["status"], data=result, appeal_snapshot=safe_data({field: record[field] for field in ("source", "source_record_id", "text", "address", "date", "language", "privacy_status")})))
                        session.get(Appeal, appeal_id).analysis_status = result["status"]
                    case_ids = {}
                    for kind, groups in (("case", output["cases"]), ("problem", output["problems"])):
                        for group in groups:
                            saved = AnalysisGroup(id=str(uuid4()), run_id=run_id, kind=kind, group_key=group["key"], status="proposed", data={key: value for key, value in group.items() if key not in {"appeal_ids", "case_keys", "status"}})
                            session.add(saved)
                            session.flush()
                            for appeal_id in group["appeal_ids"]:
                                session.add(GroupMembership(group_id=saved.id, appeal_id=appeal_id))
                            if kind == "case":
                                case_ids[group["key"]] = saved.id
                            else:
                                for case_key in group["case_keys"]:
                                    session.add(ProblemCase(problem_id=saved.id, case_id=case_ids[case_key]))
                    run.status = "completed"
                    run.algorithm = output["algorithm"]
                    run.finished_at = utcnow()
                    run.blocked = sum(result["status"] == "blocked" for result in output["results"])
                    run.analyzed = len(records) - run.blocked
                    run.uncertainties_count = sum(bool(result["uncertainties"]) for result in output["results"])
                    run.case_count = len(output["cases"])
                    run.problem_count = len(output["problems"])
                    session.commit()
                    return run_json(session, run)
            except Exception:
                # Never publish exception text: libraries can include original input strings.
                with session_factory() as session:
                    session.execute(sql_text("BEGIN IMMEDIATE"))
                    run = session.get(AnalysisRun, run_id)
                    run.status = "failed"
                    run.finished_at = utcnow()
                    run.error_count = 1
                    run.errors = [{"kind": "analysis_error", "message": "Локальный анализ не завершён. Данные и предыдущие результаты сохранены. Повторите запуск."}]
                    for item in session.scalars(select(Appeal).where(Appeal.id.in_([record["id"] for record in records]))):
                        item.analysis_status = "error"
                    session.commit()
                    return run_json(session, run)
        finally:
            analysis_lock.release()

    @router.get("/analysis/status")
    def analysis_status():
        engine_status = safe_data(get_engine().get_engine_status())
        with session_factory() as session:
            latest = session.scalar(select(AnalysisRun).order_by(AnalysisRun.created_at.desc(), AnalysisRun.id).limit(1))
            return {"algorithm": engine_status, "latest_run": run_json(session, latest) if latest else None, "categories": categories(), "total_appeals": session.scalar(select(func.count()).select_from(Appeal)), "pending_appeals": session.scalar(select(func.count()).select_from(Appeal).where(Appeal.analysis_status.not_in(["analyzed", "review_required"]))) }

    @router.post("/analysis/run")
    def run_analysis(payload: RunRequest = RunRequest()):
        return perform_run(payload.mode)

    @router.post("/analysis/runs/{run_id}/retry")
    def retry_analysis(run_id: str, payload: RunRequest | None = None):
        with session_factory() as session:
            old_run = session.get(AnalysisRun, run_id)
            if old_run is None:
                raise HTTPException(404, "Запуск анализа не найден.")
            mode = payload.mode if payload else old_run.mode
        # A retry always uses all current records and current manual overrides.
        return perform_run(mode, rerun_of=run_id)

    @router.get("/analysis/runs")
    def list_runs():
        with session_factory() as session:
            return [run_json(session, run) for run in session.scalars(select(AnalysisRun).order_by(AnalysisRun.created_at.desc(), AnalysisRun.id))]

    @router.get("/analysis/runs/{run_id}")
    def get_run(run_id: str):
        with session_factory() as session:
            return run_json(session, selected_run(session, run_id))

    @router.get("/analysis/results")
    def results(run_id: str | None = None):
        with session_factory() as session:
            run = selected_run(session, run_id)
            if run is None:
                return []
            return [result_json(session, result) for result in session.scalars(select(AppealAnalysis).where(AppealAnalysis.run_id == run.id).order_by(AppealAnalysis.appeal_id))]

    @router.get("/groups")
    def groups(run_id: str | None = None, kind: Literal["case", "problem"] | None = None):
        with session_factory() as session:
            run = selected_run(session, run_id)
            if run is None:
                return []
            query = select(AnalysisGroup).where(AnalysisGroup.run_id == run.id, AnalysisGroup.status != "archived")
            if kind:
                query = query.where(AnalysisGroup.kind == kind)
            return [group_json(session, group) for group in session.scalars(query.order_by(AnalysisGroup.kind, AnalysisGroup.group_key))]

    @router.get("/problems/{problem_id}")
    def problem(problem_id: str):
        with session_factory() as session:
            group = session.get(AnalysisGroup, problem_id)
            if group is None or group.kind != "problem":
                raise HTTPException(404, "Проблема не найдена.")
            return group_json(session, group)

    @router.get("/groups/{group_id}/appeals")
    def group_appeals(group_id: str):
        with session_factory() as session:
            group = session.get(AnalysisGroup, group_id)
            if group is None:
                raise HTTPException(404, "Группа не найдена.")
            items = session.scalars(select(Appeal).join(GroupMembership, GroupMembership.appeal_id == Appeal.id).where(GroupMembership.group_id == group_id).order_by(Appeal.date, Appeal.id)).all()
            output = []
            for appeal in items:
                result = session.scalar(select(AppealAnalysis).where(AppealAnalysis.run_id == group.run_id, AppealAnalysis.appeal_id == appeal.id))
                analysis = result_json(session, result)
                output.append(analysis | {field: getattr(appeal, field) for field in ("id", "source", "source_record_id", "text", "address", "date", "language", "privacy_status", "analysis_status", "warnings")} | {"appeal_id": appeal.id, "appeal_version": appeal.version, "created_at": timestamp(appeal.created_at), "analysis": analysis})
            return output

    @router.get("/analysis/issues")
    def issues(run_id: str | None = None):
        with session_factory() as session:
            run = selected_run(session, run_id)
            if run is None:
                return []
            output = list(run.errors)
            for result in session.scalars(select(AppealAnalysis).where(AppealAnalysis.run_id == run.id)):
                if result.status == "blocked":
                    output.append({"appeal_id": result.appeal_id, "kind": "privacy", "message": "Обезличивание требует ручной проверки; обращение не участвовало в анализе и группировке."})
                output.extend({"appeal_id": result.appeal_id, "kind": "uncertainty", "message": item} for item in result.data.get("uncertainties", []))
            if stale_run(session, run):
                output.append({"kind": "stale", "message": "После запуска изменились исходные записи или ручные категории. Для актуальных групп повторите анализ."})
            return output

    @router.patch("/appeals/{appeal_id}/category")
    def set_category(appeal_id: str, payload: CategoryRequest):
        if payload.category not in categories():
            raise HTTPException(422, "Выберите категорию из справочника.")
        with session_factory() as session:
            session.execute(sql_text("BEGIN IMMEDIATE"))
            appeal = session.get(Appeal, appeal_id)
            if appeal is None:
                raise HTTPException(404, "Обращение не найдено.")
            override = session.get(CategoryOverride, appeal_id)
            old_version = override.version if override else 0
            if payload.version != old_version + 1:
                raise HTTPException(409, "Категория уже изменена. Обновите результаты и повторите правку.")
            previous_result = session.scalar(select(AppealAnalysis).join(AnalysisRun).where(AppealAnalysis.appeal_id == appeal_id).order_by(AnalysisRun.created_at.desc()).limit(1))
            previous_category = override.category if override else previous_result.category if previous_result else None
            reason = mask(payload.reason).text
            new_version = old_version + 1
            if override:
                override.category = payload.category
                override.version = new_version
                override.reason = reason
                override.updated_at = utcnow()
            else:
                session.add(CategoryOverride(appeal_id=appeal_id, category=payload.category, version=new_version, reason=reason))
            session.add(CategoryAudit(id=str(uuid4()), appeal_id=appeal_id, previous_category=previous_category, category=payload.category, version=new_version, reason=reason))
            appeal.analysis_status = "pending"
            session.commit()
            return {"category": payload.category, "version": new_version + 1, "requires_reanalysis": True}

    return router
