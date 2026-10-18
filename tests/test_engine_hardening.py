import base64
import hashlib
import hmac
import json
from dataclasses import asdict

import pytest

from local_anonymizer.engine import Anonymizer, _stem_surname


def _serialized(result) -> str:
    return json.dumps(asdict(result), ensure_ascii=False)


def test_quoted_multiword_secrets_are_removed_as_complete_values():
    secrets = ("correct horse battery staple", "синяя лошадь батарейка скоба")
    source = f'password="{secrets[0]}"; секретная фраза=«{secrets[1]}»'

    result = Anonymizer().anonymize(source)
    serialized = _serialized(result)

    assert result.text.count("(удалено)") == 2
    for secret in secrets:
        assert secret not in serialized
        for word in secret.split():
            assert word not in serialized


def test_real_synthetic_jwt_is_removed_irreversibly():
    def b64url(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    header = b64url(b'{"alg":"HS256","typ":"JWT"}')
    payload = b64url(b'{"sub":"synthetic-user","iat":1789344000}')
    signing_input = f"{header}.{payload}"
    signature = b64url(hmac.new(b"test-only-signing-key", signing_input.encode(), hashlib.sha256).digest())
    token = f"{signing_input}.{signature}"

    result = Anonymizer().anonymize(f"Authorization: Bearer {token}")

    assert token not in _serialized(result)
    assert result.text == "Authorization: Bearer (удалено)"
    assert result.mapping == {}


def test_two_component_people_with_shared_surnames_get_distinct_markers():
    source = "Сергей Иванов и Алексей Иванов; Sergey Petrov and Alexey Petrov."

    result = Anonymizer().anonymize(source)

    assert len(result.mapping) == 4
    assert set(result.mapping.values()) == {
        "Сергей Иванов",
        "Алексей Иванов",
        "Sergey Petrov",
        "Alexey Petrov",
    }
    assert all(f"[ФИО-{index}]" in result.text for index in range(1, 5))


def test_surname_stem_normalizes_russian_case_forms():
    assert {_stem_surname(value) for value in ("Иванов", "Иванова", "Иванову")} == {"иванов"}
    assert {
        _stem_surname(value)
        for value in ("Петровский", "Петровского", "Петровскому", "Петровской")
    } == {"петровский"}


def test_initials_reuse_anchor_but_bare_declined_surname_gets_separate_marker():
    source = "Петровский Иван Сергеевич. И. С. Петровскому. Позвать Петровского."

    result = Anonymizer().anonymize(source)

    assert result.text.count("[ФИО-1]") == 2
    assert result.text.count("[ФИО-2]") == 1
    assert "Петровск" not in result.text
    assert result.mapping == {
        "[ФИО-1]": "Петровский Иван Сергеевич",
        "[ФИО-2]": "Петровского",
    }


def test_full_name_case_and_order_variants_share_one_identity_marker():
    source = (
        "Иванов Сергей Петрович; Иванова Сергея Петровича; И. С. Иванов; "
        "Сергей Петрович Иванов"
    )

    result = Anonymizer().anonymize(source)

    assert result.text.count("[ФИО-1]") == 4
    assert "[ФИО-2]" not in result.text
    assert result.mapping == {"[ФИО-1]": "Иванов Сергей Петрович"}


def test_initials_disambiguate_people_but_bare_surname_remains_hint():
    source = (
        "Иванов Сергей Петрович; Иванов Алексей Николаевич; "
        "И. С. Иванов; позвать Иванова."
    )

    result = Anonymizer().anonymize(source)

    assert result.text.count("[ФИО-1]") == 2
    assert result.text.count("[ФИО-2]") == 1
    assert "[ФИО-3]" not in result.text
    assert "Иванова" in result.text
    assert "Иванова" in result.candidates


def test_initials_remain_hint_when_multiple_anchors_are_compatible():
    source = (
        "Иванов Сергей Петрович; Иванов Семён Павлович; "
        "И. С. Иванов; позвать Иванова."
    )

    result = Anonymizer().anonymize(source)

    assert "[ФИО-1]" in result.text and "[ФИО-2]" in result.text
    assert "[ФИО-3]" not in result.text
    assert "И. С. Иванов" in result.text
    assert {"Иванов", "Иванова"}.issubset(result.candidates)


def test_latin_full_name_canonical_normalizes_component_order():
    result = Anonymizer().anonymize("Sergey Petrov; Petrov Sergey")

    assert result.text == "[ФИО-1]; [ФИО-1]"
    assert result.mapping == {"[ФИО-1]": "Sergey Petrov"}


def test_disabled_custom_category_cannot_disable_dictionary_secret():
    secret = "dictionary-only-secret"
    result = Anonymizer(
        user_dictionary={secret: "SECRET"},
        disabled_categories={"CUSTOM"},
    ).anonymize(f"value={secret}")

    assert secret not in _serialized(result)
    assert result.text == "value=(удалено)"
    assert result.mapping == {}


def test_empty_dictionary_key_is_ignored():
    result = Anonymizer(user_dictionary={"": "CUSTOM"}).anonymize("plain text")

    assert result.text == "plain text"
    assert result.mapping == {}
    assert result.total == 0


def test_custom_phrase_does_not_match_inside_a_larger_word():
    result = Anonymizer(user_dictionary={"alpha beta": "СИСТЕМА"}).anonymize(
        "xxalpha betayy | alpha beta"
    )

    assert result.text == "xxalpha betayy | [СИСТЕМА-1]"
    assert result.mapping == {"[СИСТЕМА-1]": "alpha beta"}


def test_literal_marker_with_huge_digit_suffix_is_safe_and_does_not_reserve_counter():
    literal = f"[ФИО-{'9' * 5000}]"

    result = Anonymizer().anonymize(f"{literal} Иванов Сергей Петрович")

    assert result.text == f"{literal} [ФИО-1]"
    assert result.mapping == {"[ФИО-1]": "Иванов Сергей Петрович"}


def test_signed_synthetic_jwt_value_is_actually_redacted():
    def b64url(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    header = b64url(b'{"alg":"HS256","typ":"JWT"}')
    payload = b64url(b'{"sub":"regression-user","iat":1789344000}')
    signing_input = f"{header}.{payload}"
    signature = b64url(hmac.new(b"synthetic-test-key", signing_input.encode(), hashlib.sha256).digest())
    token = f"{signing_input}.{signature}"

    result = Anonymizer().anonymize(token)

    assert result.text == "(удалено: токен)"
    assert token not in _serialized(result)
    assert result.mapping == {}


def test_literal_custom_marker_label_with_digits_and_underscore_reserves_counter():
    anonymizer = Anonymizer(user_dictionary={"alpha beta": "CASE_ID2"})

    result = anonymizer.anonymize("[CASE_ID2-1] alpha beta")

    assert result.text == "[CASE_ID2-1] [CASE_ID2-2]"
    assert result.mapping == {"[CASE_ID2-2]": "alpha beta"}


def test_contextual_capture_is_rejected_when_full_regex_scope_crosses_office_boundary():
    source = "паспорт\ufdd0 12 34 567890"

    result = Anonymizer().anonymize(source)

    assert result.text == source
    assert result.mapping == {}


def test_document_heading_and_in_tom_chisle_do_not_seed_global_false_positives():
    source = (
        "Название документа\nФормат\nСтруктура документа\n"
        "Эксплуатационные документы выполняются на бумажных носителях.\n"
        "Требование действует в том числе при монтаже."
    )

    result = Anonymizer().anonymize(source)

    assert result.text == source
    assert result.mapping == {}


def test_contract_roles_and_payment_deadlines_are_not_people_or_money():
    source = (
        "После устранения Исполнителем недостатков Акт подписывается Заказчиком.\n"
        "Оплата производится не позднее 7 (Семи) рабочих дней со дня подписания."
    )

    result = Anonymizer().anonymize(source)

    assert result.text == source
    assert result.mapping == {}


def test_russian_street_first_postal_addresses_are_redacted_without_generic_street_words():
    source = (
        "Сервер 3 штуки — г. Москва, ул. Энтузиастов, д.5, к.6.\n"
        "Направляется по адресу: г. Москва, ул. Профсоюзная, 125А.\n"
        "Счет направляется по адресу: г. Москва, Профсоюзная улица, 125А.\n"
        "Улица была перекрыта, а проспект оказался свободен."
    )

    result = Anonymizer().anonymize(source)

    assert "ул. Энтузиастов, д.5, к.6" not in result.text
    assert "ул. Профсоюзная, 125А" not in result.text
    assert "Профсоюзная улица, 125А" not in result.text
    assert result.counts["АДРЕС"] == 3
    assert "Улица была перекрыта, а проспект оказался свободен." in result.text


def test_english_labelled_contact_address_and_software_are_redacted():
    source = (
        "Organization: Example Systems LLC\n"
        "Contact: Alex Example\n"
        "Address: 10 Test Street, Testville, 123456\n"
        "Email: demo@example.invalid\n"
        "Software: Example Office Suite\n"
        "This synthetic document contains no real people or addresses."
    )

    result = Anonymizer().anonymize(source)

    assert "Alex Example" not in result.text
    assert "10 Test Street, Testville" not in result.text
    assert "123456" not in result.text
    assert "Example Office Suite" not in result.text
    assert result.counts["ФИО"] == 1
    assert result.counts["АДРЕС"] == 1
    assert result.counts["ИНДЕКС"] == 1
    assert result.counts["ПРОГРАММА"] == 1


def test_new_false_positive_guards_keep_real_entities_detectable():
    source = (
        "Компания названа Atlas.\n"
        "Исполнитель Иванов подписал акт.\n"
        "Диск DATA подключен.\n"
        "Оплата составляет 7000 без НДС."
    )

    result = Anonymizer().anonymize(source)

    assert "Atlas" not in result.text
    assert "Иванов" not in result.text
    assert "DATA" not in result.text
    assert "7000" not in result.text
    assert result.counts["ОРГАНИЗАЦИЯ"] == 1
    assert result.counts["ФИО"] == 1
    assert result.counts["ДИСК"] == 1
    assert result.counts["СУММА"] == 1


def test_english_labels_are_contextual_and_respect_disabled_categories():
    unlabeled = "Alex Example visited 10 Test Street and reviewed Example Office Suite."
    assert Anonymizer().anonymize(unlabeled).text == unlabeled

    source = (
        "Contact: Alex Example\n"
        "Address: 10 Test Street, Testville, 123456\n"
        "Software: Example Office Suite"
    )
    disabled = Anonymizer(
        disabled_categories={"ФИО", "АДРЕС", "ИНДЕКС", "ПРОГРАММА"},
    ).anonymize(source)

    assert disabled.text == source
    assert disabled.mapping == {}


def test_address_and_deadline_adversarial_regressions():
    sensitive = (
        "Улица 50 лет Октября, д. 5\n"
        "Адрес: 8 Марта ул., 10\n"
        "Address: 10 Main Street, New York, NY 10001\n"
        "Address: 1600 Pennsylvania Avenue NW, Washington, DC 20500"
    )
    result = Anonymizer().anonymize(sensitive)

    for value in ("50 лет Октября", "8 Марта", "New York", "NY 10001", "Pennsylvania", "DC 20500"):
        assert value not in result.text
    assert result.counts["АДРЕС"] == 4
    assert result.counts["ИНДЕКС"] == 2

    ordinary = (
        "ул. была перекрыта, 5\n"
        "Улица была перекрыта, 5\n"
        "пр. завершён, д. 12\n"
        "123456 задач обработано, город Тестовый модуль завершён.\n"
        "Оплата производится в течение 7 банковских дней.\n"
        "Оплата производится не позднее 7 (Семи банковских) рабочих дней."
    )
    assert Anonymizer().anonymize(ordinary).text == ordinary


def test_complete_address_record_does_not_consume_surrounding_narrative():
    source = (
        "Работы выполняются по адресу Профсоюзная ул., 125А, Тестоградск, 123456.\n"
        "г. Тестоградск, ул. Испытателей, д. 5. После проверки документ подписывается."
    )

    result = Anonymizer().anonymize(source)

    assert "Работы выполняются по адресу" in result.text
    assert "После проверки документ подписывается." in result.text
    assert "Профсоюзная ул., 125А" not in result.text
    assert "ул. Испытателей, д. 5" not in result.text


def test_complete_address_span_inside_prose_consumes_all_typed_components_only():
    address = (
        "ул. Испытателей, д. 12, корп. 1, стр. 2, г. Тестоградск, "
        "Макетинская область, 123456"
    )
    source = f"Оплата производится через 7 дней; доставка: {address}; после подписания."

    result = Anonymizer().anonymize(source)

    assert result.text == (
        "Оплата производится через 7 дней; доставка: [АДРЕС-1]; после подписания."
    )
    assert result.mapping == {"[АДРЕС-1]": address}


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        ("Пр. Завершён, д. 12", "Пр. Завершён, д. 12"),
        ("Улица Проекта обсуждалась 5 дней.", "Улица Проекта обсуждалась 5 дней."),
        ("Проект QZXS, пр. Начат, д. 12.", "Проект [СОКРАЩЕНИЯ-1], пр. Начат, д. 12."),
    ),
)
def test_address_detector_rejects_project_like_street_phrases(source, expected):
    result = Anonymizer().anonymize(source)

    assert result.text == expected
    assert result.counts.get("АДРЕС", 0) == 0


def test_russian_city_street_address_without_comma_before_house_is_redacted_as_one_value():
    source = "г. Тестоградск, ул. Испытателей 67а"

    result = Anonymizer().anonymize(source)

    assert result.text == "[АДРЕС-1]"
    assert result.mapping == {"[АДРЕС-1]": source}


def test_russian_ordinal_street_address_without_comma_before_house_is_redacted():
    source = "г. Тестоградск, ул. 7го примера 68б"

    result = Anonymizer().anonymize(source)

    assert result.text == "[АДРЕС-1]"
    assert result.mapping == {"[АДРЕС-1]": source}


def test_russian_region_city_street_address_is_redacted_as_one_value():
    source = "Макетинская область, г. Макетинск, ул. Испытателей 12"

    result = Anonymizer().anonymize(source)

    assert result.text == "[АДРЕС-1]"
    assert result.mapping == {"[АДРЕС-1]": source}


def test_russian_inventory_geography_cells_and_numeric_street_do_not_leak():
    separator = "\ufdd0"
    source = separator.join((
        "Республика Испытаний (Тестоградск)",
        "Северо-Западный",
        "КЦ Тестоградск",
        "г. Тестоградск, ул. Испытателей 67а",
        "Макетинский автономный округ — Макетия",
        "Уральский",
        "КЦ Макетинск",
        "г. Макетинск, ул. 9 января 68б",
    ))

    result = Anonymizer().anonymize(source)

    assert result.text == separator.join((
        "[ГОРОД-1]",
        "[ГОРОД-2]",
        "КЦ [ГОРОД-3]",
        "[АДРЕС-1]",
        "[ГОРОД-4]",
        "[ГОРОД-5]",
        "КЦ [ГОРОД-6]",
        "[АДРЕС-2]",
    ))
    assert result.mapping == {
        "[ГОРОД-1]": "Республика Испытаний (Тестоградск)",
        "[ГОРОД-2]": "Северо-Западный",
        "[ГОРОД-3]": "Тестоградск",
        "[АДРЕС-1]": "г. Тестоградск, ул. Испытателей 67а",
        "[ГОРОД-4]": "Макетинский автономный округ — Макетия",
        "[ГОРОД-5]": "Уральский",
        "[ГОРОД-6]": "Макетинск",
        "[АДРЕС-2]": "г. Макетинск, ул. 9 января 68б",
    }


def test_russian_official_region_forms_are_consumed_with_full_addresses():
    sources = (
        "Тестовая автономная область, г. Тестоградск, ул. Испытателей 12",
        "Проверочная Республика — Макетия, г. Тестоградск, ул. Испытателей 12",
        "Макетинская обл., г. Тестоградск, ул. Испытателей 12",
    )

    for source in sources:
        result = Anonymizer().anonymize(source)
        assert result.text == "[АДРЕС-1]"
        assert result.mapping == {"[АДРЕС-1]": source}


@pytest.mark.parametrize(
    "source",
    (
        "123456, г. Тестоградск, пр. Испытателей, д. 12а",
        "123456, Макетинская область, г. Макетинск, ул. Проверочная, зд.5",
        "123456, Республика Испытаний, город Тестоградск, Макетинский район, улица Проверочная, д. № 12 а",
        "123456, Макетинская обл., г. Макетинск, ул. А. Испытателей, дом №12",
        "123456, Макетия, Тестовая Республика, г. Тестоградск, Макетинский район,бульвар имени А.Б. Испытателя, д.12/3",
        "пр. Испытаний, д. 12а, г. Тестоградск, 123456",
    ),
)
def test_complete_russian_postal_address_variants_are_redacted_as_one_value(source):
    result = Anonymizer().anonymize(source)

    assert result.text == "[АДРЕС-1]"
    assert result.mapping == {"[АДРЕС-1]": source}


@pytest.mark.parametrize(
    "source",
    (
        "123456, г. Тестоградск, Испытателей бульвар, 12",
        "123456, Республика Макетия г. Тестоградск, ул. Испытателей, д. 12, корп. 1",
        "ул. Испытателей, д. 12, г. Тестоградск, Макетинская область, 123456",
        "ул. Испытателей, д. 12а г. Тестоградск, Республика Макетия, 123456",
        "123456, г. Тестоградск, ул. Испытателей, д. 12, лит. А",
        "123456, Макетинская область, г. Тестоградск, ул. Испытателей, д. 12,\u00a0лит. А",
        "123456, г. Тестоградск, проезд Проверочный 7-А, д. 12, пом. 3",
        "ул.Испытателей, д. 12, г. Тестоградск, Макетинская область, Республика Примерия, 123456",
        "ул. испытателей, д. 12, г. Тестоградск, Макетинская область, Республика Примерия",
        "ул. Испытателей, д. 12, корп. 1, лит. А г. Тестоградск, 123456",
        "пр. Испытателей, д. 12, строение 1, г. Тестоградск, 123456",
    ),
)
def test_complete_address_record_consumes_reordered_geography_and_building_tail(source):
    result = Anonymizer().anonymize(source)

    assert result.text == "[АДРЕС-1]"
    assert result.mapping == {"[АДРЕС-1]": source}


def test_contextual_russian_address_variants_are_redacted_as_complete_values():
    addresses = (
        "Макетный пер. д.3",
        "Проверочный бульвар д.13 стр.1",
        "1-ый Лабораторный пр. д.1 стр.3",
        "Пробная аллея д.2/д",
        "Малый Контрольный пер. д.7",
        "Большая Испытательная, д.46",
    )
    source = (
        "Площадки расположены по адресам "
        + ", ".join(addresses[:4])
        + ", и "
        + addresses[4]
        + ", используется макет. Площадка расположена по адресу "
        + addresses[5]
        + "."
    )

    result = Anonymizer().anonymize(source)

    address_mapping = {
        marker: original
        for marker, original in result.mapping.items()
        if marker.startswith("[АДРЕС-")
    }
    assert set(address_mapping.values()) == set(addresses)
    assert len(address_mapping) == len(addresses)
    assert all(address not in result.text for address in addresses)
    assert "Площадки расположены по адресам" in result.text
    assert "Площадка расположена по адресу" in result.text
    restored = result.text
    for marker, original in address_mapping.items():
        restored = restored.replace(marker, original)
    assert restored == source


def test_address_context_does_not_turn_project_prose_into_an_address():
    source = (
        "Пр. Завершён, д. 12. "
        "Материалы отправлены по адресу электронной почты, д. 46."
    )

    result = Anonymizer().anonymize(source)

    assert result.text == source
    assert not any(marker.startswith("[АДРЕС-") for marker in result.mapping)


@pytest.mark.parametrize(
    "suffix",
    (
        "Пр. Завершён, д. 12.",
        "1-ый Проектный пр. д. 12.",
    ),
)
def test_address_list_context_stops_at_a_sentence_boundary(suffix):
    address = "Макетный пер. д.3"
    source = f"Площадки расположены по адресам {address}. {suffix}"

    result = Anonymizer().anonymize(source)

    assert result.text == f"Площадки расположены по адресам [АДРЕС-1]. {suffix}"
    assert result.mapping == {"[АДРЕС-1]": address}


def test_address_list_context_accepts_a_dotted_street_type_before_an_ambiguous_item():
    addresses = (
        "ул. Макетная, д.3",
        "1-ый Лабораторный пр. д.1 стр.3",
    )
    source = "Площадки расположены по адресам " + ", ".join(addresses) + "."

    result = Anonymizer().anonymize(source)

    assert set(result.mapping.values()) == set(addresses)
    assert result.text == "Площадки расположены по адресам [АДРЕС-1], [АДРЕС-2]."


def test_ambiguous_geography_like_fragments_stay_visible_without_inventory_row_context():
    separator = "\ufdd0"
    source = separator.join((
        "Предметная область",
        "Рабочая область",
        "Центральный",
        "Уральский",
        "КЦ Тестирование",
    ))

    assert Anonymizer().anonymize(source).text == source


def test_labelled_contacts_accept_initials_unicode_and_docx_boundaries():
    source = (
        "Contact: Alex J. Example\n"
        "Contact: José García\n"
        "Contact:\ufdd3Taylor Example\n"
        "Software:\ufdd3Example Office Suite"
    )

    result = Anonymizer().anonymize(source)

    for value in ("Alex J. Example", "José García", "Taylor Example", "Example Office Suite"):
        assert value not in result.text
    assert result.counts["ФИО"] == 3
    assert result.counts["ПРОГРАММА"] == 1
    assert "\ufdd3" in result.text
