import base64
import hashlib
import hmac
import json
from dataclasses import asdict

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
