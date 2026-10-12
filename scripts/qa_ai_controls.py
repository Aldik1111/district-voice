"""Run independent synthetic controls through real import/SQLite/analysis APIs.

From the repository root: backend/.venv/Scripts/python.exe scripts/qa_ai_controls.py --output work/qa-ai.json
Uses separate SQLite files next to the report; never touches the working dataset.
External socket connections are forbidden, including during actual E5 loading.
"""
import argparse
import csv
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend" / "tests")]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=["auto", "tfidf"], default="auto")
    args = parser.parse_args()
    folder = args.output.resolve().parent / ("qa-ai-" + str(uuid4())[:8])
    folder.mkdir(parents=True)
    os.environ["DISTRICT_VOICE_DATABASE_URL"] = "sqlite:///" + (folder / "bootstrap.sqlite3").as_posix()
    from fastapi.testclient import TestClient
    from app.main import create_app
    from test_analysis_controls import CONTROLS, appeal, assess_control
    controls = [*CONTROLS, {"id": "I", "title": "Смешанный русский и казахский текст",
        "records": [appeal("I1", "На улице Абая 15 отключили воду."), appeal("I2", "Абай көшесі 15 үйде су жоқ, холодная вода отключена.")],
        "expected": {"case_members": [["I1", "I2"]], "recurring_problem_count": 0, "categories": {"I1": "Водоснабжение", "I2": "Водоснабжение"}}}]
    rows, attempts = [], []
    def external_guard(original):
        def connect(sock, address, *args, **kwargs):
            # Windows asyncio uses a loopback socketpair to wake its own event loop.
            if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
                return original(sock, address, *args, **kwargs)
            attempts.append("external socket connection")
            raise RuntimeError("External network forbidden by QA control")
        return connect
    with patch.object(socket.socket, "connect", external_guard(socket.socket.connect)), patch.object(socket.socket, "connect_ex", external_guard(socket.socket.connect_ex)):
        for control in controls:
            db = folder / (control["id"] + ".sqlite3")
            url = "sqlite:///" + db.as_posix()
            with TestClient(create_app(url)) as client:
                data = io.StringIO(newline="")
                fields = ["source", "source_record_id", "date", "text", "address"]
                writer = csv.DictWriter(data, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(control["records"])
                preview = client.post("/api/imports/preview", files={"file": ("synthetic.csv", data.getvalue().encode("utf-8-sig"))})
                preview.raise_for_status()
                imported = client.post("/api/imports/confirm", json={"preview_id": preview.json()["preview_id"]})
                assert imported.json()["accepted"] == len(control["records"])
                saved = client.get("/api/appeals").json()["items"]
                mapping = {item["id"]: item["source_record_id"] for item in saved}
                response = client.post("/api/analysis/run", json={"mode": args.mode})
                response.raise_for_status()
                run = response.json()
                assert run["status"] == "completed", run
                original_groups = client.get("/api/groups").json()
                original_results = client.get("/api/analysis/results").json()
                groups = [{**item, "appeal_ids": [mapping[value] for value in item["appeal_ids"]]} for item in original_groups]
                results = [{**item, "appeal_id": mapping[item["appeal_id"]]} for item in original_results]
                output = {"cases": [item for item in groups if item["kind"] == "case"], "problems": [item for item in groups if item["kind"] == "problem"], "results": results}
                actual, failures = assess_control(control, output)
                for group in original_groups:
                    evidence = client.get(f"/api/groups/{group['id']}/appeals").json()
                    assert {item["id"] for item in evidence} == set(group["appeal_ids"])
                    assert group["message_count"] == len(evidence)
                    assert group["source_count"] == len({item["source"] for item in evidence})
                    assert all(item["id"] in mapping for item in evidence)
                if args.mode == "auto" and run["algorithm"]["name"] != "multilingual-e5-small":
                    failures.append("Actual E5 model did not run")
                retried = client.post(f"/api/analysis/runs/{run['id']}/retry").json()
                assert retried["status"] == "completed" and retried["rerun_of"] == run["id"]
                assert client.get("/api/appeals").json()["total"] == len(mapping)
                assert client.get("/api/groups", params={"run_id": run["id"]}).json() == original_groups
            with TestClient(create_app(url)) as restarted:
                assert restarted.get("/api/analysis/results", params={"run_id": run["id"]}).json() == original_results
            with sqlite3.connect(db) as connection:
                assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                assert not connection.execute("PRAGMA foreign_key_check").fetchall()
                assert connection.execute("SELECT count(*) FROM appeals").fetchone()[0] == len(mapping)
            rows.append({"id": control["id"], "title": control["title"], "expected": control["expected"], "actual": actual, "failures": failures, "passed": not failures, "run": run, "evidence_ids": mapping, "sqlite_persistence_retry": "PASS"})
    report = {"dataset": "Synthetic A-I, not a real-world accuracy benchmark", "mode": args.mode, "network_attempts": attempts, "total": len(rows), "passed": sum(row["passed"] for row in rows), "controls": rows}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{report['passed']}/{report['total']} API/SQLite controls passed; network attempts: {len(attempts)}")
    return 0 if report["passed"] == report["total"] and not attempts else 1


if __name__ == "__main__":
    raise SystemExit(main())
