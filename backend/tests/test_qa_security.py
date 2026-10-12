"""Final-audit boundary tests; all inputs are synthetic and databases isolated."""
import io
import socket
import zipfile

import pytest


def test_ordinary_recount_comment_is_not_mistaken_for_a_bank_account():
    from app.privacy import mask
    comment = "Финальный QA: исключена синтетическая перепубликация для проверки пересчёта и сохранения связей."
    assert mask(comment).text == comment
    for value in ("счёт: AB12345678", "IBAN KZ000000000000000000", "паспорт: AB123456"):
        assert mask(value).text != value
        assert "[ДОКУМЕНТ СКРЫТ]" in mask(value).text


def test_local_guard_rejects_foreign_origins_and_hosts(client):
    assert client.get("/api/health", headers={"Origin": "https://untrusted.example"}).status_code == 403
    assert client.get("/api/health", headers={"Host": "untrusted.example"}).status_code == 400
    assert client.get("/api/health", headers={"Origin": "http://127.0.0.1:3000"}).status_code == 200


@pytest.mark.parametrize("kind", ["compressed_bomb", "macro", "too_many_members"])
def test_unsafe_xlsx_archive_rejected_before_parser(client, kind):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        if kind == "compressed_bomb":
            archive.writestr("xl/worksheets/sheet1.xml", "x" * (2 * 1024 * 1024))
        elif kind == "macro":
            archive.writestr("xl/vbaProject.bin", b"synthetic")
        else:
            for index in range(1001):
                archive.writestr(str(index), b"")
    response = client.post("/api/imports/preview", files={"file": ("synthetic.xlsx", output.getvalue())})
    assert response.status_code == 400
    assert client.get("/api/stats").json()["total_appeals"] == 0


def test_xml_incompatible_csv_text_is_rejected_and_database_unchanged(client, valid_record, upload_csv, confirm):
    preview = upload_csv(client, [dict(valid_record, text="Синтетический текст\uffff")])
    assert preview.status_code == 200 and preview.json()["invalid_rows"] == 1
    assert confirm(client, preview)["rejected"] == 1
    assert client.get("/api/appeals").json()["total"] == 0


def test_sql_metacharacters_are_literal_and_do_not_change_database(client, valid_record, upload_csv, confirm):
    row = dict(valid_record, source_record_id="QA-' OR 1=1 --", text="Нет воды. <script>synthetic()</script>")
    confirm(client, upload_csv(client, [row, dict(valid_record, source_record_id="QA-OTHER")]))
    response = client.get("/api/registry", params={"q": "' OR 1=1 --"})
    assert response.status_code == 200 and response.json()["total"] == 1
    assert response.json()["items"][0]["text"] == row["text"]
    assert client.get("/api/registry", params={"q": "%_"}).json()["total"] == 0
    assert client.get("/api/appeals").json()["total"] == 2


def test_missing_real_model_path_uses_offline_fallback_and_persists(client, valid_record, upload_csv, confirm, monkeypatch, tmp_path):
    confirm(client, upload_csv(client, [dict(valid_record, text="Абай көшесі 15 үйде су жоқ, холодная вода отключена.")]))
    attempts = []
    def forbid_network(*args, **kwargs):
        attempts.append("attempt")
        raise AssertionError("No external network allowed")
    monkeypatch.setenv("DISTRICT_VOICE_MODEL_PATH", str(tmp_path / "model-not-installed"))
    monkeypatch.setattr(socket.socket, "connect", forbid_network)
    result = client.post("/api/analysis/run", json={"mode": "auto"}).json()
    assert result["status"] == "completed" and result["algorithm"]["name"] == "tfidf_char"
    assert not result["algorithm"]["semantic"] and "FileNotFoundError" in result["algorithm"]["fallback_reason"]
    assert client.get("/api/analysis/results").json()[0]["category"] == "Водоснабжение"
    assert client.get("/api/analysis/runs/" + result["id"]).json() == result
    assert not attempts
