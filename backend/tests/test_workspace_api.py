"""Live read models and analyst decisions, using isolated SQLite via the import API."""
from fastapi.testclient import TestClient
from app.main import create_app
from app.analysis_models import AnalysisRun


def seed(client, valid_record, upload_csv, confirm):
    first = {**valid_record, "date": "2026-09-01", "text": "На улице Абая 15 отключили холодную воду."}
    copy = {**first, "source_record_id": "COPY", "source": "Публичный портал"}
    later = {**first, "source_record_id": "LATER", "date": "2026-10-01", "text": "На улице Абая 15 нет холодной воды."}
    confirm(client, upload_csv(client, [first, copy, later]))
    response = client.post("/api/analysis/run", json={"mode": "tfidf"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    return response.json()


def test_empty_dashboard_has_no_fabricated_analysis(client):
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["total_appeals"] == 0
    assert data["unique_appeals"] is data["groups_count"] is data["pending_review"] is None
    assert data["by_date"] == data["by_category"] == data["by_territory"] == []
    assert data["period"] is data["run"] is None
    assert client.get("/api/registry").json()["items"] == []
    assert client.get("/api/groups/missing").status_code == 404
    assert client.get("/api/reports/missing").status_code == 404


def test_dashboard_counts_match_sqlite_results_and_real_membership(client, valid_record, upload_csv, confirm):
    run = seed(client, valid_record, upload_csv, confirm)
    data = client.get("/api/dashboard").json()
    assert (data["total_appeals"], data["unique_appeals"], data["republications"]) == (3, 2, 1)
    assert (data["case_count"], data["problem_count"], data["groups_count"]) == (2, 1, 3)
    assert data["pending_review"] == 3
    assert data["by_date"] == [{"date": "2026-09-01", "count": 2}, {"date": "2026-10-01", "count": 1}]
    assert data["by_category"] == [{"name": "Водоснабжение", "count": 3, "percent": 100.0}]
    assert data["by_territory"][0]["count"] == 3
    assert len(data["latest_problems"]) == 1
    assert data["run"]["id"] == run["id"]
    ids = {item["id"] for item in client.get("/api/registry").json()["items"]}
    for group in data["latest_groups"]:
        assert set(group["appeal_ids"]) <= ids
        assert client.get(f"/api/groups/{group['id']}").json() == group


def test_registry_filters_pagination_and_current_override(client, valid_record, upload_csv, confirm):
    seed(client, valid_record, upload_csv, confirm)
    page = client.get("/api/registry", params={"category": "Водоснабжение", "page_size": 1}).json()
    assert page["total"] == 3 and len(page["items"]) == 1
    assert page["items"][0]["source_record_id"] == "LATER"
    next_page = client.get("/api/registry", params={"page": 2, "page_size": 1}).json()
    assert next_page["items"][0]["id"] != page["items"][0]["id"]
    assert client.get("/api/registry", params={"q": "АБАЯ"}).json()["total"] == 3
    assert client.get("/api/registry", params={"q": "does-not-exist"}).json()["total"] == 0
    assert client.get("/api/registry", params={"source": "Публичный портал"}).json()["total"] == 1
    assert client.get("/api/registry", params={"category": "Придуманная"}).status_code == 422
    assert client.get("/api/registry", params={"page_size": 101}).status_code == 422
    appeal_id = page["items"][0]["id"]
    assert client.get("/api/registry", params={"q": appeal_id}).json()["total"] == 1
    response = client.patch(f"/api/appeals/{appeal_id}/category", json={"category": "Другое", "version": 1, "reason": "Уточнение аналитика"})
    assert response.status_code == 200, response.text
    changed = client.get("/api/registry", params={"category": "Другое"}).json()
    assert changed["total"] == 1
    assert changed["items"][0]["requires_reanalysis"] is True
    assert changed["items"][0]["classification_method"] == "manual_override"
    assert changed["run"]["stale"] is True
    assert changed["items"][0]["groups"]


def test_review_is_versioned_reversible_and_persistent(client, database_url, valid_record, upload_csv, confirm):
    seed(client, valid_record, upload_csv, confirm)
    group = client.get("/api/groups").json()[0]
    path = f"/api/groups/{group['id']}/review"
    payload = {"status": "confirmed", "version": group["version"], "reason": "Территория и период проверены"}
    response = client.patch(path, json=payload)
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["status"] == "confirmed" and updated["version"] == 2
    assert updated["appeal_ids"] == group["appeal_ids"]
    assert updated["review_history"][0]["previous_status"] == "proposed"
    assert client.get("/api/dashboard").json()["confirmed_groups"] == 1
    assert client.get("/api/dashboard").json()["pending_review"] == 2
    assert client.patch(path, json=payload).status_code == 409
    assert client.patch(path, json={**payload, "version": 2, "reason": "Телефон +7 777 123 45 67"}).status_code == 422
    updated = client.patch(path, json={**payload, "version": 2, "status": "rejected"}).json()
    assert updated["status"] == "rejected"
    updated = client.patch(path, json={**payload, "version": 3, "status": "proposed"}).json()
    assert len(updated["review_history"]) == 3 and updated["version"] == 4
    with TestClient(create_app(database_url=database_url)) as restarted:
        assert restarted.get(f"/api/groups/{group['id']}").json() == updated
        assert restarted.get("/api/dashboard").json()["pending_review"] == 3


def test_historical_and_stale_groups_cannot_be_reviewed(client, valid_record, upload_csv, confirm):
    seed(client, valid_record, upload_csv, confirm)
    group = client.get("/api/groups").json()[0]
    client.post("/api/analysis/run", json={"mode": "tfidf"})
    payload = {"status": "confirmed", "version": 1, "reason": "Территория проверена"}
    assert client.patch(f"/api/groups/{group['id']}/review", json=payload).status_code == 409
    current = client.get("/api/groups").json()[0]
    confirm(client, upload_csv(client, [{**valid_record, "source_record_id": "NEW"}]))
    assert client.get(f"/api/groups/{current['id']}").json()["stale"] is True
    assert client.patch(f"/api/groups/{current['id']}/review", json=payload).status_code == 409


def test_report_snapshot_uses_run_dates_counts_and_evidence(client, valid_record, upload_csv, confirm):
    run = seed(client, valid_record, upload_csv, confirm)
    confirm(client, upload_csv(client, [{**valid_record, "source_record_id": "NEW", "date": "2026-12-01"}]))
    assert client.get("/api/dashboard").json()["total_appeals"] == 4
    response = client.get(f"/api/reports/{run['id']}")
    assert response.status_code == 200, response.text
    report = response.json()
    attachment = client.get(f"/api/reports/{run['id']}?download=true")
    assert attachment.status_code == 200
    assert attachment.headers["content-disposition"] == f'attachment; filename="district-voice-{run["id"][:8]}.json"'
    assert attachment.json()["groups"] == report["groups"]
    assert report["approved_summary"] is False
    assert report["summary"]["total_appeals"] == len(report["appeals"]) == 3
    assert report["summary"]["period"] == {"start": "2026-09-01", "end": "2026-10-01"}
    assert report["summary"]["run"]["stale"] is True
    ids = {item["appeal_id"] for item in report["appeals"]}
    for group in report["groups"]:
        assert set(group["appeal_ids"]) <= ids
    # Report method rejects failed/incomplete runs rather than inventing a report.
    with client.app.state.session_factory() as session:
        saved = session.get(AnalysisRun, run["id"])
        saved.status = "failed"
        session.commit()
    assert client.get(f"/api/reports/{run['id']}").status_code == 409


def test_missing_territory_is_never_invented(client, valid_record, upload_csv, confirm):
    confirm(client, upload_csv(client, [{**valid_record, "text": "Нет холодной воды.", "address": ""}]))
    client.post("/api/analysis/run", json={"mode": "tfidf"})
    dashboard = client.get("/api/dashboard").json()
    assert dashboard["by_territory"][0]["name"] == "Территория неизвестна"
    assert dashboard["latest_groups"][0]["territory"] is None
