from local_anonymizer.engine import Anonymizer
from local_anonymizer.formats import restore_text_file


def test_custom_label_with_digits_and_underscore_reserves_existing_counter():
    engine = Anonymizer(user_dictionary={"alpha beta": "CASE_ID2"})
    first = engine.anonymize("alpha beta")

    second = engine.anonymize(first.text + " | alpha beta")

    assert first.text == "[CASE_ID2-1]"
    assert second.text == "[CASE_ID2-1] | [CASE_ID2-2]"


def test_text_restore_supports_custom_label_with_digits_and_underscore(tmp_path):
    marker = "[CASE_ID2-1]"
    source = tmp_path / "anonymized.txt"
    output = tmp_path / "restored.txt"
    source.write_text(marker, encoding="utf-8")

    unknown = restore_text_file(source, output, {marker: "alpha beta"})

    assert output.read_text(encoding="utf-8") == "alpha beta"
    assert unknown == []
