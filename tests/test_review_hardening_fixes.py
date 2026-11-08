import pytest

from local_anonymizer.engine import Anonymizer
from local_anonymizer.app import asset_path


@pytest.mark.parametrize("source,value", [
    ("Например, документ Form12345 был обновлен", "Form12345"),
    ("На принтере напечатан документ Cheque12345", "Cheque12345"),
    ("Рабочая станция загружает Profile2026", "Profile2026"),
])
def test_structured_identifier_does_not_mask_ordinary_prose(source, value):
    result = Anonymizer().anonymize(source)
    assert value in result.text
    assert "[УЗЕЛ-" not in result.text


def test_structured_identifier_still_masks_explicit_naming_example():
    result = Anonymizer().anonymize("Пример: сервер QZ_v10_RF")
    assert "QZ_v10_RF" not in result.text
    assert "[УЗЕЛ-" in result.text


@pytest.mark.parametrize("source", [
    "Количество страниц в отчете составляет 3 тыс.",
    "На сервере хранится 3 тыс. документов",
])
def test_thousands_metric_does_not_mask_document_counts(source):
    result = Anonymizer().anonymize(source)
    assert "3 тыс." in result.text
    assert "[МЕТРИКА-" not in result.text


def test_thousands_metric_keeps_confirmed_account_capacity():
    result = Anonymizer().anonymize("Общее количество активных пользовательских аккаунтов примерно 30 тыс.")
    assert "30 тыс." not in result.text
    assert "[МЕТРИКА-" in result.text


def test_metric_category_is_exposed_in_both_active_category_panels():
    for name in ("index-v1.8.23.html", "index-en-v1.8.23.html"):
        html = asset_path(name).read_text(encoding="utf-8")
        assert html.count('data-categories="МЕТРИКА"') == 1
        assert "[МЕТРИКА-N]" in html


def test_system_inventory_accepts_numbered_pp_header():
    source = (
        "Интеграционные системы\ufdd0\ufdd1\ufdd0№ п/п\ufdd0Система\ufdd0Тип"
        "\ufdd0\ufdd2\ufdd01\ufdd0QZ Internal Suite\ufdd0Информационная система"
        "\ufdd0\ufdd2\ufdd02\ufdd0QZ Monitoring Hub\ufdd0Мониторинг\ufdd0\ufdd2\ufdd0"
    )

    result = Anonymizer().anonymize(source)

    assert "QZ Internal Suite" not in result.text
    assert "QZ Monitoring Hub" not in result.text
    assert result.text.count("[СИСТЕМА-") == 2


def test_em_dash_is_accepted_in_new_metric_and_account_rules():
    source = "Защита от брутфорса — 45 минут. Участник — administrator. AdminCount=1 — 64"

    result = Anonymizer().anonymize(source)

    assert "45 минут" not in result.text
    assert "administrator" not in result.text
    assert "64" not in result.text
    assert "[МЕТРИКА-" in result.text
    assert "[ЛОГИН-" in result.text


def test_table_cell_punctuation_residue_does_not_create_marker():
    source = (
        "Приложение А Групповые политики\ufdd0\ufdd1\ufdd0№\ufdd0Наименование"
        "\ufdd0\ufdd2\ufdd01\ufdd0[СТРУКТУРА-AD-1];\ufdd0\ufdd2\ufdd0"
    )

    result = Anonymizer().anonymize(source)

    assert ";" not in result.mapping.values()
    assert not any(value.strip(" .,:;—–-") == "" for value in result.mapping.values())


def test_secret_value_does_not_swallow_following_word_run():
    source = "password=[PERSON-1]\ufdd3Для"

    result = Anonymizer().anonymize(source)

    assert "Для" in result.text
    assert set(result.mapping.values()) == {"[PERSON-1]"}
    assert "1]\nДля" not in result.mapping.values()


def test_password_update_adverb_is_not_a_secret():
    source = "Обновление пароля - автоматически в 120 дней"

    result = Anonymizer().anonymize(source)

    assert "автоматически" in result.text
    assert "автоматически" not in result.mapping.values()
    assert "120 дней" not in result.text


def test_order_number_suffix_is_part_of_document_metadata():
    source = "Введено Приказом от 01.02.2030 № 123-ОД"

    result = Anonymizer().anonymize(source)

    assert "123-ОД" not in result.text
    assert "-ОД" not in result.text
    assert result.text.count("[ДОКУМЕНТ-") == 1
    assert list(result.mapping.values()) == ["01.02.2030 № 123-ОД"]


def test_structured_identifier_comma_example_is_not_naming_context():
    source = "Пример, документ Form12345 был обновлен"

    result = Anonymizer().anonymize(source)

    assert "Form12345" in result.text
    assert "[УЗЕЛ-" not in result.text


def test_structured_identifier_naming_context_does_not_cross_sentence():
    source = "Пример: сервер QZ_v10_RF. Документ Form12345 обновлен"

    result = Anonymizer().anonymize(source)

    assert "QZ_v10_RF" not in result.text
    assert "Form12345" in result.text


def test_structured_identifier_sentence_break_immediately_before_candidate():
    source = "Формат имени: site-role-0001. Обновления2026"

    result = Anonymizer().anonymize(source)

    assert "site-role-0001" not in result.text
    assert "Обновления2026" in result.text


@pytest.mark.parametrize("separator", ["\n", "\ufdd0"])
def test_structured_identifier_naming_context_does_not_cross_document_boundaries(separator):
    source = f"Пример: сервер QZ_v10_RF{separator}Документ Form12345 обновлен"

    result = Anonymizer().anonymize(source)

    assert "QZ_v10_RF" not in result.text
    assert "Form12345" in result.text


def test_vm_inventory_general_host_is_stable_on_first_and_second_pass():
    source = (
        "Компоненты\ufdd0\ufdd1\ufdd0№\ufdd0Компонент\ufdd0Hostname\ufdd0CPU\ufdd0RAM\ufdd0Disk\ufdd0Разметка\ufdd0IP\ufdd0Маска"
        "\ufdd0\ufdd2\ufdd01\ufdd0Файловый сервер\ufdd0srv-file-001\ufdd08\ufdd016\ufdd0200"
        "\ufdd0/data 50 [СОКРАЩЕНИЯ-57]\ufdd0192.0.2.-\ufdd024\ufdd0\ufdd2\ufdd0"
    )

    first = Anonymizer().anonymize(source)
    for value in ("srv-file-001", "/data", "192.0.2.-"):
        assert value not in first.text
    assert {"8", "16", "200"}.issubset(set(first.mapping.values()))
    assert "24" in first.text

    second = Anonymizer().anonymize(first.text)
    assert second.text == first.text
    assert second.mapping == {}


def test_four_word_product_version_label_is_not_fragmented():
    result = Anonymizer().anonymize("Используется Astra Linux Special Edition версии 1.7.5.")

    assert "Astra" not in result.text
    assert list(result.mapping.values()) == ["Astra Linux Special Edition версии 1.7.5"]


def test_six_word_product_version_label_is_not_fragmented():
    result = Anonymizer().anonymize("Используется Astra Linux Special Edition Certified Build версии 1.7.5.")

    assert "Astra" not in result.text
    assert list(result.mapping.values()) == ["Astra Linux Special Edition Certified Build версии 1.7.5"]


def test_summary_capacity_words_are_not_commercial():
    for source, value in (
        ("Суммарное количество серверов 7,6 тыс.", "7,6 тыс."),
        ("Суммарно 5 серверов", "5"),
    ):
        result = Anonymizer().anonymize(source)
        assert value not in result.text
        assert "[МЕТРИКА-" in result.text


def test_thousands_currency_is_money_not_capacity_metric():
    result = Anonymizer().anonymize("Сервер закуплен на сумму 500 тыс. руб.")

    assert "500 тыс." not in result.text
    assert "[МЕТРИКА-" not in result.text
    assert "[СУММА-" in result.text


def test_center_of_data_does_not_disable_server_count():
    result = Anonymizer().anonymize("В центре данных 5 серверов")

    assert "5" not in result.text
    assert "[МЕТРИКА-" in result.text


def test_capacity_noun_after_thousands_supports_context():
    result = Anonymizer().anonymize("Зарегистрировано 12 тыс. пользователей")

    assert "12 тыс." not in result.text
    assert "[МЕТРИКА-" in result.text


def test_multiword_product_version_label_is_not_fragmented():
    result = Anonymizer().anonymize("Используется Astra Linux версии 1.7.5.")

    assert "Astra" not in result.text
    assert "Linux" not in result.text
    assert "1.7.5" not in result.text
    assert list(result.mapping.values()) == ["Astra Linux версии 1.7.5"]


def test_document_specification_version_is_not_software():
    source = "Изменения в версии 2 спецификации сохранены"

    result = Anonymizer().anonymize(source)

    assert "версии 2 спецификации" in result.text
    assert "[ПРОГРАММА-" not in result.text


def test_multiword_product_name_is_not_fragmented():
    source = "Используется Alt Linux 1.7.5."

    result = Anonymizer().anonymize(source)

    assert "Alt" not in result.text
    assert "Linux" not in result.text
    assert "1.7.5" not in result.text
    assert list(result.mapping.values()) == ["Alt Linux 1.7.5"]


def test_mail_server_all_caps_name_remains_abbreviation():
    result = Anonymizer().anonymize("Почтового сервера UCMDB")

    assert "UCMDB" not in result.text
    assert "[СОКРАЩЕНИЯ-" in result.text
    assert "[СИСТЕМА-" not in result.text


def test_residual_batch_docx_roundtrip(tmp_path):
    from docx import Document
    from local_anonymizer.documents import DocxProcessor

    source, output, restored = [tmp_path / name for name in ("source.docx", "out.docx", "restored.docx")]
    doc = Document()
    table = doc.add_table(rows=3, cols=3)
    for cell, value in zip(table.rows[0].cells, ("№ п/п", "Система", "Тип")):
        cell.text = value
    for row, values in zip(table.rows[1:], (("1", "QZ Internal Suite", "Информационная система"), ("2", "QZ Monitoring Hub", "Мониторинг"))):
        for cell, value in zip(row.cells, values):
            cell.text = value
    doc.save(source)
    original = source.read_bytes()

    processor = DocxProcessor()
    result = processor.anonymize(source, output)
    output_text = "\n".join(cell.text for table in Document(output).tables for row in table.rows for cell in row.cells)
    assert "QZ Internal Suite" not in output_text
    assert "QZ Monitoring Hub" not in output_text
    assert source.read_bytes() == original

    unknown = processor.restore(output, restored, result.mapping, package_archive=result.package_archive)
    assert unknown == []
    assert restored.read_bytes() == original
