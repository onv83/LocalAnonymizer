from local_anonymizer.engine import Anonymizer


def test_single_two_letter_uppercase_unicode_abbreviation_is_redacted_and_restored_exactly():
    abbreviation = "ЮЯ"
    source = f"Код: {abbreviation}."

    result = Anonymizer().anonymize(source)

    marker = next(
        marker for marker, value in result.mapping.items() if value == abbreviation
    )
    assert result.text == f"Код: {marker}."
    assert result.counts["СОКРАЩЕНИЯ"] == 1
    assert result.text.replace(marker, result.mapping[marker]) == source


def test_two_letter_rule_uses_only_complete_uppercase_letter_tokens():
    standalone = "QZ"
    source = " ".join([
        standalone, "Qz", "qz", "QZ1", "XQZ", "QZ-QZ", "QZ_id", "id_QZ",
    ])

    result = Anonymizer().anonymize(source)

    assert standalone in result.mapping.values()
    assert "QZ1" in result.text
    assert "QZ-QZ" in result.text
    assert "QZ_id" in result.text and "id_QZ" in result.text
    assert "Qz" in result.text and "qz" in result.text
    assert set(result.mapping.values()) == {standalone, "XQZ"}


def test_two_letter_rule_preserves_nfc_equivalents_as_exact_distinct_values():
    composed = "ÅB"
    decomposed = "A\u030aB"
    source = f"{composed} {decomposed}"

    result = Anonymizer().anonymize(source)

    assert set(result.mapping.values()) == {composed, decomposed}
    assert result.counts["СОКРАЩЕНИЯ"] == 2
    restored = result.text
    for marker, original in result.mapping.items():
        restored = restored.replace(marker, original)
    assert restored == source


def test_two_letter_rule_allows_unicode_letter_continuations_without_partial_matches():
    samples = ("A\u0483B", "A\u200cB", "\u0301QZ", "QZ\u0301")
    source = " ".join(samples)

    result = Anonymizer().anonymize(source)

    assert set(result.mapping.values()) == set(samples)
    assert result.counts["СОКРАЩЕНИЯ"] == len(samples)
    assert "AB" not in result.mapping.values()


def test_single_two_letter_abbreviation_can_be_disabled():
    source = "QZ"

    result = Anonymizer(disabled_categories={"СОКРАЩЕНИЯ"}).anonymize(source)

    assert result.text == source
    assert result.mapping == {}
    assert "СОКРАЩЕНИЯ" not in result.counts


def test_abbreviations_have_an_independent_reversible_category():
    source = (
        "Для серверов используется UCMDB.\n"
        "Приоритетные ИС интегрированы с AD.\n"
        "QZXB Почта взаимодействует через SSO и NTLM.\n"
        "Повтор: QZXB."
    )

    result = Anonymizer().anonymize(source)

    assert all(value not in result.text for value in ("UCMDB", "QZXB", "SSO", "NTLM"))
    assert "ИС" not in result.text
    assert "AD" not in result.text
    qzxb_marker = next(marker for marker, value in result.mapping.items() if value == "QZXB")
    assert result.text.count(qzxb_marker) == 2
    assert result.counts["СОКРАЩЕНИЯ"] == 7
    assert set(result.mapping.values()) >= {"UCMDB", "ИС", "AD", "QZXB", "SSO", "NTLM"}

    restored = result.text
    for marker, original in result.mapping.items():
        restored = restored.replace(marker, original)
    assert restored == source


def test_abbreviations_can_be_disabled_without_blocking_other_categories():
    source = "QZXB Почта: admin@example.ru, адрес 192.0.2.1."

    result = Anonymizer(disabled_categories={"СОКРАЩЕНИЯ"}).anonymize(source)

    assert "QZXB" in result.text
    assert "СОКРАЩЕНИЯ" not in result.counts
    assert "admin@example.ru" not in result.text
    assert "192.0.2.1" not in result.text


def test_abbreviations_include_two_letter_units_but_preserve_existing_markers():
    source = (
        "Объем 128 GB, 500 МБ, версия 2.0, ИНН 7707083893, КПП 773601001, "
        "IP 192.0.2.1, [ФИО-7]."
    )

    result = Anonymizer().anonymize(source)

    assert {"GB", "МБ", "IP"} <= set(result.mapping.values())
    assert "[ФИО-7]" in result.text
    assert result.mapping.get("[ИНН-1]") == "7707083893"
    assert result.mapping.get("[КПП-1]") == "773601001"
    assert result.mapping.get("[IP-1]") == "192.0.2.1"
    abbreviation_values = {
        item["orig"] for item in result.legend if item["cat"] == "СОКРАЩЕНИЯ"
    }
    assert abbreviation_values == {"GB", "МБ", "ИНН", "КПП", "IP"}


def test_abbreviations_redact_every_token_with_three_consecutive_uppercase_letters():
    source = (
        "ОБЩИЕ ДАННЫЕ ПО ДОМЕНУ\nВАЖНО: ТЕКСТ ДОКУМЕНТА\n"
        "АКТ ТЗ РФ ГОСТ МВД ФНС ЦБ РФ\nIMPORTANT DOCUMENT DATA\n"
        "SLA GB МБ [ФИО-7]"
    )

    result = Anonymizer().anonymize(source)
    abbreviation_values = {
        item["orig"] for item in result.legend if item["cat"] == "СОКРАЩЕНИЯ"
    }

    assert abbreviation_values == {
        "ОБЩИЕ", "ДАННЫЕ", "ДОМЕНУ", "ВАЖНО", "ТЕКСТ", "ДОКУМЕНТА",
        "ПО", "АКТ", "ТЗ", "РФ", "ГОСТ", "МВД", "ФНС", "ЦБ",
        "IMPORTANT", "DOCUMENT", "DATA", "SLA", "GB", "МБ",
    }
    assert "[ФИО-7]" in result.text


def test_abbreviations_cover_multi_vowel_and_internal_identifier_forms():
    source = "ЕГАИС NASA UEFI UNESCO QZXB-ТЕСТ QZXB_ТЕСТ XQZXB QZXB1"

    result = Anonymizer().anonymize(source)

    assert "СОКРАЩЕНИЯ" in result.counts
    assert all(value not in result.text for value in source.split())
    assert set(result.mapping.values()) == set(source.split())


def test_abbreviations_redact_the_entire_token_around_any_three_uppercase_run():
    long_token = "A" * 33
    abbreviations = {
        "preABCpost",
        "ABCpost",
        "2ABC",
        "ABC-def",
        "abc-ABC",
        "АБВгде",
        "ÅÄÖ",
        "ЄЇІ",
        "A\u0301BC",
        "A\u0483BC",
        "AB\u200cC",
        "ABC\u0483def",
        "ABC\u200cdef",
        long_token,
    }
    source = " ".join(sorted(abbreviations) + ["preABpost"])

    result = Anonymizer().anonymize(source)

    assert abbreviations <= set(result.mapping.values())
    assert all(value not in result.text for value in abbreviations)
    assert "preABpost" in result.text


def test_custom_rules_win_over_abbreviations():
    source = "QZXB и ALPHA"
    result = Anonymizer(user_dictionary={"ALPHA": "ВНУТРЕННИЙ-КОД"}).anonymize(source)

    assert "[СОКРАЩЕНИЯ-1]" in result.text
    assert "[ВНУТРЕННИЙ-КОД-1]" in result.text
    assert result.mapping["[СОКРАЩЕНИЯ-1]"] == "QZXB"
    assert result.mapping["[ВНУТРЕННИЙ-КОД-1]"] == "ALPHA"


def test_abbreviations_have_a_compact_marker():
    result = Anonymizer(compact_markers=True).anonymize("QZXB")

    assert result.text == "[СОКР-1]"
    assert result.mapping == {"[СОКР-1]": "QZXB"}
