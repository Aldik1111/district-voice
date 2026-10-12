"""Transactional manual curation of the existing case/problem graph."""
from copy import deepcopy
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import ConfigDict, Field
from sqlalchemy import delete, select, text as sql_text

from .ai.normalization import CATEGORIES
from .analysis_api import group_json, selected_run, stale_run, timestamp
from .analysis_models import AnalysisGroup, AnalysisRun, AppealAnalysis, GroupMembership, ProblemCase
from .models import utcnow
from .privacy import mask
from .input_validation import SafeInputModel

DEMO_ACTOR = "demo_operator"


class GroupAction(SafeInputModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    action: Literal["edit", "add", "remove", "split", "merge"]
    version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)
    title: str | None = Field(default=None, min_length=3, max_length=160)
    category: str | None = None
    appeal_ids: list[str] = Field(default_factory=list, max_length=500)
    case_ids: list[str] = Field(default_factory=list, max_length=500)
    case_id: str | None = None
    target_id: str | None = None
    target_version: int | None = Field(default=None, ge=1)


def editable_group(session, group_id, version):
    group = session.get(AnalysisGroup, group_id)
    if not group:
        raise HTTPException(404, "Группа не найдена.")
    latest = selected_run(session, None)
    if group.status == "archived" or not latest or latest.id != group.run_id or stale_run(session, latest):
        raise HTTPException(409, "Историческую, объединённую или устаревшую группу менять нельзя. Откройте актуальный анализ.")
    if session.scalar(select(AnalysisRun.id).where(AnalysisRun.status == "running").limit(1)):
        raise HTTPException(409, "Дождитесь завершения анализа перед ручной проверкой.")
    if version != group.version:
        raise HTTPException(409, "Группа уже изменена. Обновите карточку и повторите действие.")
    return group


def public_state(session, group):
    data = group_json(session, group)
    return {key: data.get(key) for key in ("title", "category", "status", "appeal_ids", "case_ids", "message_count", "source_count", "sources", "start_date", "end_date", "territory")}


def audit_group(session, group, action, reason, before):
    group.version += 1
    history = list(group.data.get("review_history", []))
    history.append({"action": action, "old_value": before, "new_value": public_state(session, group),
                    "previous_status": before["status"], "status": group.status, "reason": reason,
                    "created_at": timestamp(utcnow()), "version": group.version, "actor": DEMO_ACTOR})
    group.data = group.data | {"review_history": history}


def members(session, group):
    return set(session.scalars(select(GroupMembership.appeal_id).where(GroupMembership.group_id == group.id)))


def replace_members(session, group, ids):
    session.execute(delete(GroupMembership).where(GroupMembership.group_id == group.id))
    session.add_all(GroupMembership(group_id=group.id, appeal_id=value) for value in sorted(ids))
    session.flush()


def recompute(session, group):
    if group.kind == "problem":
        ids = set(session.scalars(select(GroupMembership.appeal_id).join(ProblemCase, ProblemCase.case_id == GroupMembership.group_id).where(ProblemCase.problem_id == group.id)))
        replace_members(session, group, ids)
    ids = members(session, group)
    results = list(session.scalars(select(AppealAnalysis).where(AppealAnalysis.run_id == group.run_id, AppealAnalysis.appeal_id.in_(ids))))
    dates = sorted(item.appeal_snapshot["date"] for item in results)
    sources = sorted({item.appeal_snapshot["source"] for item in results})
    territories = sorted({item.data["territory"] for item in results if item.data.get("territory")})
    unknown = any(not item.data.get("territory") for item in results)
    warnings = ["Состав или описание изменены демо-оператором. Основание AI и сходство устарели; требуется ручная проверка."]
    if len(territories) > 1 or unknown:
        warnings.append("Есть разные или неизвестные территории. Общий адрес не установлен.")
    if any(item.category != group.data["category"] for item in results):
        warnings.append("Категория группы отличается от категории части обращений. Классификация исходных записей сохранена.")
    if group.kind == "problem" and len(list(session.scalars(select(ProblemCase.case_id).where(ProblemCase.problem_id == group.id)))) < 2:
        warnings.append("Осталось меньше двух случаев: повторяемость требует проверки.")
    group.status = "proposed" if ids else "rejected"
    group.data = group.data | {
        "message_count": len(ids), "source_count": len(sources), "sources": sources,
        "independent_evidence_count": sum(item.data.get("duplicate_of") is None for item in results),
        "start_date": dates[0] if dates else "", "end_date": dates[-1] if dates else "",
        "territory": territories[0] if len(territories) == 1 and not unknown else None,
        "territories": territories, "minimum_similarity": None, "explanation_stale": True,
        "explanations": ["Текущий состав установлен вручную; подтверждающие ID, даты и источники пересчитаны из SQLite."],
        "uncertainties": list(dict.fromkeys(warnings + [warning for item in results for warning in item.data.get("uncertainties", [])])),
    }


def new_group(session, original):
    group = AnalysisGroup(id=str(uuid4()), run_id=original.run_id, kind=original.kind, group_key="manual:" + str(uuid4()),
                          status="proposed", version=1, data={"category": original.data["category"], "title": original.data.get("title", original.data["category"]) + " · выделенная группа"})
    session.add(group)
    session.flush()
    return group


def build_group_actions_router(session_factory):
    router = APIRouter(prefix="/api")

    @router.post("/groups/{group_id}/actions")
    def act(group_id: str, payload: GroupAction):
        if any(mask(value).text != value for value in [payload.reason, payload.title or ""]):
            raise HTTPException(422, "Уберите персональные сведения из названия и комментария.")
        if payload.category is not None and payload.category not in CATEGORIES:
            raise HTTPException(422, "Неизвестная категория.")
        with session_factory() as session:
            session.execute(sql_text("BEGIN IMMEDIATE"))
            group = editable_group(session, group_id, payload.version)
            touched = {}
            def touch(item):
                if item.id not in touched:
                    touched[item.id] = (item, deepcopy(public_state(session, item)))
            touch(group)
            created = None
            ids = set(payload.appeal_ids)
            if len(ids) != len(payload.appeal_ids) or len(set(payload.case_ids)) != len(payload.case_ids):
                raise HTTPException(422, "Список ID содержит повторы.")
            if payload.action == "edit":
                if payload.title is None and payload.category is None:
                    raise HTTPException(422, "Укажите название или категорию.")
                group.data = group.data | {key: value for key, value in {"title": payload.title, "category": payload.category}.items() if value is not None}
            elif payload.action in {"add", "remove"}:
                if not ids:
                    raise HTTPException(422, "Выберите хотя бы одно обращение.")
                results = list(session.scalars(select(AppealAnalysis).where(AppealAnalysis.run_id == group.run_id, AppealAnalysis.appeal_id.in_(ids))))
                if len(results) != len(ids) or any(item.status == "blocked" for item in results):
                    raise HTTPException(422, "ID должны принадлежать этому анализу и пройти проверку обезличивания.")
                if payload.action == "remove":
                    if not ids <= members(session, group):
                        raise HTTPException(422, "Часть обращений отсутствует в группе.")
                    cases = [group] if group.kind == "case" else list(session.scalars(select(AnalysisGroup).join(ProblemCase, ProblemCase.case_id == AnalysisGroup.id).where(ProblemCase.problem_id == group.id)))
                    for case in cases:
                        if members(session, case) & ids:
                            touch(case)
                            replace_members(session, case, members(session, case) - ids)
                else:
                    if group.kind == "case":
                        case = group
                    else:
                        link = session.get(ProblemCase, (group.id, payload.case_id)) if payload.case_id else None
                        if not link:
                            raise HTTPException(422, "Выберите связанный случай, в который нужно добавить обращение.")
                        case = session.get(AnalysisGroup, payload.case_id)
                    occupied = session.scalar(select(GroupMembership.appeal_id).join(AnalysisGroup).where(AnalysisGroup.run_id == group.run_id, AnalysisGroup.kind == "case", AnalysisGroup.status != "archived", GroupMembership.appeal_id.in_(ids)).limit(1))
                    if occupied:
                        raise HTTPException(409, "Обращение уже находится в активном случае. Сначала исключите его из прежнего случая либо объедините случаи.")
                    touch(case)
                    replace_members(session, case, members(session, case) | ids)
            elif payload.action == "split":
                chosen = ids if group.kind == "case" else set(payload.case_ids)
                existing = members(session, group) if group.kind == "case" else set(session.scalars(select(ProblemCase.case_id).where(ProblemCase.problem_id == group.id)))
                if not chosen or not chosen < existing:
                    raise HTTPException(422, "Выберите непустую часть группы. В исходной группе должно что-то остаться.")
                created = new_group(session, group)
                touch(created)
                if group.kind == "case":
                    replace_members(session, group, existing - chosen)
                    replace_members(session, created, chosen)
                    for parent in list(session.scalars(select(ProblemCase.problem_id).where(ProblemCase.case_id == group.id))):
                        touch(session.get(AnalysisGroup, parent))
                        session.add(ProblemCase(problem_id=parent, case_id=created.id))
                else:
                    for case_id in chosen:
                        session.delete(session.get(ProblemCase, (group.id, case_id)))
                        session.add(ProblemCase(problem_id=created.id, case_id=case_id))
            elif payload.action == "merge":
                other = editable_group(session, payload.target_id, payload.target_version)
                if other.id == group.id or other.kind != group.kind or other.run_id != group.run_id:
                    raise HTTPException(422, "Выберите другую группу того же типа из текущего анализа.")
                touch(other)
                if group.kind == "case":
                    replace_members(session, group, members(session, group) | members(session, other))
                    for link in list(session.scalars(select(ProblemCase).where(ProblemCase.case_id == other.id))):
                        parent = session.get(AnalysisGroup, link.problem_id)
                        if parent.status == "archived":
                            continue
                        touch(parent)
                        if not session.get(ProblemCase, (link.problem_id, group.id)):
                            session.add(ProblemCase(problem_id=link.problem_id, case_id=group.id))
                        session.delete(link)
                else:
                    for case_id in session.scalars(select(ProblemCase.case_id).where(ProblemCase.problem_id == other.id)):
                        if not session.get(ProblemCase, (group.id, case_id)):
                            session.add(ProblemCase(problem_id=group.id, case_id=case_id))
                other.status = "archived"
                other.data = other.data | {"merged_into": group.id}
            session.flush()
            # Every active parent is a union of its cases, never a disconnected list of IDs.
            for item, _ in list(touched.values()):
                if item.kind == "case":
                    for parent in session.scalars(select(AnalysisGroup).join(ProblemCase, ProblemCase.problem_id == AnalysisGroup.id).where(ProblemCase.case_id == item.id, AnalysisGroup.status != "archived")):
                        touch(parent)
            for item, _ in sorted(touched.values(), key=lambda pair: pair[0].kind == "problem"):
                if item.status != "archived":
                    recompute(session, item)
            for item, before in touched.values():
                audit_group(session, item, payload.action if item.id == group.id else "related_" + payload.action, payload.reason, before)
            session.commit()
            return {"group": group_json(session, group), "created_group": group_json(session, created) if created else None,
                    "changed_ids": list(touched)}

    return router
