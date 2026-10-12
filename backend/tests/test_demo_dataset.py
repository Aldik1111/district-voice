import csv
import io
import json
from pathlib import Path

from app.summary_api import safe_cell


def test_demo_import_matches_independent_gold_and_is_idempotent(client):
    root = Path(__file__).resolve().parents[2]
    content = (root / "data/demo-180.csv").read_bytes()
    assert content == (root / "frontend/public/demo-180.csv").read_bytes()
    gold = json.loads((root / "data/demo-180-gold.json").read_text(encoding="utf-8"))
    rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
    assert len(rows) == len(gold["rows"]) == 180
    assert sum(any(letter in row["text"] for letter in "әғқңөұүһі") for row in rows) >= 45
    assert all(row["source"].startswith("ДЕМО ·") for row in rows)
    first = client.post("/api/imports/preview", files={"file": ("demo.csv", content, "text/csv")})
    assert first.status_code == 200, first.text
    response = client.post("/api/imports/confirm", json={"preview_id": first.json()["preview_id"]})
    assert response.status_code == 200
    result = response.json()
    assert {key: result[key] for key in ("accepted", "rejected", "duplicates", "conflicts")} == {key: value for key, value in gold["expected_import"].items() if key != "rows"}
    second = client.post("/api/imports/preview", files={"file": ("demo.csv", content, "text/csv")})
    result = client.post("/api/imports/confirm", json={"preview_id": second.json()["preview_id"]}).json()
    assert (result["accepted"], result["rejected"], result["duplicates"]) == (0, 2, 178)
    records = [item for page in (1, 2) for item in client.get("/api/registry", params={"page": page, "page_size": 100}).json()["items"]]
    assert {item["source_record_id"] for item in records} == {key for ids in gold["cases"].values() for key in ids}
    assert len(records) == 176 and client.get("/api/dashboard").json()["synthetic_appeals"] == 176
    assert "SYN-021" in gold["cases"]["water-workshop"] and "SYN-021" not in gold["cases"]["water-main"]


def test_csv_formula_prefixes_are_literal_and_multiline_is_preserved():
    for value in ["=SUM(A1)", "+CMD", "-1+2", "@SUM(A1)", "   =1", "\t=1", "\r=1", "\n=1"]:
        assert safe_cell(value) == "'" + value
    assert safe_cell("Обычный текст\nҚазақша жол") == "Обычный текст\nҚазақша жол"
