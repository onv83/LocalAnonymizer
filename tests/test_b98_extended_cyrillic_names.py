"""B98: public generic extended-Cyrillic vocabulary; synthetic pairings only."""
import hashlib
import json

import pytest

from local_anonymizer.engine import Anonymizer
from local_anonymizer.given_names import GIVEN_NAMES, canonical_given_name


EXTENDED_GIVEN_NAMES = (
    "Айгүл", "Айсұлу", "Абылғазы", "Аймағамбет", "Ақмарал", "Андрій", "Аврелія",
)


def test_packaged_selftest_covers_extended_cyrillic_names():
    from local_anonymizer.app import AppApi, _extended_cyrillic_names_self_test

    assert _extended_cyrillic_names_self_test() is True
    payload = AppApi().engine_self_test()
    assert payload["extended_cyrillic_names_ok"] is True
    assert payload["ok"] is True


def test_extended_cyrillic_resource_has_pinned_public_sources():
    from importlib.resources import files

    root = files("local_anonymizer").joinpath("assets/given_names")
    manifest = json.loads(root.joinpath("manifest.json").read_text(encoding="utf-8"))
    expected = {"айгүл", "айсұлу", "абылғазы", "аймағамбет", "ақмарал", "андрій", "аврелія"}
    assert expected <= GIVEN_NAMES
    assert manifest["mimesis_revision"] == "8897e1c879cba8ec3088246c0cf1e79d6888d0d9"
    assert manifest["mimesis_archive_sha256"] == "8be7d058fee2b716a84bf94cd3abc6aa261f787a00fe57d18b904da828aa4d57"
    assert manifest["mimesis_locales"] == ["kk", "ru", "uk"]
    assert manifest["mimesis_extended_cyrillic_spellings"] > 0
    assert manifest["spellings"] > 10283
    assert "MIT" in root.joinpath("LICENSE-MIMESIS.txt").read_text(encoding="utf-8")
    raw = root.joinpath("names.txt").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["resource_sha256"]


@pytest.mark.parametrize("given", EXTENDED_GIVEN_NAMES)
def test_extended_cyrillic_full_name_pairs_in_both_orders(given):
    source = f"{given} Леснов; Леснов {given}"
    result = Anonymizer().anonymize(source)
    assert result.text == "[ФИО-1]; [ФИО-1]"
    assert result.mapping == {"[ФИО-1]": f"{given} Леснов"}
    assert Anonymizer(disabled_categories={"ФИО"}).anonymize(source).text == source


def test_ukrainian_masculine_and_feminine_case_forms():
    source = "Андрій Крау; Крау Андрія; Крау Андрію; Крау Андрієм; Аврелія Шо; Шо Аврелії; Шо Аврелію; Шо Аврелією"
    result = Anonymizer().anonymize(source)
    assert "Андрій" not in result.text
    assert "Андрія" not in result.text
    assert "Андрію" not in result.text
    assert "Андрієм" not in result.text
    assert "Аврелія" not in result.text
    assert "Аврелії" not in result.text
    assert "Аврелію" not in result.text
    assert "Аврелією" not in result.text
    assert result.text.count("[ФИО-1]") == 4
    assert result.counts["ФИО"] == 8
    assert len(result.mapping) <= 4
    assert canonical_given_name("Андрія") == "андрій"
    assert canonical_given_name("Аврелії") == "аврелія"
    # Аврелію collides with another generated base: detect it without guessing identity.
    assert canonical_given_name("Аврелію") in {"аврелія", "аврелію"}


def test_extended_cyrillic_bare_name_and_surname_aliases_next_to_markers():
    source = "Айгүл Леснов подписала. [ФИО-7]Айгүл уточнила. [ФИО-8]Леснов"
    result = Anonymizer().anonymize(source)
    assert "[ФИО-7]Айгүл" not in result.text
    assert "[ФИО-8]Леснов" not in result.text
    assert "Айгүл уточнила" not in result.text
    assert result.text.count("[ФИО-") >= 4


@pytest.mark.parametrize("source", [
    "Айгүл",
    "Айгүл, Крау",
    "Айгүл\nКрау",
    "Айгүл\ufdd0Крау",
    "Система Айгүл",
    "Продукт «Айгүл Крау»",
])
def test_extended_cyrillic_negatives(source):
    assert "[ФИО-" not in Anonymizer().anonymize(source).text


def test_extended_cyrillic_triple_names_and_initials():
    source = "Леснов Айгүл Ардаққызы; Айгүл Ардаққызы Леснов; Леснов А. Қ.; А. Қ. Леснов"
    result = Anonymizer().anonymize(source)
    for value in ("Айгүл", "Ардаққызы", "Леснов А. Қ.", "А. Қ. Леснов"):
        assert value not in result.text
    assert result.counts["ФИО"] == 4
    assert result.text.count("[ФИО-1]") == 2


def test_extended_cyrillic_docx_split_runs_and_exact_restore(tmp_path):
    from docx import Document
    from local_anonymizer.documents import DocxProcessor

    source, output, restored = [tmp_path / name for name in ("source.docx", "out.docx", "restored.docx")]
    doc = Document()
    paragraph = doc.add_paragraph()
    paragraph.add_run("Айг").bold = True
    paragraph.add_run("үл Леснов; Леснов Айгүл")
    table = doc.add_table(rows=1, cols=2)
    paragraph = table.cell(0, 0).paragraphs[0]
    paragraph.add_run("Анд")
    paragraph.add_run("рій ")
    paragraph.add_run("Крау")
    table.cell(0, 1).text = "Крау Андрій"
    doc.save(source)
    original = source.read_bytes()

    processor = DocxProcessor()
    result = processor.anonymize(source, output)
    out = Document(output)
    assert out.paragraphs[0].text == "[ФИО-1]; [ФИО-1]"
    assert out.paragraphs[0].runs[0].bold
    assert out.tables[0].cell(0, 0).text == out.tables[0].cell(0, 1).text == "[ФИО-2]"
    processor.restore(output, restored, result.mapping, package_archive=result.package_archive)
    assert restored.read_bytes() == original == source.read_bytes()


def test_unknown_user_docx_split_runs_and_exact_restore(tmp_path):
    from docx import Document
    from local_anonymizer.documents import DocxProcessor

    source, output, restored = [tmp_path / name for name in ("account.docx", "out.docx", "restored.docx")]
    doc = Document()
    paragraph = doc.add_paragraph()
    paragraph.add_run("Неизвестный ")
    paragraph.add_run("пользователь (")
    paragraph.add_run("qzx")
    paragraph.add_run("login)")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Неизвестный пользователь"
    table.cell(0, 1).text = "(qzxother)"
    doc.save(source)
    original = source.read_bytes()

    processor = DocxProcessor()
    result = processor.anonymize(source, output)
    out = Document(output)
    assert "qzxlogin" not in out.paragraphs[0].text
    assert "[ЛОГИН-" in out.paragraphs[0].text
    assert "qzxother" not in out.tables[0].cell(0, 1).text
    processor.restore(output, restored, result.mapping, package_archive=result.package_archive)
    assert restored.read_bytes() == original == source.read_bytes()


def test_unknown_user_parenthesized_account_is_masked():
    source = "Неизвестный пользователь (qzxlogin)"
    result = Anonymizer().anonymize(source)
    assert "qzxlogin" not in result.text
    assert "[ЛОГИН-" in result.text
