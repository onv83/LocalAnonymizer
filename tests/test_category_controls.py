import pytest

from local_anonymizer.engine import Anonymizer


STANDARD_CLASS_CASES = {
    "DN": "CN=Test User,OU=Lab,DC=example,DC=test",
    "IP": "192.0.2.10",
    "MAC": "02:00:5e:10:00:00",
    "IMEI": "IMEI: 123456789012347",
    "VIN": "VIN 1HGBH41JXMN109186",
    "АККАУНТ": "Связь: @synthetic_user",
    "БИК": "БИК 040000000",
    "ГОРОД": "Москва",
    "ГОСНОМЕР": "госномер А000АА 000",
    "ДАТА-РОЖДЕНИЯ": "дата рождения: 01.02.2000",
    "ДИСК": "диск SYNTH01",
    "ДОГОВОР": "договор № SYN-001",
    "ДОКУМЕНТ": "приказ № SYN-002",
    "ДОМЕН": "example.test",
    "ЗАДАЧА": "SYN-123",
    "ИНН": "ИНН 0000000000",
    "КАДАСТР": "кадастровый номер 00:00:0000000:000",
    "КАРТА": "карта 0000000000000",
    "КПП": "КПП 000000000",
    "ЛОГИН": "логин: synthetic_user",
    "ОГРН": "ОГРН 0000000000000",
    "ОРГАНИЗАЦИЯ": "ООО «Синтетикс»",
    "ПАСПОРТ": "паспорт 0000 000000",
    "ПОЧТА": "user@example.test",
    "ПРОГРАММА": "Развертывание ПО\ufdd0Synthetic App\ufdd0",
    "ПРОИЗВОДИТЕЛЬ": "производитель\ufdd0Synthetic Vendor",
    "ПУТЬ": r"C:\Synthetic\data.txt",
    "СЗИ": "Secret Net Studio",
    "СИСТЕМА": "АС «Синтетика»",
    "СКРИПТЫ": "Скрипты\ufdd0synthetic.ps1\ufdd0",
    "СНИЛС": "СНИЛС 00000000000",
    "ССЫЛКА": "https://example.test/path",
    "СТАВКА": "скидка 7%",
    "СТРУКТУРА-AD": "OU или контейнер AD\ufdd0Lab/Users\ufdd01\ufdd0100\ufdd050\ufdd0",
    "СУММА": "1000 рублей",
    "СЧЁТ": "расчетный счет 00000000000000000000",
    "ТАБЕЛЬНЫЙ": "табельный номер 000001",
    "ТЕЛЕФОН": "+7 900 000-00-00",
    "УЗЕЛ": "vm-synth-01",
    "ФИО": "Иванов Иван Иванович",
    "уязвимость": "CVE-2099-0001",
}

PARANOID_CLASS_CASES = {
    "ДОЛЖНОСТЬ": "директор отдела тестирования",
    "СПЕЦКАТЕГОРИЯ": "диагноз",
    "СКРЫТО": "это Квантум",
}


@pytest.mark.parametrize("category,source", STANDARD_CLASS_CASES.items())
def test_each_standard_replacement_class_has_an_effect_and_its_own_off_switch(category, source):
    enabled = Anonymizer(compact_markers=False).anonymize(source)
    assert enabled.counts.get(category, 0) >= 1, (category, enabled.text, enabled.counts)

    disabled = Anonymizer(disabled_categories={category}, compact_markers=False).anonymize(source)
    assert disabled.text == source
    assert category not in disabled.counts
    assert not disabled.mapping


@pytest.mark.parametrize("category,source", PARANOID_CLASS_CASES.items())
def test_each_paranoid_replacement_class_has_an_effect_and_its_own_off_switch(category, source):
    enabled = Anonymizer(paranoid=True, compact_markers=False).anonymize(source)
    assert enabled.counts.get(category, 0) >= 1, (category, enabled.text, enabled.counts)

    disabled = Anonymizer(
        paranoid=True,
        disabled_categories={category},
        compact_markers=False,
    ).anonymize(source)
    assert disabled.text == source
    assert category not in disabled.counts
    assert not disabled.mapping


def test_custom_dictionary_and_yellow_hints_are_separate_non_class_controls():
    custom_source = "Синтетикс"
    custom = Anonymizer(user_dictionary={custom_source: "ТЕСТ-КАТЕГОРИЯ"}).anonymize(custom_source)
    assert custom.text == "[ТЕСТ-КАТЕГОРИЯ-1]"
    custom_disabled = Anonymizer(
        user_dictionary={custom_source: "ТЕСТ-КАТЕГОРИЯ"},
        disabled_categories={"CUSTOM"},
    ).anonymize(custom_source)
    assert custom_disabled.text == custom_source
    assert not custom_disabled.mapping

    hint_source = "директор отдела тестирования"
    assert Anonymizer().anonymize(hint_source).hint_count
    assert not Anonymizer(disabled_categories={"HINTS"}).anonymize(hint_source).hint_count
