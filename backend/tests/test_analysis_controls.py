"""Independent synthetic controls for grouping quality, with exportable actual results.

Run from backend: python tests/test_analysis_controls.py --report PATH
All texts are synthetic; no citizen data is used or downloaded by these tests.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
import numpy as np


def appeal(identifier, text, *, address="ул. Абая, 15", date="2026-09-01"):
    return {
        "id": identifier, "source_record_id": identifier, "source": "Синтетический контроль",
        "date": date, "text": text, "address": address, "privacy_status": "clear",
        "version": 1, "official_status": "Открыто", "language": "kk" if "су жоқ" in text else "ru",
    }


CONTROLS = [
    {
        "id": "A", "title": "Разные русские формулировки одного отключения воды",
        "records": [appeal("A1", "В доме третий день нет холодной воды."), appeal("A2", "Холодное водоснабжение отключено, из кранов ничего не идёт.")],
        "expected": {"case_members": [["A1", "A2"]], "recurring_problem_count": 0},
    },
    {
        "id": "B", "title": "Русский и казахский: одно отключение по одному адресу",
        "records": [appeal("B1", "На улице Абая 15 отключили воду."), appeal("B2", "Абай көшесі 15 үйде су жоқ.", address="Абай көшесі, 15")],
        "expected": {"case_members": [["B1", "B2"]], "recurring_problem_count": 0},
    },
    {
        "id": "C", "title": "Одна тема по разным адресам не доказывает одну аварию",
        "records": [appeal("C1", "В доме нет холодной воды."), appeal("C2", "В доме нет холодной воды.", address="ул. Абая, 27")],
        "expected": {"case_members": [["C1"], ["C2"]], "recurring_problem_count": 0},
    },
    {
        "id": "D", "title": "Вода и уличное освещение по одному адресу",
        "records": [appeal("D1", "В доме отключили холодную воду."), appeal("D2", "Уличные фонари не горят, во дворе совсем темно.")],
        "expected": {"case_members": [["D1"], ["D2"]], "recurring_problem_count": 0, "distinct_categories": 2},
    },
    {
        "id": "E", "title": "Отключения воды с интервалом месяц: два случая, одна повторяющаяся проблема",
        "records": [appeal("E1", "В доме нет воды, водоснабжение отключено."), appeal("E2", "В доме снова нет воды, водоснабжение отключено.", date="2026-10-01")],
        "expected": {"case_members": [["E1"], ["E2"]], "recurring_problem_count": 1},
    },
    {
        "id": "F", "title": "Дословная перепубликация не становится независимым доказательством",
        "records": [appeal("F1", "В доме нет холодной воды со вчерашнего дня."), appeal("F2", "В доме нет холодной воды со вчерашнего дня.")],
        "expected": {"case_members": [["F1", "F2"]], "recurring_problem_count": 0, "independent_evidence_count": 1, "republication_required": True},
    },
    {
        "id": "G", "title": "Неизвестные адреса: отдельные случаи и явная неопределённость",
        "records": [appeal("G1", "Нет холодной воды.", address="неизвестно"), appeal("G2", "Холодную воду отключили.", address="")],
        "expected": {"case_members": [["G1"], ["G2"]], "recurring_problem_count": 0, "uncertain_ids": ["G1", "G2"], "unknown_territory": True},
    },
    {
        "id": "H", "title": "Противоречащий адрес и восстановленная услуга не сливаются с отключением",
        "records": [
            appeal("H1", "В доме на улице Абая 15 нет воды."),
            appeal("H2", "На улице Абая 15 водоснабжение восстановлено, вода снова есть."),
            appeal("H3", "На улице Сейфуллина 88 нет воды, авария водоснабжения."),
        ],
        "expected": {"case_members": [["H1"], ["H2"], ["H3"]], "recurring_problem_count": 0, "uncertain_ids": ["H3"]},
    },
]

# Labels are specified independently from the engine's dictionaries or examples.
EXPECTED_CATEGORIES = {
    "A1": "Водоснабжение", "A2": "Водоснабжение",
    "B1": "Водоснабжение", "B2": "Водоснабжение",
    "C1": "Водоснабжение", "C2": "Водоснабжение",
    "D1": "Водоснабжение", "D2": "Освещение",
    "E1": "Водоснабжение", "E2": "Водоснабжение",
    "F1": "Водоснабжение", "F2": "Водоснабжение",
    "G1": "Водоснабжение", "G2": "Водоснабжение",
    "H1": "Водоснабжение", "H2": "Водоснабжение", "H3": "Водоснабжение",
}
for control in CONTROLS:
    control["expected"]["categories"] = {record["id"]: EXPECTED_CATEGORIES[record["id"]] for record in control["records"]}


def normalized_members(cases):
    return sorted(sorted(case["appeal_ids"]) for case in cases)


def assess_control(control, output):
    expected = control["expected"]
    actual = {
        "case_members": normalized_members(output["cases"]),
        "recurring_problem_count": len(output["problems"]),
        "distinct_categories": len({result["category"] for result in output["results"]}),
        "independent_evidence_count": sum(case["independent_evidence_count"] for case in output["cases"]),
        "republication_required": any(result["duplicate_kind"] == "republication_candidate" for result in output["results"]),
        "uncertain_ids": sorted(result["appeal_id"] for result in output["results"] if result["uncertainties"]),
        "territories": {result["appeal_id"]: result["territory"] for result in output["results"]},
        "categories": {result["appeal_id"]: result["category"] for result in output["results"]},
    }
    failures = []
    for key in ("case_members", "recurring_problem_count", "distinct_categories", "independent_evidence_count", "republication_required", "categories"):
        if key in expected and actual[key] != expected[key]:
            failures.append(f"{key}: expected {expected[key]!r}, got {actual[key]!r}")
    if not set(expected.get("uncertain_ids", [])).issubset(actual["uncertain_ids"]):
        failures.append("Missing required uncertainty flags")
    if expected.get("unknown_territory"):
        if any(value not in (None, "", "неизвестно", "unknown") for value in actual["territories"].values()):
            failures.append("Unknown address received a fabricated territory")
    evidence = {record["id"] for record in control["records"]}
    if {result["appeal_id"] for result in output["results"]} != evidence:
        failures.append("Result evidence IDs mismatch")
    if {identifier for case in output["cases"] for identifier in case["appeal_ids"]} != evidence:
        failures.append("Case evidence IDs mismatch")
    return actual, failures


@pytest.mark.parametrize("control", CONTROLS, ids=lambda control: control["id"])
def test_independent_labeled_controls(control):
    from app.ai.engine import analyze

    output = analyze(control["records"], mode="tfidf")
    actual, failures = assess_control(control, output)
    assert not failures, json.dumps({"control": control["id"], "failures": failures, "actual": actual}, ensure_ascii=False)


def test_time_chain_cannot_merge_events_spanning_more_than_three_days():
    from app.ai.engine import analyze

    records = [appeal(f"CHAIN-{day}", "В доме отключили холодную воду.", date=f"2026-09-{day:02d}") for day in (1, 3, 5)]
    output = analyze(records, mode="tfidf")
    assert len(output["cases"]) == 2
    assert output["problems"] == []
    record_map = {record["id"]: record for record in records}
    for case in output["cases"]:
        dates = [date.fromisoformat(record_map[identifier]["date"]) for identifier in case["appeal_ids"]]
        assert (max(dates) - min(dates)).days <= 3


def test_same_address_events_outside_recurrence_window_stay_separate():
    from app.ai.engine import analyze

    records = [appeal("OLD", "В доме отключили холодную воду.", date="2026-01-01"), appeal("NEW", "В доме отключили холодную воду.", date="2026-09-01")]
    output = analyze(records, mode="tfidf")
    assert normalized_members(output["cases"]) == [["NEW"], ["OLD"]]
    assert output["problems"] == []


def test_identical_republication_after_a_month_is_not_recurrence_evidence():
    from app.ai.engine import analyze

    text = "В доме на улице Абая 15 нет холодной воды со вчерашнего дня."
    records = [appeal("ORIGINAL", text, date="2026-09-01"), appeal("REPOST", text, date="2026-10-01")]
    output = analyze(records, mode="tfidf")
    assert normalized_members(output["cases"]) == [["ORIGINAL"], ["REPOST"]]
    assert output["problems"] == []
    results = {result["appeal_id"]: result for result in output["results"]}
    assert results["ORIGINAL"]["duplicate_kind"] == "independent"
    assert results["REPOST"]["duplicate_kind"] == "republication_candidate"
    assert results["REPOST"]["duplicate_of"] == "ORIGINAL"
    assert sum(case["independent_evidence_count"] for case in output["cases"]) == 1


def test_republication_window_is_measured_from_original_not_latest_copy():
    from app.ai.engine import analyze

    first_day = date(2026, 1, 1)
    records = [appeal(f"COPY-{offset:03d}", "В доме нет холодной воды со вчерашнего дня.", date=(first_day + timedelta(days=offset)).isoformat()) for offset in (0, 80, 160)]
    output = analyze(records, mode="tfidf")
    results = {result["appeal_id"]: result for result in output["results"]}
    assert results["COPY-000"]["duplicate_kind"] == "independent"
    assert results["COPY-080"]["duplicate_of"] == "COPY-000"
    assert results["COPY-160"]["duplicate_kind"] == "independent"
    assert results["COPY-160"]["duplicate_of"] is None


def test_numbered_microdistrict_is_not_a_precise_house_address():
    from app.ai.engine import analyze

    records = [appeal("DISTRICT-1", "Нет холодной воды.", address="мкр. 12"), appeal("DISTRICT-2", "Холодное водоснабжение отключено.", address="мкр. 12")]
    output = analyze(records, mode="tfidf")
    assert normalized_members(output["cases"]) == [["DISTRICT-1"], ["DISTRICT-2"]]
    assert all(result["uncertainties"] for result in output["results"])
    assert output["problems"] == []


def test_negated_outage_does_not_confirm_an_outage():
    from app.ai.engine import analyze

    records = [appeal("OUTAGE", "В доме отключили холодную воду."), appeal("NO-OUTAGE", "В доме холодную воду не отключали, аварии нет.")]
    output = analyze(records, mode="tfidf")
    assert normalized_members(output["cases"]) == [["NO-OUTAGE"], ["OUTAGE"]]
    assert next(result for result in output["results"] if result["appeal_id"] == "NO-OUTAGE")["uncertainties"]


def test_tfidf_does_not_call_network(monkeypatch):
    from app.ai.engine import analyze

    attempts = []

    def reject_network(_socket, address):
        attempts.append(address)
        raise AssertionError("Analysis must not call a network service")

    monkeypatch.setattr(socket.socket, "connect", reject_network)
    output = analyze(CONTROLS[0]["records"], mode="tfidf")
    assert output["results"]
    assert not attempts


def test_unavailable_embedding_model_falls_back_without_network_or_crash(monkeypatch):
    from app.ai import engine

    attempts = []

    def unavailable_model():
        raise RuntimeError("Unavailable model: private.model@example.kz")

    def reject_network(_socket, address):
        attempts.append(address)
        raise AssertionError("The fallback must not download a model")

    monkeypatch.setattr(engine, "_load_model", unavailable_model)
    monkeypatch.setattr(socket.socket, "connect", reject_network)
    output = engine.analyze(CONTROLS[0]["records"], mode="auto")
    assert len(output["results"]) == 2
    assert normalized_members(output["cases"]) == [["A1", "A2"]]
    assert "tf" in json.dumps(output["algorithm"], ensure_ascii=False).lower()
    assert "private.model@example.kz" not in json.dumps(output, ensure_ascii=False)
    assert not attempts


def test_privacy_blocked_and_detected_raw_personal_data_never_reach_vectors(monkeypatch):
    from app.ai import engine

    seen = []
    original_represent = engine._represent

    def inspect_vector_inputs(texts, mode):
        seen.extend(texts)
        return original_represent(texts, mode)

    allowed = appeal("SAFE", "В доме нет холодной воды.")
    review = {**appeal("REVIEW", "Вероятные личные сведения требуют проверки."), "privacy_status": "review_required"}
    raw = appeal("RAW", "Нет воды. private.resident@example.kz")
    monkeypatch.setattr(engine, "_represent", inspect_vector_inputs)
    output = engine.analyze([allowed, review, raw], mode="tfidf")
    assert seen == [allowed["text"]]
    results = {result["appeal_id"]: result for result in output["results"]}
    assert results["REVIEW"]["status"] == results["RAW"]["status"] == "blocked"
    assert normalized_members(output["cases"]) == [["SAFE"]]


def test_e5_receives_query_prefix_for_appeals_and_prototypes(monkeypatch):
    from app.ai import engine

    calls = []

    class FakeLocalModel:
        def encode(self, texts, **kwargs):
            calls.append((texts, kwargs))
            return np.eye(len(texts), dtype=np.float32)

    monkeypatch.setattr(engine, "_load_model", lambda: FakeLocalModel())
    output = engine.analyze(CONTROLS[0]["records"], mode="auto")
    assert len(calls) == 1
    texts, options = calls[0]
    assert all(text.startswith("query: ") for text in texts)
    assert texts[:2] == ["query: " + record["text"] for record in CONTROLS[0]["records"]]
    assert len(texts) == 2 + sum(len(values) for values in engine.PROTOTYPES.values())
    assert options["normalize_embeddings"] is True
    assert options["batch_size"] == 16
    assert options["convert_to_numpy"] is True
    assert output["algorithm"]["semantic"] is True
    assert output["algorithm"]["name"] == "multilingual-e5-small"


def test_semantic_similarity_chain_requires_every_pair_to_match(monkeypatch):
    from app.ai import engine

    records = [appeal("CHAIN-A", "В доме нет воды."), appeal("CHAIN-B", "Холодная вода отключена."), appeal("CHAIN-C", "Подача воды отсутствует.")]
    similarities = np.array([[1.0, 0.9, 0.1], [0.9, 1.0, 0.9], [0.1, 0.9, 1.0]])
    monkeypatch.setattr(engine, "_represent", lambda texts, mode: (similarities, None, engine._metadata(True)))
    output = engine.analyze(records, mode="auto")
    assert sorted(len(case["appeal_ids"]) for case in output["cases"]) == [1, 2]
    assert all(not {"CHAIN-A", "CHAIN-C"}.issubset(case["appeal_ids"]) for case in output["cases"])


def write_report(path: Path, mode="tfidf"):
    from app.ai.engine import analyze

    rows = []
    for control in CONTROLS:
        output = analyze(control["records"], mode=mode)
        actual, failures = assess_control(control, output)
        rows.append({**control, "actual": actual, "passed": not failures, "failures": failures, "algorithm": output["algorithm"], "output": output})
    report = {"dataset": "Independent synthetic controls A-H; not a representative accuracy benchmark", "mode": mode, "total": len(rows), "passed": sum(row["passed"] for row in rows), "controls": rows}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--mode", choices=["tfidf", "auto"], default="tfidf")
    arguments = parser.parse_args()
    report = write_report(arguments.report, arguments.mode)
    print(f"{report['passed']}/{report['total']} synthetic controls passed ({arguments.mode})")
    raise SystemExit(0 if report["passed"] == report["total"] else 1)
