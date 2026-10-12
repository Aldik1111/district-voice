"""Dashboard/read models and versioned analyst decisions over existing analysis tables."""
from collections import Counter
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import ConfigDict, Field
from sqlalchemy import func, or_, select, text as sql_text

from .ai.normalization import CATEGORIES
from .analysis_api import group_json, result_json, run_json, selected_run, stale_run, timestamp
from .analysis_models import AnalysisGroup, AnalysisRun, AppealAnalysis, CategoryOverride, GroupMembership, ProblemCase
from .models import Appeal, utcnow
from .privacy import mask
from .input_validation import SafeInputModel
from .group_actions import editable_group, audit_group, public_state


class GroupDecision(SafeInputModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    status: Literal["confirmed", "rejected", "proposed"]
    version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)


def dashboard_data(session, run=None, historical=False):
    total = session.scalar(select(func.count()).select_from(Appeal))
    dates = list(session.execute(select(Appeal.date, func.count()).group_by(Appeal.date).order_by(Appeal.date)))
    results = list(session.scalars(select(AppealAnalysis).where(AppealAnalysis.run_id == run.id))) if run else []
    if historical and run:
        total = run.total
        dates = sorted(Counter(item.appeal_snapshot["date"] for item in results).items())
    groups = list(session.scalars(select(AnalysisGroup).where(AnalysisGroup.run_id == run.id, AnalysisGroup.status != "archived"))) if run else []
    eligible = [item for item in results if item.status != "blocked"]
    category_counts = Counter(item.category for item in eligible)
    if run:
        territories = Counter(item.data.get("territory") or "Территория неизвестна" for item in eligible)
    else:
        territories = Counter()
        for address, count in session.execute(select(Appeal.address, func.count()).group_by(Appeal.address)):
            territories[address or "Территория неизвестна"] += count
    categories = [{"name": name, "count": count, "percent": round(count / len(eligible) * 100, 1)} for name, count in category_counts.most_common()]
    top_territories = [{"name": name, "count": count, "percent": round(count / (len(eligible) if run else total) * 100, 1)} for name, count in territories.most_common(6)]
    ordered = sorted(groups, key=lambda group: (group.data["end_date"], group.data["message_count"], group.id), reverse=True)
    return {
        "total_appeals": total,
        "synthetic_appeals": sum(item.appeal_snapshot["source"].startswith("ДЕМО ·") for item in results) if historical else session.scalar(select(func.count()).select_from(Appeal).where(Appeal.source.startswith("ДЕМО ·"))),
        "unique_appeals": sum(item.data.get("duplicate_of") is None for item in eligible) if run else None,
        "republications": sum(item.data.get("duplicate_of") is not None for item in eligible) if run else None,
        "analysis_total": len(results), "analyzed": len(eligible),
        "groups_count": len(groups) if run else None,
        "pending_review": sum(group.status == "proposed" for group in groups) if run else None,
        "confirmed_groups": sum(group.status == "confirmed" for group in groups),
        "rejected_groups": sum(group.status == "rejected" for group in groups),
        "case_count": sum(group.kind == "case" for group in groups),
        "problem_count": sum(group.kind == "problem" for group in groups),
        "privacy_review": sum(item.appeal_snapshot["privacy_status"] == "review_required" for item in results) if historical else session.scalar(select(func.count()).select_from(Appeal).where(Appeal.privacy_status == "review_required")),
        "period": {"start": dates[0][0], "end": dates[-1][0]} if dates else None,
        "by_date": [{"date": day, "count": count} for day, count in dates],
        "by_category": categories, "by_territory": top_territories,
        "latest_groups": [group_json(session, group) for group in ordered[:5]],
        "latest_problems": [group_json(session, group) for group in ordered if group.kind == "problem"][:4],
        "run": run_json(session, run) if run else None,
    }


def build_workspace_router(session_factory, appeal_serializer):
    router = APIRouter(prefix="/api")

    @router.get("/dashboard")
    def dashboard(run_id: str | None = None):
        with session_factory() as session:
            return dashboard_data(session, selected_run(session, run_id))

    @router.get("/registry")
    def registry(q: str = Query(default="", max_length=200), category: str | None = None,
                 source: str | None = None, analysis_status: str | None = None,
                 privacy_status: Literal["clear", "masked", "review_required"] | None = None,
                 page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100)):
        with session_factory() as session:
            run = selected_run(session, None)
            run_id = run.id if run else ""
            effective_category = func.coalesce(CategoryOverride.category, AppealAnalysis.category)
            query = select(Appeal, AppealAnalysis, CategoryOverride).outerjoin(
                AppealAnalysis, (AppealAnalysis.appeal_id == Appeal.id) & (AppealAnalysis.run_id == run_id)
            ).outerjoin(CategoryOverride, CategoryOverride.appeal_id == Appeal.id)
            if q.strip():
                value = q.strip().casefold()
                query = query.where(or_(*(func.casefold(column).contains(value, autoescape=True) for column in (Appeal.id, Appeal.text, Appeal.address, Appeal.source_record_id, Appeal.source))))
            if category:
                if category not in CATEGORIES:
                    raise HTTPException(422, "Неизвестная категория.")
                query = query.where(effective_category == category)
            if source:
                query = query.where(Appeal.source == source)
            if analysis_status:
                query = query.where(Appeal.analysis_status == analysis_status)
            if privacy_status:
                query = query.where(Appeal.privacy_status == privacy_status)
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            rows = session.execute(query.order_by(Appeal.date.desc(), Appeal.id).offset((page - 1) * page_size).limit(page_size)).all()
            ids = [appeal.id for appeal, _, _ in rows]
            membership = {}
            if ids and run:
                for appeal_id, group in session.execute(select(GroupMembership.appeal_id, AnalysisGroup).join(AnalysisGroup).where(AnalysisGroup.run_id == run.id, AnalysisGroup.status != "archived", GroupMembership.appeal_id.in_(ids))):
                    membership.setdefault(appeal_id, []).append({"id": group.id, "kind": group.kind, "category": group.data["category"], "status": group.status})
            items = []
            for appeal, result, override in rows:
                items.append(appeal_serializer(appeal) | {
                    "category": override.category if override else result.category if result else None,
                    "classification_method": "manual_override" if override else result.data.get("classification_method") if result else None,
                    "requires_reanalysis": bool(result and (appeal.version != result.input_version or (override.version if override else 0) != result.input_override_version)),
                    "groups": membership.get(appeal.id, []),
                })
            return {"items": items, "total": total, "page": page, "page_size": page_size,
                    "categories": CATEGORIES, "sources": list(session.scalars(select(Appeal.source).distinct().order_by(Appeal.source))),
                    "run": run_json(session, run) if run else None}

    @router.get("/groups/{group_id}")
    def get_group(group_id: str):
        with session_factory() as session:
            group = session.get(AnalysisGroup, group_id)
            if group is None:
                raise HTTPException(404, "Группа не найдена.")
            return group_json(session, group)

    @router.patch("/groups/{group_id}/review")
    def review_group(group_id: str, payload: GroupDecision):
        with session_factory() as session:
            session.execute(sql_text("BEGIN IMMEDIATE"))
            group = editable_group(session, group_id, payload.version)
            if payload.status == "confirmed" and not group.data.get("message_count"):
                raise HTTPException(422, "Пустую группу нельзя подтвердить.")
            if payload.status == "confirmed" and group.kind == "problem":
                rejected_cases = session.scalars(select(AnalysisGroup).join(ProblemCase, ProblemCase.case_id == AnalysisGroup.id).where(ProblemCase.problem_id == group.id, AnalysisGroup.status == "rejected"))
                if any(item.data.get("message_count") for item in rejected_cases):
                    raise HTTPException(409, "В проблеме есть отклонённый случай. Проверьте его решение или исключите неподтверждённые обращения перед утверждением проблемы.")
            if mask(payload.reason).text != payload.reason:
                raise HTTPException(422, "Уберите персональные сведения из комментария аналитика.")
            before = public_state(session, group)
            group.status = payload.status
            audit_group(session, group, "review", payload.reason, before)
            if group.kind == "case" and before["status"] != group.status:
                # A changed evidence decision invalidates approval of every active parent.
                # Keep memberships intact: rejecting a case must not delete its appeals.
                parents = session.scalars(select(AnalysisGroup).join(ProblemCase, ProblemCase.problem_id == AnalysisGroup.id).where(ProblemCase.case_id == group.id, AnalysisGroup.status != "archived"))
                for parent in parents:
                    parent_before = public_state(session, parent)
                    parent.status = "proposed" if parent.data.get("message_count") else "rejected"
                    warning = "Решение по связанному случаю изменено; повторно проверьте основания проблемы."
                    parent.data = parent.data | {"explanation_stale": True, "uncertainties": list(dict.fromkeys([*parent.data.get("uncertainties", []), warning]))}
                    audit_group(session, parent, "related_review", payload.reason, parent_before)
            session.commit()
            return group_json(session, group)

    @router.get("/reports/{run_id}")
    def report(run_id: str, download: bool = False):
        with session_factory() as session:
            run = selected_run(session, run_id)
            if run.status != "completed":
                raise HTTPException(409, "Отчёт доступен только для завершённого анализа.")
            groups = list(session.scalars(select(AnalysisGroup).where(AnalysisGroup.run_id == run.id).order_by(AnalysisGroup.kind, AnalysisGroup.group_key)))
            content = {"report_type": "analysis_snapshot", "approved_summary": False,
                    "notice": "Рабочий снимок анализа. Не является утверждённой аналитической сводкой. Независимость авторов не установлена.",
                    "generated_at": timestamp(utcnow()), "summary": dashboard_data(session, run, historical=True),
                    "groups": [group_json(session, group) for group in groups],
                    "appeals": [result_json(session, result) for result in session.scalars(select(AppealAnalysis).where(AppealAnalysis.run_id == run.id).order_by(AppealAnalysis.appeal_id))]}
            if download:
                return JSONResponse(content, headers={"Content-Disposition": f'attachment; filename="district-voice-{run.id[:8]}.json"'})
            return content

    return router
