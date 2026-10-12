"""Isolated API integration fixtures: every test gets its own on-disk SQLite DB."""

import csv
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'test.sqlite3').as_posix()}"


@pytest.fixture
def client(database_url):
    with TestClient(create_app(database_url=database_url)) as test_client:
        yield test_client


@pytest.fixture
def valid_record():
    return {
        "source_record_id": "KZ-001",
        "source": "Городской портал",
        "date": "2026-10-01",
        "text": "На улице Абая третий день не работает освещение.",
        "address": "ул. Абая, 15",
    }


@pytest.fixture
def upload_csv():
    def upload(client, records, *, headers=None, mapping=None, bom=True, filename="appeals.csv"):
        columns = headers if headers is not None else list(records[0])
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        writer.writerows(records)
        data = output.getvalue().encode("utf-8-sig" if bom else "utf-8")
        form = {"mapping": json.dumps(mapping, ensure_ascii=False)} if mapping is not None else {}
        return client.post(
            "/api/imports/preview",
            files={"file": (filename, data, "text/csv")},
            data=form,
        )

    return upload


@pytest.fixture
def confirm():
    def confirm_preview(client, preview):
        assert preview.status_code == 200, preview.text
        response = client.post("/api/imports/confirm", json={"preview_id": preview.json()["preview_id"]})
        assert response.status_code == 200, response.text
        return response.json()

    return confirm_preview
