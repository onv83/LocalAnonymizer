from local_anonymizer.engine import Anonymizer


def test_two_letter_uppercase_abbreviations_require_more_than_five_exact_tokens():
    frequent = "ЮЯ"
    rare = "ФХ"
    source = " ".join([frequent] * 6 + [rare] * 5)

    result = Anonymizer().anonymize(source)

    frequent_marker = next(
        marker for marker, value in result.mapping.items() if value == frequent
    )
    assert result.text.count(frequent_marker) == 6
    assert result.text.count(rare) == 5
    assert rare not in result.mapping.values()
    assert result.counts["СОКРАЩЕНИЯ"] == 6


def test_two_letter_frequency_uses_only_complete_uppercase_letter_tokens():
    standalone = "QZ"
    source = " ".join(
        [standalone] * 5
        + ["Qz", "qz", "QZ1", "XQZ", "QZ-QZ"] * 6
    )

    result = Anonymizer().anonymize(source)

    assert result.text.startswith("QZ QZ QZ QZ QZ ")
    assert standalone not in result.mapping.values()
    assert "QZ1" in result.text
    assert "QZ-QZ" in result.text


def test_two_letter_frequency_combines_nfc_equivalents_but_restores_exactly():
    composed = "ÅB"
    decomposed = "A\u030aB"
    source = " ".join([composed] * 3 + [decomposed] * 3)

    result = Anonymizer().anonymize(source)

    assert set(result.mapping.values()) == {composed, decomposed}
    assert result.counts["СОКРАЩЕНИЯ"] == 6
    restored = result.text
    for marker, original in result.mapping.items():
        restored = restored.replace(marker, original)
    assert restored == source


def test_two_letter_frequency_allows_unicode_letter_continuations():
    samples = ("A\u0483B", "A\u200cB")
    source = " ".join(sample for sample in samples for _ in range(6))

    result = Anonymizer().anonymize(source)

    assert set(result.mapping.values()) == set(samples)
    assert result.counts["СОКРАЩЕНИЯ"] == 12


def test_frequent_two_letter_abbreviations_can_be_disabled():
    source = " ".join(["QZ"] * 6)

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
    assert "ИС" in result.text
    assert "AD" in result.text
    qzxb_marker = next(marker for marker, value in result.mapping.items() if value == "QZXB")
    assert result.text.count(qzxb_marker) == 2
    assert result.counts["СОКРАЩЕНИЯ"] == 5
    assert set(result.mapping.values()) >= {"UCMDB", "QZXB", "SSO", "NTLM"}

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


def test_abbreviations_use_three_uppercase_letters_but_preserve_short_units_and_markers():
    source = (
        "Объем 128 GB, 500 МБ, версия 2.0, ИНН 7707083893, КПП 773601001, "
        "IP 192.0.2.1, [ФИО-7]."
    )

    result = Anonymizer().anonymize(source)

    assert all(value in result.text for value in ("GB", "МБ", "IP", "[ФИО-7]"))
    assert "[ФИО-7]" in result.text
    assert result.mapping.get("[ИНН-1]") == "7707083893"
    assert result.mapping.get("[КПП-1]") == "773601001"
    assert result.mapping.get("[IP-1]") == "192.0.2.1"
    abbreviation_values = {
        item["orig"] for item in result.legend if item["cat"] == "СОКРАЩЕНИЯ"
    }
    assert abbreviation_values == {"ИНН", "КПП"}


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
        "АКТ", "ГОСТ", "МВД", "ФНС", "IMPORTANT", "DOCUMENT", "DATA", "SLA",
    }
    assert all(value in result.text for value in ("ПО", "ТЗ", "РФ", "ЦБ", "GB", "МБ", "[ФИО-7]"))


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
