from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_BZIP2, ZIP_DEFLATED, ZipFile

from lxml import etree
import pytest
from docx import Document
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml.ns import qn
from openpyxl import Workbook, load_workbook
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

from local_anonymizer.documents import (
    DocxProcessor,
    RestorationError,
    _preflight_docx_package,
    _safe_known_attribute_value,
    _sanitize_package,
)
from local_anonymizer.engine import AnonymizationResult, Anonymizer
from local_anonymizer.formats import XlsxProcessor


class _BrokenJoinEngine:
    def anonymize(self, source: str) -> AnonymizationResult:
        return AnonymizationResult(text="one-piece", mapping={})


@pytest.mark.parametrize(
    ("first", "second", "dictionary", "expected_first", "expected_second"),
    [
        ("password: Secret123!", "next", {}, "password: (удалено)", "next"),
        ("https://example.invalid/path", "next", {}, "[ССЫЛКА-1]", "next"),
        ("компания: Альфа", "next", {}, "компания: [ОРГАНИЗАЦИЯ-1]", "next"),
        ("alpha", "beta", {"alpha\ufdd0beta": "СИСТЕМА"}, "alpha", "beta"),
    ],
)
@pytest.mark.parametrize("kind", ["docx", "xlsx"])
def test_office_fragment_boundary_is_never_consumed_by_detectors(
    tmp_path: Path,
    first: str,
    second: str,
    dictionary: dict[str, str],
    expected_first: str,
    expected_second: str,
    kind: str,
) -> None:
    source = tmp_path / f"boundary.{kind}"
    output = tmp_path / f"boundary.anonymized.{kind}"
    engine = Anonymizer(user_dictionary=dictionary)
    if kind == "docx":
        document = Document()
        document.add_paragraph(first)
        document.add_paragraph(second)
        document.save(source)
        DocxProcessor(engine).anonymize(source, output)
        values = [paragraph.text for paragraph in Document(output).paragraphs]
    else:
        workbook = Workbook()
        sheet = workbook.active
        sheet["A1"], sheet["A2"] = first, second
        workbook.save(source)
        XlsxProcessor(engine).anonymize(source, output)
        sheet = load_workbook(output, data_only=False).active
        values = [sheet["A1"].value, sheet["A2"].value]

    assert values == [expected_first, expected_second]


def _package_bytes(path: Path) -> bytes:
    with ZipFile(path) as archive:
        return b"".join(archive.read(name) for name in archive.namelist())


def _inject_part(path: Path, name: str, data: bytes) -> None:
    replacement = path.with_suffix(path.suffix + ".tmp")
    with ZipFile(path) as source, ZipFile(replacement, "w", ZIP_DEFLATED) as target:
        for info in source.infolist():
            if info.filename != name:
                target.writestr(info, source.read(info.filename))
        target.writestr(name, data)
    replacement.replace(path)


def _inject_phonetic_shared_string(path: Path, phonetic_text: str) -> None:
    replacement = path.with_suffix(path.suffix + ".tmp")
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    content_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
    with ZipFile(path) as source, ZipFile(replacement, "w", ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                root = etree.fromstring(payload)
                cell = root.find(f".//{{{ns}}}c")
                cell.set("t", "s")
                inline = cell.find(f"{{{ns}}}is")
                if inline is not None:
                    cell.remove(inline)
                value = etree.SubElement(cell, f"{{{ns}}}v")
                value.text = "0"
                payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8")
            elif info.filename == "xl/_rels/workbook.xml.rels":
                root = etree.fromstring(payload)
                relationship = etree.SubElement(root, f"{{{rel_ns}}}Relationship")
                relationship.set("Id", "rIdSharedStrings")
                relationship.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings")
                relationship.set("Target", "sharedStrings.xml")
                payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8")
            elif info.filename == "[Content_Types].xml":
                root = etree.fromstring(payload)
                override = etree.SubElement(root, f"{{{content_ns}}}Override")
                override.set("PartName", "/xl/sharedStrings.xml")
                override.set("ContentType", "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml")
                payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8")
            target.writestr(info, payload)
        shared = etree.Element(f"{{{ns}}}sst", count="1", uniqueCount="1")
        item = etree.SubElement(shared, f"{{{ns}}}si")
        etree.SubElement(item, f"{{{ns}}}t").text = "safe visible text"
        phonetic = etree.SubElement(item, f"{{{ns}}}rPh", sb="0", eb="4")
        etree.SubElement(phonetic, f"{{{ns}}}t").text = phonetic_text
        target.writestr(
            "xl/sharedStrings.xml",
            etree.tostring(shared, xml_declaration=True, encoding="UTF-8"),
        )
    replacement.replace(path)


def test_xlsx_rejects_separator_collision_without_publishing(tmp_path: Path) -> None:
    source, output = tmp_path / "collision.xlsx", tmp_path / "out.xlsx"
    workbook = Workbook()
    workbook.active["A1"] = "prefix\ufdd0suffix"
    workbook.save(source)

    with pytest.raises(RuntimeError, match="разбиения"):
        XlsxProcessor().anonymize(source, output)

    assert not output.exists()


def test_xlsx_phonetic_shared_string_cannot_bypass_anonymization(tmp_path: Path) -> None:
    source, output = tmp_path / "phonetic.xlsx", tmp_path / "phonetic.anonymized.xlsx"
    workbook = Workbook()
    workbook.active["A1"] = "safe visible text"
    workbook.save(source)
    secret = "Иванов Сергей Петрович"
    _inject_phonetic_shared_string(source, secret)

    XlsxProcessor().anonymize(source, output)

    assert secret.encode("utf-8") not in _package_bytes(output)
    roundtrip = load_workbook(output, data_only=False)
    try:
        assert roundtrip.active["A1"].value == "safe visible text"
    finally:
        roundtrip.close()


def test_xlsx_inline_phonetic_annotation_cannot_bypass_anonymization(tmp_path: Path):
    source = tmp_path / "phonetic-inline.xlsx"
    output = tmp_path / "phonetic-inline.anonymized.xlsx"
    secret = "Иванов Сергей Петрович"
    workbook = Workbook()
    workbook.active["A1"] = "safe visible text"
    workbook.save(source)

    sheet_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    with ZipFile(source) as package:
        sheet = etree.fromstring(package.read("xl/worksheets/sheet1.xml"))
    inline = sheet.xpath(".//x:c[@r='A1']/x:is", namespaces={"x": sheet_ns})[0]
    phonetic = etree.SubElement(inline, f"{{{sheet_ns}}}rPh", sb="0", eb="4")
    etree.SubElement(phonetic, f"{{{sheet_ns}}}t").text = secret
    etree.SubElement(inline, f"{{{sheet_ns}}}phoneticPr", fontId="1")
    _inject_part(
        source,
        "xl/worksheets/sheet1.xml",
        etree.tostring(sheet, xml_declaration=True, encoding="UTF-8", standalone=True),
    )

    XlsxProcessor().anonymize(source, output)

    assert secret.encode("utf-8") not in _package_bytes(output)
    roundtrip = load_workbook(output, data_only=False)
    try:
        assert roundtrip.active["A1"].value == "safe visible text"
    finally:
        roundtrip.close()


def test_xlsx_core_typed_dates_are_removed_instead_of_left_empty(tmp_path: Path):
    source = tmp_path / "source.xlsx"
    output = tmp_path / "output.xlsx"
    workbook = Workbook()
    workbook.active["A1"] = "safe visible text"
    workbook.save(source)

    XlsxProcessor().anonymize(source, output)

    with ZipFile(output) as package:
        core = etree.fromstring(package.read("docProps/core.xml"))
    assert not core.xpath(
        ".//*[local-name()='created' or local-name()='modified']"
    )


def test_xlsx_rejects_wrong_anonymizer_piece_count_without_skipping_cells(tmp_path: Path) -> None:
    source, output = tmp_path / "pieces.xlsx", tmp_path / "out.xlsx"
    workbook = Workbook()
    workbook.active["A1"] = "first"
    workbook.active["A2"] = "second"
    workbook.save(source)

    with pytest.raises(RuntimeError, match="разбиения"):
        XlsxProcessor(_BrokenJoinEngine()).anonymize(source, output)

    assert not output.exists()


def test_xlsx_formula_literals_are_anonymized_and_restore_inside_formula(tmp_path: Path) -> None:
    source = tmp_path / "formulas.xlsx"
    anonymized = tmp_path / "formulas.anonymized.xlsx"
    restored = tmp_path / "formulas.restored.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet["A1"] = '=\"Иванов Сергей Петрович\"'
    sheet["A2"] = '=HYPERLINK(\"mailto:ivanov@example.com\",\"Написать Иванову\")'
    sheet["A3"] = "=SUM(1,2)"
    workbook.save(source)

    result = XlsxProcessor().anonymize(source, anonymized)
    formulas = load_workbook(anonymized, data_only=False).active
    assert formulas["A1"].value == '=\"[ФИО-1]\"'
    assert "ivanov@example.com" not in formulas["A2"].value
    assert "[ПОЧТА-1]" in formulas["A2"].value
    assert formulas["A3"].value == "=SUM(1,2)"

    unknown = XlsxProcessor().restore(anonymized, restored, result.mapping)
    restored_formulas = load_workbook(restored, data_only=False).active
    assert unknown == []
    assert restored_formulas["A1"].value == '=\"Иванов Сергей Петрович\"'
    assert "ivanov@example.com" in restored_formulas["A2"].value
    assert restored_formulas["A3"].value == "=SUM(1,2)"


def test_xlsx_dangerous_formulas_are_irreversibly_blocked_with_structured_warning(tmp_path: Path) -> None:
    source, output = tmp_path / "danger.xlsx", tmp_path / "danger.anonymized.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet["A1"] = '=WEBSERVICE(\"https://network-canary.invalid/query\")'
    sheet["A2"] = "=cmd|' /C dde-canary'!A0"
    sheet["A3"] = "='C:\\synthetic\\[external-canary.xlsx]Sheet1'!A1"
    sheet["A4"] = "=SUM(1,2)"
    workbook.save(source)

    result = XlsxProcessor().anonymize(source, output)
    out = load_workbook(output, data_only=False).active

    assert not result.ready
    blocked = [warning for warning in result.warnings if isinstance(warning, dict) and warning.get("kind") == "XLSX_FORMULA_BLOCKED"]
    assert len(blocked) == 3
    assert all(warning.get("level") == "stop" for warning in blocked)
    assert all(out[f"A{row}"].value == "[BLOCKED-FORMULA]" for row in range(1, 4))
    assert out["A4"].value == "=SUM(1,2)"
    assert not any("network-canary" in value or "dde-canary" in value or "external-canary" in value for value in result.mapping.values())
    package = _package_bytes(output)
    assert b"network-canary" not in package
    assert b"dde-canary" not in package
    assert b"external-canary" not in package


def test_xlsx_hidden_pii_surfaces_are_cleared_and_block_readiness(tmp_path: Path) -> None:
    source, output = tmp_path / "hidden.xlsx", tmp_path / "hidden.anonymized.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet["A1"] = "visible"
    sheet["B1"] = "contact"
    sheet["B1"].hyperlink = "mailto:hidden-canary@example.invalid"
    sheet.oddHeader.center.text = "Иванов Сергей Петрович"
    sheet.oddFooter.left.text = "hidden-footer@example.invalid"
    validation = DataValidation(
        type="whole",
        promptTitle="Иванов Сергей Петрович",
        prompt="hidden-prompt@example.invalid",
        errorTitle="Иванов Сергей Петрович",
        error="hidden-error@example.invalid",
    )
    validation.add(sheet["A1"])
    sheet.add_data_validation(validation)
    workbook.defined_names.add(DefinedName("HiddenCanary", attr_text='"hidden-name@example.invalid"'))
    workbook.save(source)
    _inject_part(source, "xl/externalLinks/externalLink1.xml", b"<externalLink>external-part-canary</externalLink>")

    result = XlsxProcessor().anonymize(source, output)
    out = load_workbook(output, data_only=False)
    out_sheet = out.active
    warning_kinds = {warning.get("kind") for warning in result.warnings if isinstance(warning, dict)}

    assert not result.ready
    assert {
        "XLSX_HYPERLINK",
        "XLSX_HEADER_FOOTER",
        "XLSX_DATA_VALIDATION",
        "XLSX_DEFINED_NAME",
        "XLSX_EXTERNAL_LINK",
    } <= warning_kinds
    assert out_sheet["B1"].hyperlink is None
    assert not out_sheet.oddHeader.center.text
    assert not out_sheet.oddFooter.left.text
    assert all(not item.prompt and not item.promptTitle and not item.error and not item.errorTitle for item in out_sheet.data_validations.dataValidation)
    assert not out.defined_names
    package = _package_bytes(output)
    for canary in (
        b"hidden-canary",
        b"hidden-footer",
        b"hidden-prompt",
        b"hidden-error",
        b"hidden-name",
        b"external-part-canary",
    ):
        assert canary not in package


def test_docx_risky_and_unknown_parts_fail_closed_and_external_urls_are_removed(tmp_path: Path) -> None:
    source, output = tmp_path / "parts.docx", tmp_path / "parts.anonymized.docx"
    document = Document()
    document.add_paragraph("Обычный текст")
    risky_parts = {
        "word/media/image-canary.bin": ("application/octet-stream", b"media-part-canary"),
        "customXml/item-canary.xml": ("application/xml", b"<root>custom-xml-canary</root>"),
        "word/charts/chart-canary.xml": ("application/xml", b"<chart>chart-part-canary</chart>"),
        "word/diagrams/data-canary.xml": ("application/xml", b"<diagram>diagram-part-canary</diagram>"),
        "word/userExtensions/unknown-canary.xml": ("application/xml", b"<user>unknown-part-canary</user>"),
        "word/userExtensions/hidden-canary.bin": ("application/octet-stream", b"unknown-binary-part-canary"),
        "word/afchunk/hidden-canary.html": ("text/html", b"unknown-html-part-canary"),
        "docProps/thumbnail-canary.jpeg": ("image/jpeg", b"unknown-thumbnail-part-canary"),
        "word/fonts/font-canary.odttf": ("application/vnd.openxmlformats-officedocument.obfuscatedFont", b"unknown-font-part-canary"),
    }
    for index, (name, (content_type, blob)) in enumerate(risky_parts.items()):
        part = Part(PackURI("/" + name), content_type, blob, document.part.package)
        document.part.relate_to(part, f"urn:synthetic-risk-{index}")
    document.part.relate_to("https://external-rel-canary.invalid/path", "urn:synthetic-external", is_external=True)
    document.save(source)

    result = DocxProcessor().anonymize(source, output)
    with ZipFile(output) as archive:
        names = archive.namelist()
        rel_bytes = b"".join(archive.read(name) for name in names if name.endswith(".rels"))
        package_bytes = b"".join(archive.read(name) for name in names)

    assert not result.ready
    messages = "\n".join(
        warning if isinstance(warning, str) else warning.get("message", "")
        for warning in result.warnings
    )
    for name in risky_parts:
        assert name in messages
    assert "Требуется ручная проверка" in messages
    assert b"external-rel-canary" not in rel_bytes
    assert b"custom-xml-canary" not in package_bytes
    for name, (_content_type, blob) in risky_parts.items():
        assert name not in names
        assert blob not in package_bytes
    assert "customXml/item-canary.xml" not in names
    Document(output)


def test_docx_document_variables_are_removed_and_block_readiness(tmp_path: Path) -> None:
    source, output = tmp_path / "docvars.docx", tmp_path / "docvars.anonymized.docx"
    document = Document()
    document.add_paragraph("Обычный текст")
    doc_vars = document.settings.element.makeelement(qn("w:docVars"))
    doc_var = document.settings.element.makeelement(qn("w:docVar"))
    doc_var.set(qn("w:name"), "HiddenSetting")
    doc_var.set(qn("w:val"), "SETTINGS_DOCVAR_SECRET_CANARY")
    doc_vars.append(doc_var)
    document.settings.element.append(doc_vars)
    document.save(source)

    result = DocxProcessor().anonymize(source, output)

    assert not result.ready
    assert b"SETTINGS_DOCVAR_SECRET_CANARY" not in _package_bytes(output)
    assert any("document-variables" in str(warning) for warning in result.warnings)
    Document(output)


def test_docx_unknown_relationship_part_is_removed_and_blocks_readiness(tmp_path: Path) -> None:
    source, output = tmp_path / "rogue-rels.docx", tmp_path / "rogue-rels.anonymized.docx"
    document = Document()
    document.add_paragraph("Обычный текст")
    rogue = Part(
        PackURI("/word/_rels/canary.rels"),
        "application/vnd.openxmlformats-package.relationships+xml",
        b'<evil:root xmlns:evil="urn:foreign"><evil:item secret="ROGUE_RELS_SECRET_CANARY"/></evil:root>',
        document.part.package,
    )
    document.part.relate_to(rogue, "urn:synthetic-rogue-relationship-part")
    document.save(source)

    result = DocxProcessor().anonymize(source, output)

    assert not result.ready
    assert any("word/_rels/canary.rels" in str(warning) for warning in result.warnings)
    with ZipFile(output) as archive:
        assert "word/_rels/canary.rels" not in archive.namelist()
        assert b"ROGUE_RELS_SECRET_CANARY" not in b"".join(
            archive.read(name) for name in archive.namelist()
        )
    Document(output)


def test_docx_known_relationship_part_schema_is_canonicalized(tmp_path: Path) -> None:
    source = tmp_path / "relationship-schema.docx"
    document = Document()
    document.add_paragraph("Обычный текст")
    document.save(source)
    with ZipFile(source) as archive:
        rels = etree.fromstring(archive.read("word/_rels/document.xml.rels"))
    rels.set("{urn:relationship-canary}secret", "RELS_ROOT_ATTRIBUTE_CANARY")
    rels.text = "RELS_ROOT_TEXT_CANARY"
    foreign = etree.SubElement(rels, "{urn:relationship-canary}payload")
    foreign.text = "RELS_CHILD_TEXT_CANARY"
    foreign.tail = "RELS_CHILD_TAIL_CANARY"
    first = rels[0]
    first.set("Id", "RELS_ID_CANARY")
    first.set("Type", "urn:RELS_TYPE_CANARY")
    first.set("{urn:relationship-canary}secret", "RELS_ITEM_ATTRIBUTE_CANARY")
    first.text = "RELS_ITEM_TEXT_CANARY"
    dangling = etree.SubElement(
        rels,
        "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship",
    )
    dangling.set("Id", "rId999")
    dangling.set(
        "Type",
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles",
    )
    dangling.set("Target", "RELS_TARGET_CANARY.xml")
    _inject_part(
        source,
        "word/_rels/document.xml.rels",
        etree.tostring(rels, xml_declaration=True, encoding="UTF-8", standalone=True),
    )

    warnings = _sanitize_package(source)

    assert any("foreign-xml" in warning for warning in warnings)
    assert b"RELS_" not in _package_bytes(source)
    Document(source)


def test_docx_content_types_schema_is_canonicalized(tmp_path: Path) -> None:
    source = tmp_path / "content-types-schema.docx"
    document = Document()
    document.add_paragraph("Обычный текст")
    document.save(source)
    with ZipFile(source) as archive:
        content_types = etree.fromstring(archive.read("[Content_Types].xml"))
    content_types.set("{urn:content-types-canary}secret", "CT_ROOT_ATTRIBUTE_CANARY")
    content_types.text = "CT_ROOT_TEXT_CANARY"
    foreign = etree.SubElement(content_types, "{urn:content-types-canary}payload")
    foreign.text = "CT_CHILD_TEXT_CANARY"
    first_valid = content_types[0]
    first_valid.set("{urn:content-types-canary}Extension", "CT_FOREIGN_ATTRIBUTE_CANARY")
    override = next(
        child for child in content_types
        if child.get("PartName") == "/word/styles.xml"
    )
    override.set("ContentType", "application/CT_CONTENT_TYPE_CANARY")
    _inject_part(
        source,
        "[Content_Types].xml",
        etree.tostring(content_types, xml_declaration=True, encoding="UTF-8", standalone=True),
    )

    warnings = _sanitize_package(source)

    assert any("foreign-xml" in warning for warning in warnings)
    assert b"CT_" not in _package_bytes(source)
    Document(source)


def test_docx_application_properties_are_scrubbed_and_foreign_xml_blocks(tmp_path: Path) -> None:
    source = tmp_path / "app-properties.docx"
    document = Document()
    document.add_paragraph("Обычный текст")
    document.save(source)
    with ZipFile(source) as archive:
        app = etree.fromstring(archive.read("docProps/app.xml"))
    company_ns = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
    company = app.find(f"{{{company_ns}}}Company")
    assert company is not None
    company.text = "APP_STANDARD_COMPANY_CANARY"
    app.set("{urn:app-properties-canary}secret", "APP_ROOT_ATTRIBUTE_CANARY")
    foreign = etree.SubElement(app, "{urn:app-properties-canary}payload")
    foreign.text = "APP_FOREIGN_TEXT_CANARY"
    _inject_part(
        source,
        "docProps/app.xml",
        etree.tostring(app, xml_declaration=True, encoding="UTF-8", standalone=True),
    )

    warnings = _sanitize_package(source)

    assert any("foreign-xml" in warning for warning in warnings)
    assert b"APP_" not in _package_bytes(source)
    Document(source)


def test_docx_foreign_xml_in_allowed_part_is_removed_and_blocks_restore(tmp_path: Path) -> None:
    source, anonymized = tmp_path / "foreign-settings.docx", tmp_path / "foreign-settings.anonymized.docx"
    restored = tmp_path / "existing.docx"
    document = Document()
    document.add_paragraph("[ФИО-1]")
    foreign = document.settings.element.makeelement("{urn:foreign-canary}payload")
    foreign.set("{urn:foreign-canary}secret", "FOREIGN_XML_ATTRIBUTE_CANARY")
    foreign.text = "FOREIGN_XML_TEXT_CANARY"
    document.settings.element.append(foreign)
    unknown_wml = document.settings.element.makeelement(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}secretPayload"
    )
    unknown_wml.set(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}secretAttribute",
        "UNKNOWN_WML_ATTRIBUTE_CANARY",
    )
    unknown_wml.text = "UNKNOWN_WML_TEXT_CANARY"
    document.settings.element.append(unknown_wml)
    document.save(source)

    result = DocxProcessor().anonymize(source, anonymized)

    assert not result.ready
    assert any("foreign-xml" in str(warning) for warning in result.warnings)
    assert b"FOREIGN_XML_" not in _package_bytes(anonymized)
    assert b"UNKNOWN_WML_" not in _package_bytes(anonymized)
    previous = Document()
    previous.add_paragraph("PREVIOUS DESTINATION")
    previous.save(restored)
    previous_bytes = restored.read_bytes()
    with pytest.raises(RestorationError, match="неподдерживаем"):
        DocxProcessor().restore(source, restored, {"[ФИО-1]": "Иванов Сергей Петрович"})
    assert restored.read_bytes() == previous_bytes


def test_docx_unknown_wml_attribute_is_removed_and_blocks_readiness(tmp_path: Path) -> None:
    source, output = tmp_path / "unknown-wml-attribute.docx", tmp_path / "out.docx"
    document = Document()
    document.add_paragraph("Обычный текст")
    zoom = document.settings.element.find(qn("w:zoom"))
    assert zoom is not None
    zoom.set(qn("w:secretAttribute"), "UNKNOWN_WML_ATTRIBUTE_ONLY_CANARY")
    document.save(source)

    result = DocxProcessor().anonymize(source, output)

    assert not result.ready
    assert any("foreign-xml" in str(warning) for warning in result.warnings)
    assert b"UNKNOWN_WML_ATTRIBUTE_ONLY_CANARY" not in _package_bytes(output)
    Document(output)


def test_docx_direct_text_and_tail_on_structural_wml_are_removed_and_block_readiness(
    tmp_path: Path,
) -> None:
    source, output = tmp_path / "structural-text.docx", tmp_path / "out.docx"
    document = Document()
    document.add_paragraph("Обычный текст")
    settings = document.settings.element
    settings.text = "STRUCTURAL_WML_ROOT_TEXT_CANARY"
    zoom = settings.find(qn("w:zoom"))
    assert zoom is not None
    zoom.text = "STRUCTURAL_WML_CHILD_TEXT_CANARY"
    zoom.tail = "STRUCTURAL_WML_CHILD_TAIL_CANARY"
    misplaced_text = etree.SubElement(settings, qn("w:t"))
    misplaced_text.text = "STRUCTURAL_WML_MISPLACED_TEXT_CANARY"
    document.save(source)

    result = DocxProcessor().anonymize(source, output)

    assert not result.ready
    assert any("foreign-xml" in str(warning) for warning in result.warnings)
    assert b"STRUCTURAL_WML_" not in _package_bytes(output)
    Document(output)


def test_docx_known_wml_names_in_wrong_context_are_removed_and_block_readiness(
    tmp_path: Path,
) -> None:
    source, output = tmp_path / "wrong-context.docx", tmp_path / "out.docx"
    document = Document()
    paragraph = document.add_paragraph("Обычный текст")
    paragraph._p.set(qn("w:author"), "KNOWN_ATTRIBUTE_WRONG_CONTEXT_CANARY")
    misplaced_name = etree.SubElement(document.element.body, qn("w:name"))
    misplaced_name.set(qn("w:val"), "KNOWN_NAMES_WRONG_CONTEXT_CANARY")
    document.save(source)

    result = DocxProcessor().anonymize(source, output)

    assert not result.ready
    assert any("foreign-xml" in str(warning) for warning in result.warnings)
    package = _package_bytes(output)
    assert b"KNOWN_NAMES_WRONG_CONTEXT_CANARY" not in package
    assert b"KNOWN_ATTRIBUTE_WRONG_CONTEXT_CANARY" not in package
    Document(output)


def test_docx_known_string_fields_are_contextual_and_canonical(tmp_path: Path) -> None:
    source, output = tmp_path / "known-string-fields.docx", tmp_path / "out.docx"
    document = Document()
    document.add_paragraph("Visible content")
    document.save(source)

    def mutate(name: str, data: bytes) -> bytes:
        root = etree.fromstring(data)
        if name == "word/document.xml":
            body = root.find(qn("w:body"))
            paragraph = root.find(".//" + qn("w:p"))
            assert body is not None and paragraph is not None
            for local, attr, value in (
                ("zoom", "val", "WRONG_ZOOM_VAL_CANARY"),
                ("rFonts", "ascii", "WRONG_RFONT_ASCII_CANARY"),
                ("lang", "val", "WRONG_LANG_VAL_CANARY"),
                ("color", "val", "WRONG_COLOR_VAL_CANARY"),
            ):
                child = etree.SubElement(body, qn(f"w:{local}"))
                child.set(qn(f"w:{attr}"), value)
            compat = etree.SubElement(body, qn("w:compatSetting"))
            compat.set(qn("w:name"), "compatibilityMode")
            compat.set(qn("w:val"), "WRONG_COMPAT_VAL_CANARY")
            paragraph.set(qn("w:styleId"), "WRONG_P_STYLEID_CANARY")
            paragraph.set(qn("w:name"), "WRONG_P_NAME_CANARY")
            paragraph.set(qn("w:val"), "WRONG_P_VAL_CANARY")
            paragraph.set(qn("w:rsidR"), "CORRECT_CONTEXT_RSID_CANARY")
            paragraph.find(qn("w:r") + "/" + qn("w:t")).set(
                "{http://www.w3.org/XML/1998/namespace}space", "XML_SPACE_VALUE_CANARY"
            )
            p_pr = etree.Element(qn("w:pPr"))
            jc = etree.SubElement(p_pr, qn("w:jc"))
            jc.set(qn("w:val"), "CORRECT_CONTEXT_JC_VAL_CANARY")
            paragraph.insert(0, p_pr)
            hyperlink = etree.SubElement(paragraph, qn("w:hyperlink"))
            hyperlink.set(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id",
                "RELATIONSHIP_ID_VALUE_CANARY",
            )
            hyperlink_run = etree.SubElement(hyperlink, qn("w:r"))
            hyperlink_text = etree.SubElement(hyperlink_run, qn("w:t"))
            hyperlink_text.text = "safe link label"
        elif name == "word/styles.xml":
            style = root.find(qn("w:style"))
            assert style is not None
            style.set(qn("w:styleId"), "VALID_CONTEXT_STYLE_ID_CANARY")
            style_name = style.find(qn("w:name"))
            assert style_name is not None
            style_name.set(qn("w:val"), "VALID_CONTEXT_STYLE_NAME_CANARY")
        elif name == "word/theme/theme1.xml":
            root.set("name", "THEME_NAME_VALUE_CANARY")
            latin = root.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}latin")
            assert latin is not None
            latin.set("typeface", "VALID_CONTEXT_TYPEFACE_CANARY")
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    for part_name in (
        "word/document.xml",
        "word/styles.xml",
        "word/theme/theme1.xml",
    ):
        with ZipFile(source) as package:
            part_data = package.read(part_name)
        _inject_part(source, part_name, mutate(part_name, part_data))
    result = DocxProcessor().anonymize(source, output)
    assert result.ready is False
    assert any("foreign-xml" in str(item) for item in result.warnings)
    package = _package_bytes(output)
    assert b"_CANARY" not in package
    Document(output)


def test_docx_unknown_word_xml_root_is_replaced_and_blocks_readiness(tmp_path: Path) -> None:
    source = tmp_path / "unknown-root.docx"
    document = Document()
    document.add_paragraph("Обычный текст")
    document.save(source)
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    root = etree.Element(f"{{{namespace}}}secretRoot", nsmap={"w": namespace})
    root.text = "UNKNOWN_WML_ROOT_CANARY"
    _inject_part(
        source,
        "word/settings.xml",
        etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True),
    )

    warnings = _sanitize_package(source)

    assert any("foreign-xml" in warning for warning in warnings)
    assert b"UNKNOWN_WML_ROOT_CANARY" not in _package_bytes(source)
    Document(source)


def test_docx_malformed_xml_is_replaced_without_retaining_payload(tmp_path: Path) -> None:
    source = tmp_path / "malformed.docx"
    document = Document()
    document.add_paragraph("Visible")
    document.save(source)
    _inject_part(source, "word/settings.xml", b'<w:settings xmlns:w="urn:broken">SECRET_MALFORMED')

    warnings = _sanitize_package(source)

    assert any("invalid-xml" in warning for warning in warnings)
    assert b"SECRET_MALFORMED" not in _package_bytes(source)
    Document(source)


def test_docx_untrusted_numeric_attribute_value_is_removed_and_blocks_readiness(tmp_path: Path) -> None:
    source, output = tmp_path / "numeric-channel.docx", tmp_path / "out.docx"
    document = Document()
    document.add_paragraph("Visible")
    zoom = document.settings.element.find(qn("w:zoom"))
    assert zoom is not None
    zoom.set(qn("w:percent"), "654321")
    document.save(source)

    result = DocxProcessor().anonymize(source, output)

    assert not result.ready
    assert b"79161234567" not in _package_bytes(output)


def test_trusted_word_fixture_values_are_scoped_to_their_part() -> None:
    assert _safe_known_attribute_value("word/settings.xml", "zoom", "percent", "100")
    assert not _safe_known_attribute_value("word/document.xml", "zoom", "percent", "100")


def test_docx_noncanonical_relationship_target_is_removed(tmp_path: Path) -> None:
    source = tmp_path / "relationship-target.docx"
    document = Document()
    document.add_paragraph("Visible")
    document.save(source)
    with ZipFile(source) as archive:
        root = etree.fromstring(archive.read("word/_rels/document.xml.rels"))
    styles = next(child for child in root if child.get("Target") == "styles.xml")
    styles.set("Target", "PERSONAL_CANARY/../styles.xml")
    _inject_part(source, "word/_rels/document.xml.rels", etree.tostring(root))

    warnings = _sanitize_package(source)

    assert any("noncanonical-relationship" in warning for warning in warnings)
    assert b"PERSONAL_CANARY" not in _package_bytes(source)
    Document(source)


def test_docx_relationship_ids_are_canonicalized_with_consumer_references(tmp_path: Path) -> None:
    source = tmp_path / "relationship-id-channel.docx"
    document = Document()
    document.add_paragraph("Visible")
    document.sections[0].header.paragraphs[0].text = "Header"
    document.save(source)

    rel_part = "word/_rels/document.xml.rels"
    with ZipFile(source) as package:
        rel_root = etree.fromstring(package.read(rel_part))
        document_root = etree.fromstring(package.read("word/document.xml"))
    header_rel = next(rel for rel in rel_root if rel.get("Target", "").startswith("header"))
    old_id = header_rel.get("Id")
    assert old_id
    attacker_id = "rId987654321"
    header_rel.set("Id", attacker_id)
    references = document_root.xpath(
        "//@r:id",
        namespaces={"r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"},
    )
    assert old_id in references
    for element in document_root.iter():
        attr = f"{{http://schemas.openxmlformats.org/officeDocument/2006/relationships}}id"
        if element.get(attr) == old_id:
            element.set(attr, attacker_id)
    _inject_part(source, rel_part, etree.tostring(rel_root))
    _inject_part(source, "word/document.xml", etree.tostring(document_root))

    warnings = _sanitize_package(source)

    with ZipFile(source) as package:
        rel_root = etree.fromstring(package.read(rel_part))
        document_root = etree.fromstring(package.read("word/document.xml"))
    relationship_ids = {rel.get("Id") for rel in rel_root}
    referenced_ids = set(document_root.xpath(
        "//@r:id",
        namespaces={"r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"},
    ))
    assert attacker_id not in relationship_ids
    assert attacker_id not in referenced_ids
    assert referenced_ids <= relationship_ids
    assert relationship_ids == {f"rId{index}" for index in range(1, len(relationship_ids) + 1)}
    assert warnings == []
    assert Document(source).sections[0].header.paragraphs[0].text == "Header"



def test_docx_equivalent_duplicate_relationships_are_deduplicated_deterministically(tmp_path: Path) -> None:
    first = tmp_path / "relationship-duplicates-a.docx"
    second = tmp_path / "relationship-duplicates-b.docx"
    document = Document()
    document.add_paragraph("Visible")
    document.sections[0].header.paragraphs[0].text = "Header"
    document.save(first)
    second.write_bytes(first.read_bytes())

    rel_part = "word/_rels/document.xml.rels"
    document_part = "word/document.xml"
    office_rel_id = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

    def add_equivalent_relationships(path: Path, ids: tuple[str, str]) -> None:
        with ZipFile(path) as package:
            rel_root = etree.fromstring(package.read(rel_part))
            document_root = etree.fromstring(package.read(document_part))
        header_rel = next(rel for rel in rel_root if rel.get("Target", "").startswith("header"))
        original_id = header_rel.get("Id")
        assert original_id
        duplicate = etree.fromstring(etree.tostring(header_rel))
        header_rel.set("Id", ids[0])
        duplicate.set("Id", ids[1])
        if ids[0] == "rId123456789":
            attributes = dict(header_rel.attrib)
            header_rel.attrib.clear()
            for name in ("Target", "Type", "Id"):
                header_rel.set(name, attributes[name])
            header_rel.text = "  "
            header_rel.tail = "\n    "
        rel_root.insert(rel_root.index(header_rel) + 1, duplicate)
        for element in document_root.iter():
            if element.get(office_rel_id) == original_id:
                element.set(office_rel_id, "rId987654321")
        _inject_part(path, rel_part, etree.tostring(rel_root))
        _inject_part(path, document_part, etree.tostring(document_root))

    add_equivalent_relationships(first, ("rId987654321", "rId123456789"))
    add_equivalent_relationships(second, ("rId123456789", "rId987654321"))

    assert _sanitize_package(first) == []
    assert _sanitize_package(second) == []

    with ZipFile(first) as package:
        first_rels = etree.fromstring(package.read(rel_part))
        first_document = etree.fromstring(package.read(document_part))
    with ZipFile(second) as package:
        second_rels = etree.fromstring(package.read(rel_part))
        second_document = etree.fromstring(package.read(document_part))
    first_header_rels = [rel for rel in first_rels if rel.get("Target", "").startswith("header")]
    second_header_rels = [rel for rel in second_rels if rel.get("Target", "").startswith("header")]
    assert len(first_header_rels) == len(second_header_rels) == 1
    assert etree.tostring(first_rels) == etree.tostring(second_rels)
    assert etree.tostring(first_document) == etree.tostring(second_document)
    assert Document(first).sections[0].header.paragraphs[0].text == "Header"
    assert Document(second).sections[0].header.paragraphs[0].text == "Header"



def test_docx_orphan_content_type_override_is_removed(tmp_path: Path) -> None:
    source = tmp_path / "orphan-content-type.docx"
    document = Document()
    document.add_paragraph("Visible")
    document.save(source)
    namespace = "http://schemas.openxmlformats.org/package/2006/content-types"
    with ZipFile(source) as archive:
        root = etree.fromstring(archive.read("[Content_Types].xml"))
    orphan = etree.SubElement(root, f"{{{namespace}}}Override")
    orphan.set("PartName", "/PERSONAL_CANARY.xml")
    orphan.set("ContentType", "application/xml")
    _inject_part(source, "[Content_Types].xml", etree.tostring(root))

    warnings = _sanitize_package(source)

    assert any("orphan-content-type" in warning for warning in warnings)
    assert b"PERSONAL_CANARY" not in _package_bytes(source)
    Document(source)


def test_docx_duplicate_zip_member_is_rejected_before_processing(tmp_path: Path) -> None:
    source = tmp_path / "duplicate.docx"
    document = Document()
    document.add_paragraph("Visible")
    document.save(source)
    with ZipFile(source, "a", ZIP_DEFLATED) as archive:
        archive.writestr("word/settings.xml", b"DUPLICATE_SECRET")

    with pytest.raises(ValueError, match="повторяющиеся ZIP-части"):
        _preflight_docx_package(source)


def test_docx_bzip2_member_is_rejected_and_sanitized_output_is_deflated(tmp_path: Path) -> None:
    source = tmp_path / "bzip2.docx"
    document = Document()
    document.add_paragraph("Visible")
    document.save(source)
    with ZipFile(source, "r") as package:
        parts = {info.filename: package.read(info.filename) for info in package.infolist()}
    with ZipFile(source, "w", compression=ZIP_BZIP2) as package:
        for name, data in parts.items():
            package.writestr(name, data)

    with pytest.raises(ValueError, match="метод сжатия"):
        _preflight_docx_package(source)


def test_docx_duplicate_content_type_and_relationship_ids_are_rejected(tmp_path: Path) -> None:
    content_types = tmp_path / "duplicate-content-types.docx"
    document = Document()
    document.add_paragraph("Visible")
    document.save(content_types)
    with ZipFile(content_types, "r") as package:
        root = etree.fromstring(package.read("[Content_Types].xml"))
    root.append(etree.fromstring(etree.tostring(root[0])))
    _inject_part(content_types, "[Content_Types].xml", etree.tostring(root))
    with pytest.raises(ValueError, match="Content Types"):
        _preflight_docx_package(content_types)

    relationships = tmp_path / "duplicate-relationships.docx"
    document.save(relationships)
    with ZipFile(relationships, "r") as package:
        root = etree.fromstring(package.read("word/_rels/document.xml.rels"))
    root.append(etree.fromstring(etree.tostring(root[0])))
    _inject_part(relationships, "word/_rels/document.xml.rels", etree.tostring(root))
    with pytest.raises(ValueError, match="повторяющиеся Id связей"):
        _preflight_docx_package(relationships)


def test_docx_backslash_member_name_is_rejected_from_raw_zip_headers(tmp_path: Path) -> None:
    source = tmp_path / "backslash.docx"
    document = Document()
    document.add_paragraph("Visible")
    document.save(source)
    raw = source.read_bytes()
    assert raw.count(b"word/styles.xml") == 2
    source.write_bytes(raw.replace(b"word/styles.xml", b"word\\styles.xml"))

    with pytest.raises(ValueError, match="небезопасное имя ZIP-части"):
        _preflight_docx_package(source)


def test_docx_unsafe_zip_member_name_is_rejected_before_processing(tmp_path: Path) -> None:
    source = tmp_path / "unsafe-name.docx"
    document = Document()
    document.add_paragraph("Visible")
    document.save(source)
    with ZipFile(source, "a", ZIP_DEFLATED) as archive:
        archive.writestr("../PERSONAL_CANARY.xml", b"secret")

    with pytest.raises(ValueError, match="небезопасное имя"):
        _preflight_docx_package(source)


def test_docx_word_generated_extension_ids_are_scrubbed_without_blocking(tmp_path: Path) -> None:
    source = tmp_path / "word-extensions.docx"
    output = tmp_path / "word-extensions.anonymized.docx"
    document = Document()
    document.add_paragraph("Обычный список", style="List Number")
    settings = document.settings.element
    doc_id = settings.makeelement("{http://schemas.microsoft.com/office/word/2012/wordml}docId")
    doc_id.set(
        "{http://schemas.microsoft.com/office/word/2012/wordml}val",
        "{8B6B3A20-4CE8-42EE-9DCA-D5ADA1089295}",
    )
    settings.append(doc_id)
    numbering = document.part.numbering_part.element
    abstract_num = numbering.find(qn("w:abstractNum"))
    num = numbering.find(qn("w:num"))
    assert abstract_num is not None
    assert num is not None
    abstract_num.set(
        "{http://schemas.microsoft.com/office/word/2012/wordml}restartNumberingAfterBreak",
        "0",
    )
    num.set(
        "{http://schemas.microsoft.com/office/word/2016/wordml/cid}durableId",
        "1665469191",
    )
    document.save(source)

    result = DocxProcessor().anonymize(source, output)

    assert result.ready
    assert not result.warnings
    package = _package_bytes(output)
    assert b"8B6B3A20-4CE8-42EE-9DCA-D5ADA1089295" not in package
    assert b"1665469191" not in package
    reopened = Document(output)
    assert reopened.paragraphs[0].style.name == "List Number"


def test_docx_nonempty_builtin_bibliography_is_removed_and_blocks_readiness(tmp_path: Path) -> None:
    source, output = tmp_path / "bibliography.docx", tmp_path / "bibliography.anonymized.docx"
    document = Document()
    document.add_paragraph("Обычный текст")
    document.save(source)
    bibliography = b'''<?xml version="1.0" encoding="UTF-8"?>
    <b:Sources xmlns:b="http://schemas.openxmlformats.org/officeDocument/2006/bibliography"
               SelectedStyle="/APA.XSL" StyleName="APA">
      <b:Source><b:Tag>bibliography-content-canary</b:Tag></b:Source>
    </b:Sources>'''
    _inject_part(source, "customXml/item1.xml", bibliography)

    result = DocxProcessor().anonymize(source, output)
    with ZipFile(output) as archive:
        names = archive.namelist()
        package = b"".join(archive.read(name) for name in names)

    assert not result.ready
    assert any("customXml/item1.xml" in str(warning) for warning in result.warnings)
    assert b"bibliography-content-canary" not in package
    assert not any(name.startswith("customXml/") for name in names)
    Document(output)


def test_docx_restore_accepts_word_default_empty_note_separator_parts(tmp_path: Path) -> None:
    source, output = tmp_path / "word-edited.docx", tmp_path / "restored.docx"
    document = Document()
    document.add_paragraph("[ФИО-1]")
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    for kind in ("footnote", "endnote"):
        xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <w:{kind}s xmlns:w="{namespace}">
          <w:{kind} w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:{kind}>
          <w:{kind} w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:{kind}>
        </w:{kind}s>'''.encode("utf-8")
        part = Part(
            PackURI(f"/word/{kind}s.xml"),
            "application/xml",
            xml,
            document.part.package,
        )
        document.part.relate_to(
            part,
            f"http://schemas.openxmlformats.org/officeDocument/2006/relationships/{kind}s",
        )
    document.save(source)

    unknown = DocxProcessor().restore(
        source, output, {"[ФИО-1]": "Иванов Сергей Петрович"}
    )

    assert unknown == []
    assert Document(output).paragraphs[0].text == "Иванов Сергей Петрович"


@pytest.mark.parametrize(
    "part_name",
    ["word/footnotes.xml", "word/endnotes.xml", "word/glossary/document.xml"],
)
def test_docx_restore_rejects_unsupported_text_parts_without_publishing(
    tmp_path: Path, part_name: str
) -> None:
    source, output = tmp_path / "edited.docx", tmp_path / "existing.docx"
    document = Document()
    document.add_paragraph("Обычный текст")
    part = Part(
        PackURI("/" + part_name),
        "application/xml",
        b'<w:root xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:t>[NAME-1]</w:t></w:root>',
        document.part.package,
    )
    document.part.relate_to(part, "urn:synthetic-unsupported-text-part")
    document.save(source)
    previous = Document()
    previous.add_paragraph("PREVIOUS DESTINATION")
    previous.save(output)
    previous_bytes = output.read_bytes()

    with pytest.raises(RestorationError, match="неподдерживаем"):
        DocxProcessor().restore(source, output, {"[NAME-1]": "SENSITIVE-CANARY-NAME"})

    assert output.read_bytes() == previous_bytes
    assert not any(path.name.startswith(f".{output.stem}-") for path in tmp_path.iterdir())
    assert list(tmp_path.rglob("*.sanitize.tmp")) == []


def test_docx_sanitize_replace_failure_preserves_destination_and_erases_plaintext_temp(
    tmp_path: Path, monkeypatch
) -> None:
    source, output = tmp_path / "edited.docx", tmp_path / "existing.docx"
    edited = Document(); edited.add_paragraph("[ФИО-1]"); edited.save(source)
    previous = Document(); previous.add_paragraph("PREVIOUS DESTINATION"); previous.save(output)
    previous_bytes = output.read_bytes()

    def fail_replace(_source, _destination):
        raise OSError("sanitize replace fault")

    monkeypatch.setattr("local_anonymizer.documents.os.replace", fail_replace)
    with pytest.raises(OSError, match="sanitize replace fault"):
        DocxProcessor().restore(source, output, {"[ФИО-1]": "SENSITIVE-CANARY-NAME"})

    assert output.read_bytes() == previous_bytes
    assert list(tmp_path.rglob("*.sanitize.tmp")) == []
    assert not any(
        b"SENSITIVE-CANARY-NAME" in _package_bytes(path)
        for path in tmp_path.rglob("*.docx")
        if path != source and path != output
    )


def test_docx_restore_keeps_literal_fdd0_paragraph_boundaries_and_formatting(tmp_path: Path) -> None:
    source, output = tmp_path / "edited.docx", tmp_path / "restored.docx"
    document = Document()
    first = document.add_paragraph()
    first.add_run("first\ufdd0INJECTED").bold = True
    document.add_paragraph("[ФИО-1]")
    document.add_paragraph("[ZZ-2] [AA-1] [ZZ-2]")
    document.save(source)

    unknown = DocxProcessor().restore(source, output, {"[ФИО-1]": "Иванов Сергей Петрович"})

    restored = Document(output)
    assert [paragraph.text for paragraph in restored.paragraphs] == [
        "first\ufdd0INJECTED",
        "Иванов Сергей Петрович",
        "[ZZ-2] [AA-1] [ZZ-2]",
    ]
    assert restored.paragraphs[0].runs[0].bold is True
    assert unknown == ["[AA-1]", "[ZZ-2]"]
