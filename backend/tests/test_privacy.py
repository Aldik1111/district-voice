"""Privacy regressions use API outputs and the actual SQLite contents."""

import json
import sqlite3

import pytest


def dumped_database(database_url):
    with sqlite3.connect(database_url.removeprefix("sqlite:///")) as connection:
        return "\n".join(connection.iterdump())


def assert_no_secrets(value, secrets):
    serialized = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    for secret in secrets:
        assert secret not in serialized, f"Unmasked value escaped: {secret}"


def test_phone_email_iin_are_masked_before_preview_and_never_stored(client, valid_record, upload_csv, confirm, database_url):
    secrets = ["+7 (701) 123-45-67", "demo.resident@example.kz", "900101123456"]
    record = {
        **valid_record,
        "text": f"Нет воды. Контакты: {secrets[0]}, {secrets[1]}, {secrets[2]}.",
        "address": "ул. Абая, 15",
    }
    preview = upload_csv(client, [record])
    assert preview.status_code == 200, preview.text
    row = preview.json()["rows"][0]
    assert row["text"] != record["text"]
    assert_no_secrets(preview.json(), secrets)
    # Raw values must not be written even to the temporary preview storage.
    assert_no_secrets(dumped_database(database_url), secrets)

    result = confirm(client, preview)
    assert result["accepted"] == 1
    assert_no_secrets(client.get("/api/appeals").json(), secrets)
    assert_no_secrets(client.get("/api/imports").json(), secrets)
    assert_no_secrets(dumped_database(database_url), secrets)
    stats = client.get("/api/stats").json()
    assert stats["masked"] == 1


@pytest.mark.parametrize(
    ("sensitive_text", "secret"),
    [
        ("ИИН: 900 101 123 456", "900 101 123 456"),
        ("ЖСН: 910-202-123-456", "910-202-123-456"),
        ("Тел: 123-45-67", "123-45-67"),
        ("байланыс нөмірі: 234 56 78", "234 56 78"),
    ],
)
def test_labeled_spaced_iin_and_local_phones_are_masked(client, valid_record, upload_csv, confirm, database_url, sensitive_text, secret):
    preview = upload_csv(client, [{**valid_record, "text": f"Нет воды. {sensitive_text}."}])
    assert preview.status_code == 200, preview.text
    assert_no_secrets(preview.json(), [secret])
    assert_no_secrets(dumped_database(database_url), [secret])
    assert preview.json()["rows"][0]["privacy_status"] == "masked"
    assert confirm(client, preview)["accepted"] == 1
    assert_no_secrets(client.get("/api/appeals").json(), [secret])
    assert_no_secrets(dumped_database(database_url), [secret])


def test_invalid_row_errors_and_preview_do_not_echo_raw_pii(client, valid_record, upload_csv, confirm, database_url):
    secrets = ["private.person@example.kz", "911231123456"]
    preview = upload_csv(client, [{
        **valid_record,
        "date": "invalid-date",
        "text": f"Email {secrets[0]}, ЖСН {secrets[1]}",
    }])
    assert preview.status_code == 200, preview.text
    assert preview.json()["invalid_rows"] == 1
    assert_no_secrets(preview.json(), secrets)
    assert_no_secrets(dumped_database(database_url), secrets)
    assert confirm(client, preview)["rejected"] == 1
    assert_no_secrets(dumped_database(database_url), secrets)


@pytest.mark.parametrize("field", ["source", "source_record_id", "official_status"])
def test_personal_data_in_metadata_is_rejected_without_leak(client, valid_record, upload_csv, confirm, database_url, field):
    secret = "metadata.private@example.kz"
    record = {**valid_record, field: secret}
    preview = upload_csv(client, [record])
    assert preview.status_code == 200, preview.text
    assert preview.json()["invalid_rows"] == 1
    assert_no_secrets(preview.json(), [secret])
    assert_no_secrets(dumped_database(database_url), [secret])
    assert confirm(client, preview)["rejected"] == 1
    assert client.get("/api/appeals").json()["total"] == 0


def test_suspected_name_and_apartment_require_manual_review(client, valid_record, upload_csv, confirm):
    preview = upload_csv(client, [{
        **valid_record,
        "text": "Меня зовут Иванов Иван Иванович. Уже неделю нет воды.",
        "address": "ул. Абая, д. 15, кв. 42",
    }])
    assert preview.status_code == 200, preview.text
    row = preview.json()["rows"][0]
    assert row["privacy_status"] == "review_required"
    assert row["warnings"]
    confirm(client, preview)
    assert client.get("/api/appeals").json()["items"][0]["privacy_status"] == "review_required"
    assert client.get("/api/stats").json()["review_required"] == 1


def test_privacy_edit_rejects_personal_data_and_stale_version_cannot_overwrite(client, valid_record, upload_csv, confirm, database_url):
    confirm(client, upload_csv(client, [valid_record]))
    appeal = client.get("/api/appeals").json()["items"][0]
    secret = "new.private@example.kz"
    update = {
        "text": f"Нет воды. Для связи: {secret}",
        "address": appeal["address"],
        "version": appeal["version"],
    }
    response = client.patch(f"/api/appeals/{appeal['id']}/privacy", json=update)
    assert response.status_code == 422, response.text
    assert_no_secrets(response.json(), [secret])
    assert client.get("/api/appeals").json()["items"][0] == appeal
    assert_no_secrets(dumped_database(database_url), [secret])

    update["text"] = "После ручной проверки: на улице Абая нет воды."
    response = client.patch(f"/api/appeals/{appeal['id']}/privacy", json=update)
    assert response.status_code == 200, response.text
    saved = client.get("/api/appeals").json()["items"][0]
    assert saved["version"] > appeal["version"]
    assert saved["text"] == update["text"]
    assert_no_secrets(saved, [secret])
    assert_no_secrets(dumped_database(database_url), [secret])

    stale = client.patch(f"/api/appeals/{appeal['id']}/privacy", json={**update, "text": "Перезаписать устаревшую версию"})
    assert stale.status_code == 409, stale.text
    assert client.get("/api/appeals").json()["items"][0]["text"] == saved["text"]
    repeated = confirm(client, upload_csv(client, [valid_record]))
    assert repeated["duplicates"] == 1
    assert client.get("/api/appeals").json()["items"][0]["text"] == saved["text"]


def test_missing_version_cannot_bypass_edit_guard(client, valid_record, upload_csv, confirm):
    confirm(client, upload_csv(client, [valid_record]))
    appeal = client.get("/api/appeals").json()["items"][0]
    response = client.patch(f"/api/appeals/{appeal['id']}/privacy", json={"text": "Устаревшая запись", "address": "ул. Абая"})
    assert 400 <= response.status_code < 500, response.text
    assert client.get("/api/appeals").json()["items"][0]["text"] == appeal["text"]
