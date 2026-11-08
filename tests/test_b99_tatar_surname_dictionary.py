"""B98/B99: generic public surnames and Russian-written naming forms."""
import json

from local_anonymizer.engine import Anonymizer
from local_anonymizer.surnames import SURNAMES, is_surname


TATAR_SURNAMES = ("Хабибуллин", "Габдуллин", "Нуриев", "Гарипов", "Шагиев", "Фатхутдинов")


def test_generic_surname_resource_is_pinned_and_cyrillic():
    from importlib.resources import files

    root = files("local_anonymizer").joinpath("assets/given_names")
    manifest = json.loads(root.joinpath("manifest.json").read_text(encoding="utf-8"))
    assert {"хабибуллин", "габдуллин", "нуриев", "гарипов", "шагиев", "фатхутдинов"} <= SURNAMES
    assert "габдуллина" in SURNAMES
    assert manifest["surnames_source_sha256"] == "8c7a263eb0e1886f9482f01fd0f2d22e5132d51ff45266e3b592902abc8f8c6d"
    assert manifest["surname_min_count"] == 5
    assert manifest["surname_spellings"] > 50000
    assert manifest["surname_normalized_keys"] == len(SURNAMES)
    assert manifest["surname_resource_sha256"]
    assert is_surname("Хабибуллину")
    assert is_surname("Габдуллиной")


def test_tatar_names_and_surnames_in_russian_script_both_orders():
    source = "Айрат Хабибуллин; Хабибуллин Айрат; Гузель Габдуллина; Габдуллина Гузель"
    result = Anonymizer().anonymize(source)
    assert result.text == "[ФИО-1]; [ФИО-1]; [ФИО-2]; [ФИО-2]"
    assert Anonymizer(disabled_categories={"ФИО"}).anonymize(source).text == source


def test_inflected_tatar_surname_and_given_name():
    source = "Айрат Хабибуллин; Хабибуллину Айрату; Гузель Габдуллина; Габдуллиной Гузель"
    result = Anonymizer().anonymize(source)
    assert "Хабибуллину" not in result.text
    assert "Габдуллиной" not in result.text
    assert result.counts["ФИО"] == 4


def test_known_surname_anchors_capitalized_given_name_outside_dictionary():
    source = "Участники: Бронт Хабибуллин; Хабибуллин Бронт"
    result = Anonymizer().anonymize(source)
    assert result.text == "Участники: [ФИО-1]; [ФИО-1]"
    assert "[ФИО-" not in Anonymizer().anonymize("Бронт Хабибуллин").text


def test_common_legal_geographic_and_technical_phrases_are_not_people():
    for source in (
        "Российская Федерация", "Субъект Российской", "Московский Тракт",
        "Предметов Залога", "Корневой Центр", "Российской Федерации",
    ):
        assert "[ФИО-" not in Anonymizer().anonymize(source).text


def test_organization_and_common_noun_pairs_are_not_people_with_role_context():
    for source in (
        "Исполнитель работ: Фирма Михайлова и партнёры.",
        "Ответственный: Политика Москва",
        "Ответственный: Школа Секретарь",
        "Ответственный: Город Москва",
    ):
        assert "[ФИО-" not in Anonymizer().anonymize(source).text


def test_role_labelled_single_surname_without_global_prose_match():
    source = "Ответственный: Хабибуллин; Исполнитель: Габдуллиной. Система Хабибуллин. Проект Нуриев."
    result = Anonymizer().anonymize(source)
    assert "Ответственный: Хабибуллин" not in result.text
    assert "Исполнитель: Габдуллиной" not in result.text
    assert "Система Хабибуллин" in result.text
    assert "Проект Нуриев" in result.text


def test_tatar_surname_docx_split_runs_and_exact_restore(tmp_path):
    from docx import Document
    from local_anonymizer.documents import DocxProcessor

    source, output, restored = [tmp_path / name for name in ("source.docx", "out.docx", "restored.docx")]
    doc = Document()
    paragraph = doc.add_paragraph()
    paragraph.add_run("Ай")
    paragraph.add_run("рат Хаби")
    paragraph.add_run("буллин")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Ответственный:"
    paragraph = table.cell(0, 1).paragraphs[0]
    paragraph.add_run("Габдул")
    paragraph.add_run("линой")
    doc.save(source)
    original = source.read_bytes()

    processor = DocxProcessor()
    result = processor.anonymize(source, output)
    out = Document(output)
    assert out.paragraphs[0].text == "[ФИО-1]"
    assert "Габдуллиной" not in out.tables[0].cell(0, 1).text
    processor.restore(output, restored, result.mapping, package_archive=result.package_archive)
    assert restored.read_bytes() == original == source.read_bytes()
