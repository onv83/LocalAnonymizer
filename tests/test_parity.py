from pathlib import Path
from zipfile import ZipFile
from dataclasses import asdict
import json

from local_anonymizer.app import AppApi, asset_path
from local_anonymizer.engine import Anonymizer
from local_anonymizer.service import AnonymizerService


def test_secret_variants_are_irreversible_and_never_mapped():
    text = (
        "Пароль от системы морковка123; ADMIN_PSWD='str0ngggg'; "
        "admin:Str0ngpassw Bearer AbCdEf12.ghIJkl34 "
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.signature99 "
        "" + ("ghp_" + "A" * 36) + " qwerty123 "
        "0123456789abcdefABCDEF0123456789abcdefABCDEF0123456789abcdef"
    )
    result = Anonymizer().anonymize(text)
    for secret in ("морковка123", "str0ngggg", "admin:Str0ngpassw", "AbCdEf12.ghIJkl34", "eyJhbGci", "ghp_", "qwerty123"):
        assert secret not in result.text
        assert secret not in repr(result.mapping)
    assert result.text.count("(удалено") >= 7
    assert all(part.get("secret") for part in result.parts if part["t"] == "ph" and part["s"].startswith("(удалено"))


def test_whitelist_and_custom_secret_rules_cannot_bypass_irreversible_deletion():
    result = Anonymizer(whitelist={"qwerty123", "TopSecret99"},
                        user_dictionary={"TopSecret99": "SECRET"}).anonymize(
                            "старый qwerty123, код TopSecret99")
    assert "qwerty123" not in result.text.lower()
    assert "TopSecret99" not in result.text
    assert not result.mapping
    assert result.text.count("(удалено") == 2


def test_secret_plaintext_is_absent_from_serializable_result_and_marker_cannot_shield_it():
    secret = "UltraSecret987!"
    result = Anonymizer().anonymize(f"password={secret}; password=[ФИО-1]")
    serialized = json.dumps(asdict(result), ensure_ascii=False)
    assert secret not in serialized
    assert "password=[ФИО-1]" not in result.text
    assert result.text.count("(удалено)") == 2
    assert all(not part.get("orig") for part in result.parts if part.get("secret"))


def test_people_org_system_logins_and_derived_aliases():
    text = (
        "Петров Иван Сергеевич встретился с Петровым. И. С. Петров подтвердил. "
        "Согласовано у Ivan Petrov; ответственный: Сергей; менеджер Ольга. "
        "ООО «Ромашка», Ромашки; ВТБ (ПАО); PromSoft GmbH. "
        "подрядчик «строй-гарант плюс»; компания — восход; называется альфа. "
        "АС «Паутина», Паутина; login admin_db; DOMAIN\\svc_backup."
    )
    result = Anonymizer().anonymize(text)
    assert result.text.count("[ФИО-1]") >= 2
    assert "[ФИО-2]" in result.text
    assert "[ОРГАНИЗАЦИЯ-1]" in result.text and result.text.count("[ОРГАНИЗАЦИЯ-1]") >= 2
    assert "[ОРГАНИЗАЦИЯ-2]" in result.text and "[ОРГАНИЗАЦИЯ-3]" in result.text
    assert "[ОРГАНИЗАЦИЯ-4]" in result.text and "[ОРГАНИЗАЦИЯ-5]" in result.text
    assert result.text.count("[СИСТЕМА-1]") == 2
    assert "[ЛОГИН-1]" in result.text and "[ЛОГИН-2]" in result.text
    assert "подрядчик «[ОРГАНИЗАЦИЯ-4]»" in result.text
    assert "компания — [ОРГАНИЗАЦИЯ-5]" in result.text
    assert "называется [ОРГАНИЗАЦИЯ-" in result.text
    assert "АС «[СИСТЕМА-1]»" in result.text


def test_people_with_same_surname_do_not_collide_or_claim_ambiguous_alias():
    source = "Иванов Сергей Петрович и Иванов Алексей Николаевич. Позвать Иванова."
    result = Anonymizer().anonymize(source)
    assert "[ФИО-1]" in result.text and "[ФИО-2]" in result.text
    assert result.mapping["[ФИО-1]"] != result.mapping["[ФИО-2]"]
    assert "Позвать Иванова" in result.text
    assert "Иванова" in result.candidates


def test_contacts_hosts_requisites_finance_and_uppercase_abbreviations():
    text = (
        "ivanov (at) alfa точка ru, +7 999 123-45-67 и 8 (999) 123-45-67, +49 30 901820; "
        "узел srv-db-01, БИК 044525225, паспорт 45 08 123456, VIN XTA210990Y2765432, "
        "договор № 25-08/2026-ПС, приказ № А-17; бюджет 5000000, 120 т.р., пять миллионов рублей, "
        "маржа 40%; версия 1.7.5.16, SLA 99,9%, НДС 20%, порт 8080."
    )
    result = Anonymizer().anonymize(text)
    assert result.text.count("[ТЕЛЕФОН-1]") == 2
    for marker in ("[ПОЧТА-1]", "[ТЕЛЕФОН-2]", "[УЗЕЛ-1]", "[БИК-1]", "[ПАСПОРТ-1]", "[VIN-1]", "[ДОГОВОР-1]", "[ДОКУМЕНТ-1]", "[СУММА-1]", "[СУММА-2]", "[СУММА-3]", "[СТАВКА-1]", "[ПОРТ-1]"):
        assert marker in result.text, marker
    assert "1.7.5.16" in result.text
    assert "порт [ПОРТ-1]" in result.text
    assert result.mapping["[ПОРТ-1]"] == "8080"
    abbreviation_values = {
        item["orig"] for item in result.legend if item["cat"] == "СОКРАЩЕНИЯ"
    }
    assert {"БИК", "VIN", "SLA", "НДС"} <= abbreviation_values


def test_structured_parts_offsets_counts_hints_paranoid_and_warnings():
    source = "ДСП. Объект КИИ в Казани. Начальник отдела ИБ Кудряшов. Диагноз: скрыт. ОКПД2 и КТРУ. массив персональных данных"
    result = Anonymizer().anonymize(source)
    assert result.total == sum(1 for p in result.parts if p["t"] == "ph")
    assert result.legend_total == len(result.mapping)
    assert result.hint_count >= 3
    assert "[ГОРОД-1]" in result.text
    assert all(source[p["s0"]:p["s1"]] == p["orig"] for p in result.parts if p["t"] != "text")
    assert {w["kind"] for w in result.warnings} >= {"ДСП", "КИИ", "ЗАКУПКИ", "МАССИВ-ПДН"}
    paranoid = Anonymizer(paranoid=True).anonymize("Начальник отдела ИБ работает в Казани. Диагноз указан.")
    assert "[ДОЛЖНОСТЬ-1]" in paranoid.text
    assert "[ГОРОД-1]" in paranoid.text
    assert "[СПЕЦКАТЕГОРИЯ-1]" in paranoid.text
    assert paranoid.hint_count == 0


def test_acceptance_sample_new_parity_requirements():
    result = Anonymizer().anonymize(Path("acceptance_sample.txt").read_text(encoding="utf-8"))
    assert "[ОРГАНИЗАЦИЯ-" in result.text and "строй-гарант плюс" not in result.text
    assert "[СИСТЕМА-1]" in result.text and "Паутина" not in result.text
    assert "[ЛОГИН-1]" in result.text and "admin_db" not in result.text
    assert "qwerty123" not in result.text.lower()
    assert "1.7.5.16" in result.text
    assert "порт [ПОРТ-1]" in result.text
    assert result.mapping["[ПОРТ-1]"] == "8080"
    abbreviation_values = {
        item["orig"] for item in result.legend if item["cat"] == "СОКРАЩЕНИЯ"
    }
    assert {"SLA", "НДС"} <= abbreviation_values


def test_batch_zip_contains_independently_restorable_ready_pairs(tmp_path):
    service = AnonymizerService(tmp_path / "app")
    ids = []
    for name in ("one.txt", "two.md"):
        source = tmp_path / name
        source.write_text("Иванов Сергей Петрович", encoding="utf-8")
        doc_id = service.import_file(source)
        service.anonymize(doc_id)
        ids.append(doc_id)
    target = tmp_path / "all.zip"
    exported = service.export_all_ready(target)
    assert exported == target
    with ZipFile(target) as archive:
        names = archive.namelist()
        anonymized = [n for n in names if "обезличенный" in n]
        recovery = [n for n in names if n.endswith(".larecovery")]
        assert len(anonymized) == len(recovery) == 2
        assert all("mapping" not in n.lower() and not n.lower().endswith(".csv") for n in names)
        assert all("[ФИО-1]" in archive.read(n).decode("utf-8") for n in anonymized)
        recovery_payloads = [json.loads(archive.read(n).decode("utf-8")) for n in recovery]
        assert all(payload["version"] == 2 for payload in recovery_payloads)
        assert all(payload["bundle"]["mapping"]["[ФИО-1]"] == "Иванов Сергей Петрович"
                   for payload in recovery_payloads)
        assert all("envelope" not in payload for payload in recovery_payloads)


def test_ui_contains_rich_review_interactions():
    html = asset_path("index-v1.8.18.html").read_text(encoding="utf-8")
    js = asset_path("app-v1.8.18.js").read_text(encoding="utf-8")
    css = asset_path("style-v1.1.css").read_text(encoding="utf-8")
    for element in ('id="sourceMirror"', 'id="richOutput"', 'id="downloadAll"', 'id="undoChips"'):
        assert element in html
    for behavior in ("setTimeout", "ctrlKey", "Escape", "scrollTop", "dataset.s0", "restoreReplacement", "reviewedHints", "preview_document", "fileDirty"):
        assert behavior in js
    assert "Требуется ручная проверка" in js and "confirm(" in js
    assert "if(filePreview&&selected)" in js and "pywebview.api.anonymize_document(current" in js
    assert "function markSettingsDirty" in js
    assert "!['Готов','Требуется ручная проверка'].includes(status)" in js
    for style in (".mark-replacement", ".mark-secret", ".mark-hint", ".source-mark"):
        assert style in css
