"""SQLite-backed analysis API tests, including history and evidence integrity."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import Appeal


def run_analysis(client, *, path="/api/analysis/run"):
    response = client.post(path, json={"mode": "tfidf"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "completed", result
    return result


def import_water(client, valid_record, upload_csv, confirm, *, recurring=False):
    first = {**valid_record, "text": "На улице Абая 15 отключили холодную воду.", "date": "2026-09-01"}
    second = {**first, "source_record_id": "KZ-002", "text": "На улице Абая 15 нет холодной воды.", "date": "2026-10-01" if recurring else "2026-09-01"}
    confirmed = confirm(client, upload_csv(client, [first, second]))
    assert confirmed["accepted"] == 2
    return [first, second]


def test_analysis_requires_import_and_rejects_unknown_run(client):
    assert client.post("/api/analysis/run", json={"mode": "tfidf"}).status_code == 422
    assert client.get("/api/analysis/results").json() == []
    assert client.get("/api/analysis/runs/missing").status_code == 404
    assert client.post("/api/analysis/runs/missing/retry", json={"mode": "tfidf"}).status_code == 404


def test_results_groups_and_real_evidence_survive_new_application(client, database_url, valid_record, upload_csv, confirm):
    import_water(client, valid_record, upload_csv, confirm, recurring=True)
    run = run_analysis(client)
    results = client.get("/api/analysis/results").json()
    groups = client.get("/api/groups").json()
    assert len(results) == run["analyzed"] == 2
    assert run["case_count"] == 2
    assert run["problem_count"] == 1
    assert len(groups) == 3
    appeal_ids = {row["id"] for row in client.get("/api/appeals").json()["items"]}
    case_ids = {group["id"] for group in groups if group["kind"] == "case"}
    problem = next(group for group in groups if group["kind"] == "problem")
    assert set(problem["case_ids"]) == case_ids
    assert set(problem["appeal_ids"]) == appeal_ids
    assert client.get(f"/api/problems/{problem['id']}").json() == problem
    for group in groups:
        evidence = client.get(f"/api/groups/{group['id']}/appeals").json()
        assert {row["appeal_id"] for row in evidence} == set(group["appeal_ids"])
        assert all(row["analysis"]["run_id"] == run["id"] for row in evidence)
    with sqlite3.connect(database_url.removeprefix("sqlite:///")) as database:
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []
    with TestClient(create_app(database_url=database_url)) as restarted:
        assert restarted.get("/api/analysis/results").json() == results
        assert restarted.get("/api/groups").json() == groups
        assert restarted.get(f"/api/analysis/runs/{run['id']}").json()["status"] == "completed"


def test_retry_preserves_prior_results_and_does_not_duplicate_appeals(client, valid_record, upload_csv, confirm):
    import_water(client, valid_record, upload_csv, confirm)
    first = run_analysis(client)
    original_results = client.get("/api/analysis/results", params={"run_id": first["id"]}).json()
    original_groups = client.get("/api/groups", params={"run_id": first["id"]}).json()
    second = run_analysis(client, path=f"/api/analysis/runs/{first['id']}/retry")
    assert second["id"] != first["id"]
    assert second["rerun_of"] == first["id"]
    assert client.get("/api/analysis/results", params={"run_id": first["id"]}).json() == original_results
    assert client.get("/api/groups", params={"run_id": first["id"]}).json() == original_groups
    assert len(client.get("/api/analysis/runs").json()) == 2
    assert client.get("/api/appeals").json()["total"] == 2


def test_technical_duplicate_vs_republication_have_distinct_counts(client, valid_record, upload_csv, confirm):
    record = {**valid_record, "text": "На улице Абая 15 отключили холодную воду."}
    assert confirm(client, upload_csv(client, [record]))["accepted"] == 1
    assert confirm(client, upload_csv(client, [record]))["duplicates"] == 1
    copy = {**record, "source_record_id": "REPOST-002"}
    assert confirm(client, upload_csv(client, [copy]))["accepted"] == 1
    run_analysis(client)
    assert client.get("/api/stats").json()["total_appeals"] == 2
    results = client.get("/api/analysis/results").json()
    assert sorted(result["duplicate_kind"] for result in results) == ["independent", "republication_candidate"]
    cases = client.get("/api/groups", params={"kind": "case"}).json()
    assert len(cases) == 1
    assert cases[0]["message_count"] == 2
    assert cases[0]["independent_evidence_count"] == 1


def test_manual_category_is_versioned_and_survives_retry_and_restart(client, database_url, valid_record, upload_csv, confirm):
    import_water(client, valid_record, upload_csv, confirm)
    first = run_analysis(client)
    result = client.get("/api/analysis/results").json()[0]
    categories = client.get("/api/analysis/status").json()["categories"]
    replacement = next(category for category in categories if category != result["category"])
    path = f"/api/appeals/{result['appeal_id']}/category"
    change = {"category": replacement, "version": result["version"], "reason": "Сверено аналитиком с описанием"}
    response = client.patch(path, json=change)
    assert response.status_code == 200, response.text
    assert response.json()["requires_reanalysis"] is True
    assert client.patch(path, json=change).status_code == 409
    old_result = next(row for row in client.get("/api/analysis/results", params={"run_id": first["id"]}).json() if row["appeal_id"] == result["appeal_id"])
    assert old_result["category"] == result["category"]
    assert old_result["override_category"] == replacement
    assert old_result["requires_reanalysis"] is True
    assert client.get(f"/api/analysis/runs/{first['id']}").json()["stale"] is True
    second = run_analysis(client, path=f"/api/analysis/runs/{first['id']}/retry")
    new_result = next(row for row in client.get("/api/analysis/results").json() if row["appeal_id"] == result["appeal_id"])
    assert new_result["category"] == replacement
    assert new_result["proposed_category"] == result["proposed_category"]
    assert new_result["requires_reanalysis"] is False
    assert second["stale"] is False
    with TestClient(create_app(database_url=database_url)) as restarted:
        saved = next(row for row in restarted.get("/api/analysis/results").json() if row["appeal_id"] == result["appeal_id"])
        assert saved["category"] == saved["override_category"] == replacement


def test_records_requiring_privacy_review_cannot_be_group_evidence(client, valid_record, upload_csv, confirm):
    record = {**valid_record, "text": "Меня зовут Иванов Иван Иванович, нет воды.", "address": "ул. Абая, 15, кв. 42"}
    confirm(client, upload_csv(client, [record]))
    assert client.get("/api/appeals").json()["items"][0]["privacy_status"] == "review_required"
    run = run_analysis(client)
    assert run["blocked"] == 1
    assert run["analyzed"] == 0
    assert client.get("/api/analysis/results").json()[0]["status"] == "blocked"
    assert client.get("/api/groups").json() == []
    assert any(issue["kind"] == "privacy" for issue in client.get("/api/analysis/issues").json())


def test_failed_run_does_not_erase_previous_results_or_expose_exception(client, valid_record, upload_csv, confirm, monkeypatch):
    from app.ai import engine

    import_water(client, valid_record, upload_csv, confirm)
    first = run_analysis(client)
    results = client.get("/api/analysis/results").json()
    original_analyze = engine.analyze

    def fail_with_private_exception(_records, mode="auto"):
        raise RuntimeError("private.exception@example.kz is unavailable")

    monkeypatch.setattr(engine, "analyze", fail_with_private_exception)
    response = client.post("/api/analysis/run", json={"mode": "tfidf"})
    assert response.status_code == 200, response.text
    failed = response.json()
    assert failed["status"] == "failed"
    assert failed["error_count"] >= 1
    assert "private.exception@example.kz" not in json.dumps(failed)
    assert client.get("/api/analysis/results").json() == results
    assert client.get("/api/analysis/results", params={"run_id": failed["id"]}).json() == []
    assert client.get(f"/api/analysis/runs/{first['id']}").json()["status"] == "completed"
    monkeypatch.setattr(engine, "analyze", original_analyze)
    assert run_analysis(client, path=f"/api/analysis/runs/{failed['id']}/retry")["rerun_of"] == failed["id"]


@pytest.mark.parametrize("mutation", ["appeal_version", "override_version"])
def test_change_during_analysis_aborts_snapshot_without_partial_results(client, valid_record, upload_csv, confirm, monkeypatch, mutation):
    from app.ai import engine
    from app.analysis_models import CategoryOverride

    import_water(client, valid_record, upload_csv, confirm)
    first = run_analysis(client)
    original_analyze = engine.analyze

    def edit_during_analysis(records, mode="auto"):
        with client.app.state.session_factory.begin() as session:
            record = session.scalar(select(Appeal).order_by(Appeal.id))
            if mutation == "appeal_version":
                record.version += 1
                record.text = "Исправлено оператором: холодная вода отключена."
            else:
                session.add(CategoryOverride(appeal_id=record.id, category=next(iter(engine.CATEGORIES)), version=1, reason="Параллельная правка аналитика"))
        return original_analyze(records, mode=mode)

    monkeypatch.setattr(engine, "analyze", edit_during_analysis)
    response = client.post("/api/analysis/run", json={"mode": "tfidf"})
    assert response.status_code == 200, response.text
    failed = response.json()
    assert failed["status"] == "failed"
    assert failed["stale"] is True
    assert any(error["kind"] == "stale_snapshot" for error in failed["errors"])
    assert client.get("/api/analysis/results", params={"run_id": failed["id"]}).json() == []
    assert client.get("/api/groups", params={"run_id": failed["id"]}).json() == []
    assert len(client.get("/api/analysis/results", params={"run_id": first["id"]}).json()) == 2


def test_invalid_evidence_reference_is_not_persisted(client, valid_record, upload_csv, confirm, monkeypatch):
    from app.ai import engine

    import_water(client, valid_record, upload_csv, confirm)
    original_analyze = engine.analyze

    def invented_evidence(records, mode="auto"):
        output = original_analyze(records, mode=mode)
        output["cases"][0]["appeal_ids"].append("nonexistent-appeal")
        return output

    monkeypatch.setattr(engine, "analyze", invented_evidence)
    response = client.post("/api/analysis/run", json={"mode": "tfidf"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "failed"
    assert client.get("/api/analysis/results").json() == []
    assert client.get("/api/groups").json() == []


def test_concurrent_run_from_second_app_is_rejected_without_recovering_live_run(client, database_url, valid_record, upload_csv, confirm, monkeypatch):
    from app.ai import engine

    import_water(client, valid_record, upload_csv, confirm)
    original_analyze = engine.analyze
    started, release = Event(), Event()

    def delayed_analysis(records, mode="auto"):
        started.set()
        assert release.wait(timeout=15), "Test did not release the analysis worker"
        return original_analyze(records, mode=mode)

    monkeypatch.setattr(engine, "analyze", delayed_analysis)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(client.post, "/api/analysis/run", json={"mode": "tfidf"})
        try:
            assert started.wait(timeout=10)
            with TestClient(create_app(database_url=database_url)) as second_client:
                response = second_client.post("/api/analysis/run", json={"mode": "tfidf"})
                assert response.status_code == 409, response.text
                runs = second_client.get("/api/analysis/runs").json()
                assert len(runs) == 1
                assert runs[0]["status"] == "running"
        finally:
            release.set()
        assert future.result(timeout=20).json()["status"] == "completed"


def test_startup_marks_interrupted_run_failed_and_allows_retry(client, database_url, valid_record, upload_csv, confirm):
    from app.analysis_models import AnalysisRun

    import_water(client, valid_record, upload_csv, confirm)
    with client.app.state.session_factory.begin() as session:
        session.add(AnalysisRun(id="interrupted-run", status="running", mode="tfidf", snapshot=[], total=2))
    with TestClient(create_app(database_url=database_url)) as restarted:
        recovered = restarted.get("/api/analysis/runs/interrupted-run").json()
        assert recovered["status"] == "failed"
        assert recovered["error_count"] >= 1
        assert run_analysis(restarted, path="/api/analysis/runs/interrupted-run/retry")["rerun_of"] == "interrupted-run"
