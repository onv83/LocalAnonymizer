"""Synthetic Word rewrite regressions; no customer artifacts are used."""
import base64
import json
from hashlib import sha256
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from docx import Document
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree

from local_anonymizer.documents import _sanitize_package, _scrub_unknown_docx_xml
from local_anonymizer.service import AnonymizerService


def test_portable_pair_records_hash_validated_anonymized_format_core(tmp_path):
    source = tmp_path / "baseline.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.save(source)

    service = AnonymizerService(tmp_path / "library")
    document_id = service.import_file(source)
    service.anonymize(document_id)
    pair = service.export_pair(document_id, tmp_path / "portable.docx", confirmation=True)

    payload = AnonymizerService._read_recovery_file(pair["recovery_path"])
    baseline = payload["bundle"]["package_archive"]["anonymized_format_core"]
    assert set(baseline) == {"word/styles.xml", "word/numbering.xml"}
    for part in baseline.values():
        data = base64.b64decode(part["data_b64"], validate=True)
        assert sha256(data).hexdigest() == part["sha256"]


def test_portable_restore_rejects_tampered_anonymized_format_core(tmp_path):
    source = tmp_path / "baseline-tampered.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.save(source)
    service = AnonymizerService(tmp_path / "library")
    document_id = service.import_file(source)
    service.anonymize(document_id)
    pair = service.export_pair(document_id, tmp_path / "portable.docx", confirmation=True)

    def tamper(archive):
        archive["anonymized_format_core"]["word/styles.xml"]["data_b64"] = base64.b64encode(b"bad").decode()

    _replace_portable_snapshot(pair["recovery_path"], tamper)
    from local_anonymizer.documents import RestorationError
    with pytest.raises(RestorationError):
        service.restore_from_pair(pair["anonymized_path"], tmp_path / "restored.docx")


def _replace_portable_snapshot(recovery_path, replace):
    """Replace only synthetic donor bytes and recompute the portable checksum."""
    from local_anonymizer.service import _canonical_json, _recovery_checksum

    payload = json.loads(recovery_path.read_text(encoding="utf-8"))
    archive = payload["bundle"]["package_archive"]
    replace(archive)
    payload["checksum_sha256"] = _recovery_checksum(payload)
    recovery_path.write_bytes(_canonical_json(payload))


def _child(parent, local, **attributes):
    element = OxmlElement(f"w:{local}")
    for key, value in attributes.items():
        element.set(qn(f"w:{key}"), value)
    parent.append(element)
    return element


def _format_paragraph(paragraph):
    properties = paragraph.get_or_add_pPr()
    for name in ("keepLines", "widowControl", "pageBreakBefore"):
        _child(properties, name, val="0")
    _child(properties, "spacing", before="120", after="160", line="276", lineRule="auto")
    run = paragraph.find(qn("w:r"))
    properties = run.get_or_add_rPr()
    _child(properties, "rFonts", ascii="Arial", hAnsi="Arial")
    _child(properties, "color", val="123ABC")
    _child(properties, "sz", val="23")


def _word_rewrite(path):
    document = Document(path)
    # A genuinely new paragraph ensures this is semantic recovery, not exact replay.
    paragraph = document.add_paragraph("Edited [ФИО-1]")
    _format_paragraph(paragraph._p)
    body_paragraph = paragraph
    for container in (document.sections[0].header, document.sections[0].footer):
        paragraph = container.paragraphs[0]
        paragraph.text = "Visible [ФИО-1]"
        _format_paragraph(paragraph._p)
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "Visible cell"
    _child(table.rows[0]._tr.get_or_add_trPr(), "cantSplit", val="1")
    _child(table._tbl.tblPr, "jc", val="center")
    borders = _child(table._tbl.tblPr, "tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        _child(borders, edge, val="single", sz="8", space="0", color="123ABC")
    # These identifiers/targets must remain inert metadata, not expand trust.
    _child(body_paragraph._p, "bookmarkStart", id="7", name="SyntheticBookmark")
    _child(body_paragraph._p, "bookmarkEnd", id="7")
    link = _child(body_paragraph._p, "hyperlink", anchor="SyntheticBookmark")
    _child(_child(link, "r"), "t").text = "Visible link"
    _child(_child(body_paragraph._p, "r"), "fldChar", fldCharType="begin")
    _child(_child(body_paragraph._p, "r"), "instrText").text = " DATE "
    _child(_child(body_paragraph._p, "r"), "fldChar", fldCharType="separate")
    _child(_child(body_paragraph._p, "r"), "t").text = "Visible field result"
    _child(_child(body_paragraph._p, "r"), "fldChar", fldCharType="end")
    _child(document.sections[0]._sectPr, "pgNumType", start="1")
    _child(table.rows[0]._tr.get_or_add_trPr(), "tblHeader", val="1")
    for container in (document.sections[0].header, document.sections[0].footer):
        header_paragraph = container.paragraphs[0]
        _child(header_paragraph._p.get_or_add_pPr(), "outlineLvl", val="1")
        properties = header_paragraph._p.find(qn("w:r")).get_or_add_rPr()
        _child(properties, "b", val="1")
        _child(properties, "bCs", val="on")
        _child(properties, "szCs", val="23")
    _child(document.settings.element, "updateFields", val="true")
    document.save(path)
    with ZipFile(path) as package:
        parts = {name: package.read(name) for name in package.namelist()}
    numbering = etree.fromstring(parts["word/numbering.xml"])
    _child(numbering.find(".//" + qn("w:lvl")), "suff", val="space")
    parts["word/numbering.xml"] = etree.tostring(numbering)
    styles = etree.fromstring(parts["word/styles.xml"])
    properties = styles.find(".//" + qn("w:rPr"))
    _child(properties, "sz", val="23")
    _child(properties, "b", val="1")
    _child(properties, "bCs", val="on")
    _child(properties, "szCs", val="23")
    style_ppr = styles.find(".//" + qn("w:pPr"))
    _child(style_ppr, "ind", firstLine="120", left="240", right="120")
    _child(style_ppr, "keepLines", val="1")
    parts["word/styles.xml"] = etree.tostring(styles)
    with ZipFile(path, "w", ZIP_DEFLATED) as package:
        for name, data in parts.items():
            package.writestr(name, data)


def _replace_body_with_new_content(document):
    body = document.element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)
    first = document.add_paragraph("Completely new text: [ФИО-1]")
    _format_paragraph(first._p)
    second = document.add_paragraph("Second new paragraph with a surviving [ФИО-1]")
    _format_paragraph(second._p)
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "New table"
    table.cell(0, 1).text = "[ФИО-1]"
    table.cell(1, 0).text = "Other new text"
    table.cell(1, 1).text = "[ФИО-1]"
    _child(table.rows[0]._tr.get_or_add_trPr(), "cantSplit")
    _child(document.sections[0].header.paragraphs[0]._p.get_or_add_pPr(), "keepLines", val="1")
    document.sections[0].header.paragraphs[0].add_run(" [ФИО-1]")
    document.sections[0].footer.paragraphs[0].text = "Edited footer [ФИО-1]"


def test_portable_pair_restores_remaining_markers_after_complete_content_rewrite(tmp_path):
    source = tmp_path / "source.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович", style="Title")
    document.save(source)

    service = AnonymizerService(tmp_path / "library")
    document_id = service.import_file(source)
    service.anonymize(document_id)
    pair = service.export_pair(document_id, tmp_path / "portable.docx", confirmation=True)
    rewritten = Document(pair["anonymized_path"])
    _replace_body_with_new_content(rewritten)
    rewritten.save(pair["anonymized_path"])
    service.storage.delete_document(document_id)

    restored = tmp_path / "restored.docx"
    report = service.restore_from_pair(pair["anonymized_path"], restored)

    result = Document(restored)
    all_text = "\n".join(
        [paragraph.text for paragraph in result.paragraphs]
        + [cell.text for table in result.tables for row in table.rows for cell in row.cells]
        + [paragraph.text for paragraph in result.sections[0].header.paragraphs]
        + [paragraph.text for paragraph in result.sections[0].footer.paragraphs]
    )
    assert "[ФИО-1]" not in all_text
    assert all_text.count("Иванов Сергей Петрович") == 6
    assert "Completely new text" in all_text
    assert "Edited footer" in all_text
    assert report["unknown_markers"] == []


def test_standard_word_rewrite_recovers_portable_pair_without_library(tmp_path):
    source = tmp_path / "synthetic.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.save(source)
    source_bytes = source.read_bytes()
    service = AnonymizerService(tmp_path / "library")
    document_id = service.import_file(source)
    service.anonymize(document_id)
    pair = service.export_pair(document_id, tmp_path / "portable.docx", confirmation=True)
    _word_rewrite(pair["anonymized_path"])
    sanitized = tmp_path / "sanitized-standard-structures.docx"
    sanitized.write_bytes(pair["anonymized_path"].read_bytes())
    assert _sanitize_package(sanitized) == []
    with ZipFile(sanitized) as package:
        sanitized_parts = [
            etree.fromstring(package.read(name))
            for name in package.namelist()
            if name == "word/document.xml" or name.startswith(("word/header", "word/footer"))
        ]
    sanitized_text = "".join("".join(part.itertext()) for part in sanitized_parts)
    assert "Visible link" in sanitized_text
    assert "Visible field result" in sanitized_text
    for sanitized_part in sanitized_parts:
        assert sanitized_part.xpath(".//w:fldChar|.//w:instrText|.//w:bookmarkStart|.//w:bookmarkEnd|.//w:hyperlink", namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}) == []
    edited_bytes = pair["anonymized_path"].read_bytes()
    recovery_bytes = pair["recovery_path"].read_bytes()
    service.storage.delete_document(document_id)

    restored = tmp_path / "restored.docx"
    report = service.restore_from_pair(pair["anonymized_path"], restored)

    result = Document(restored)
    assert "Edited Иванов Сергей Петрович" in "\n".join(p.text for p in result.paragraphs)
    assert "Иванов Сергей Петрович" in result.sections[0].header.paragraphs[0].text
    assert "Иванов Сергей Петрович" in result.sections[0].footer.paragraphs[0].text
    assert report["unknown_markers"] == []
    assert source.read_bytes() == source_bytes
    assert pair["anonymized_path"].read_bytes() == edited_bytes
    assert pair["recovery_path"].read_bytes() == recovery_bytes
    assert _sanitize_package(restored) == []
    with ZipFile(restored) as package:
        root = etree.fromstring(package.read("word/document.xml"))
        assert root.find(".//" + qn("w:cantSplit")) is not None
        assert root.find(".//" + qn("w:tblBorders")) is not None
        assert root.find(".//" + qn("w:color")).get(qn("w:val")) == "123ABC"
        assert root.find(".//" + qn("w:updateFields")) is None


def test_standard_russian_numbering_format_is_preserved(tmp_path):
    source = tmp_path / "russian-numbering.docx"
    document = Document()
    document.add_paragraph("Synthetic only", style="List Number")
    document.save(source)
    with ZipFile(source) as package:
        parts = {name: package.read(name) for name in package.namelist()}
    numbering = etree.fromstring(parts["word/numbering.xml"])
    number_format = numbering.find(".//" + qn("w:numFmt"))
    number_format.set(qn("w:val"), "russianLower")
    parts["word/numbering.xml"] = etree.tostring(numbering)
    with ZipFile(source, "w", ZIP_DEFLATED) as package:
        for name, data in parts.items():
            package.writestr(name, data)

    assert _sanitize_package(source) == []
    with ZipFile(source) as package:
        root = etree.fromstring(package.read("word/numbering.xml"))
    assert root.find(".//" + qn("w:numFmt")).get(qn("w:val")) == "russianLower"


def test_theme_metadata_is_canonicalized_without_leaving_invalid_drawing_leaves():
    drawing = "http://schemas.openxmlformats.org/drawingml/2006/main"
    root = etree.fromstring(
        f'<a:theme xmlns:a="{drawing}" name="Synthetic theme">'
        '<a:clrScheme name="Synthetic colors"/>'
        '<a:fontScheme name="Synthetic fonts"/>'
        '<a:shade val="20000"/><a:tileRect/>'
        '</a:theme>'
    )

    clean, blocked = _scrub_unknown_docx_xml("word/theme/theme1.xml", root)

    assert not blocked
    assert clean.get("name") == "LocalAnonymizer Theme"
    assert clean.find(f"{{{drawing}}}clrScheme").get("name") == "LocalAnonymizer"
    assert clean.find(f"{{{drawing}}}fontScheme").get("name") == "LocalAnonymizer"
    assert clean.find(f"{{{drawing}}}shade").get("val") == "20000"
    assert clean.find(f"{{{drawing}}}tileRect") is not None


def test_standard_tab_leader_is_preserved_in_its_exact_tabs_context(tmp_path):
    source = tmp_path / "tab-leader.docx"
    document = Document()
    paragraph = document.add_paragraph("Synthetic only")
    tabs = _child(paragraph._p.get_or_add_pPr(), "tabs")
    _child(tabs, "tab", val="right", pos="9921", leader="dot")
    document.save(source)

    assert _sanitize_package(source) == []
    with ZipFile(source) as package:
        root = etree.fromstring(package.read("word/document.xml"))
    tab = root.find(".//" + qn("w:tabs") + "/" + qn("w:tab"))
    assert tab.get(qn("w:leader")) == "dot"


def test_invalid_newly_admitted_wml_format_values_are_removed(tmp_path):
    source = tmp_path / "invalid-format-values.docx"
    document = Document()
    paragraph = document.add_paragraph("Synthetic only")
    properties = paragraph._p.get_or_add_pPr()
    _child(properties, "spacing", lineRule="secret")
    tabs = _child(properties, "tabs")
    _child(tabs, "tab", val="left", pos="720", leader="secret")
    borders = _child(document.add_table(rows=1, cols=1)._tbl.tblPr, "tblBorders")
    _child(borders, "top", val="secret", sz="8", color="000000")
    _child(borders, "left", val="single", sz="8", color="123ABC")
    document.save(source)

    warnings = _sanitize_package(source)

    with ZipFile(source) as package:
        root = etree.fromstring(package.read("word/document.xml"))
    assert root.find(".//" + qn("w:spacing")) is None
    assert root.find(".//" + qn("w:tab")) is None
    assert root.find(".//" + qn("w:tblBorders") + "/" + qn("w:top")) is None
    assert root.find(".//" + qn("w:tblBorders") + "/" + qn("w:left")).get(qn("w:color")) == "123ABC"


def test_minimum_word_font_size_is_preserved_in_its_exact_run_property_context(tmp_path):
    source = tmp_path / "minimum-font-size.docx"
    document = Document()
    paragraph = document.add_paragraph("Synthetic only")
    run = paragraph._p.find(qn("w:r"))
    _child(run.get_or_add_rPr(), "sz", val="2")
    document.save(source)

    assert _sanitize_package(source) == []
    with ZipFile(source) as package:
        root = etree.fromstring(package.read("word/document.xml"))
    assert root.find(".//" + qn("w:sz")).get(qn("w:val")) == "2"


def _rewrite_parts(path, transform):
    with ZipFile(path) as package:
        parts = {name: package.read(name) for name in package.namelist()}
    transform(parts)
    with ZipFile(path, "w", ZIP_DEFLATED) as package:
        for name, data in parts.items():
            package.writestr(name, data)


def _inject_style(parts, style_id, name, based_on=None):
    styles = etree.fromstring(parts["word/styles.xml"])
    style = etree.SubElement(styles, qn("w:style"))
    style.set(qn("w:type"), "paragraph")
    style.set(qn("w:styleId"), style_id)
    style_name = etree.SubElement(style, qn("w:name"))
    style_name.set(qn("w:val"), name)
    if based_on is not None:
        base = etree.SubElement(style, qn("w:basedOn"))
        base.set(qn("w:val"), based_on)
    parts["word/styles.xml"] = etree.tostring(
        styles, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    return style


def _style_paragraph(parts, index, style_id):
    document_root = etree.fromstring(parts["word/document.xml"])
    body = document_root.find(qn("w:body"))
    paragraph = body.findall(qn("w:p"))[index]
    properties = paragraph.find(qn("w:pPr"))
    if properties is None:
        properties = etree.Element(qn("w:pPr"))
        paragraph.insert(0, properties)
    reference = properties.find(qn("w:pStyle"))
    if reference is None:
        reference = etree.SubElement(properties, qn("w:pStyle"))
    reference.set(qn("w:val"), style_id)
    parts["word/document.xml"] = etree.tostring(
        document_root, xml_declaration=True, encoding="UTF-8", standalone=True
    )


def _style_ids(parts):
    styles = etree.fromstring(parts["word/styles.xml"])
    return {s.get(qn("w:styleId")) for s in styles.iter(qn("w:style"))}


def _paragraph_style_references(parts):
    document_root = etree.fromstring(parts["word/document.xml"])
    return [
        element.get(qn("w:val"))
        for element in document_root.iter(qn("w:pStyle"))
    ]


def _prepare_snapshot_core_pair(tmp_path):
    """A pair whose source carries an untrusted custom style, then a Word-like edit.

    The edit inserts an extra paragraph (so paragraph counts no longer align
    and the original-layout path is unavailable) and adds one brand-new style
    to the edited styles part, exactly as Word does for generated TOC styles.
    """
    source = tmp_path / "snapshot-core.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.save(source)

    def customize(parts):
        _inject_style(parts, "CustomOriginalStyle", "Custom Original", based_on="Normal")
        _style_paragraph(parts, 0, "CustomOriginalStyle")

    _rewrite_parts(source, customize)

    service = AnonymizerService(tmp_path / "library")
    document_id = service.import_file(source)
    service.anonymize(document_id)
    pair = service.export_pair(document_id, tmp_path / "portable.docx", confirmation=True)

    anonymized_parts = {}
    with ZipFile(pair["anonymized_path"]) as package:
        anonymized_parts = {
            name: package.read(name) for name in package.namelist()
        }
    canonical = [
        value for value in _paragraph_style_references(anonymized_parts)
        if value and value.startswith("LocalStyle")
    ]
    assert canonical, "expected the untrusted source style to be canonicalized"

    rewritten = Document(pair["anonymized_path"])
    rewritten.add_paragraph("Added by Word [ФИО-1]")
    rewritten.save(pair["anonymized_path"])

    def word_edit(parts):
        _inject_style(parts, "WordAddedStyle", "Word Added", based_on=canonical[0])
        _style_paragraph(parts, -1, "WordAddedStyle")
        # The styled source paragraph also keeps its canonical reference.
        _style_paragraph(parts, 0, canonical[0])

    _rewrite_parts(pair["anonymized_path"], word_edit)
    service.storage.delete_document(document_id)
    return source, pair


def test_fallback_restore_rebuilds_format_core_from_exact_snapshot(tmp_path):
    source, pair = _prepare_snapshot_core_pair(tmp_path)

    restored = tmp_path / "restored.docx"
    report = AnonymizerService(tmp_path / "library").restore_from_pair(
        pair["anonymized_path"], restored
    )

    with ZipFile(source) as package:
        source_parts = {name: package.read(name) for name in package.namelist()}
    with ZipFile(restored) as package:
        restored_parts = {name: package.read(name) for name in package.namelist()}

    # The formatting core is rebuilt from the exact source snapshot, not from
    # the edited/sanitized package.
    for name in (
        "word/settings.xml", "word/fontTable.xml", "word/webSettings.xml",
        "word/theme/theme1.xml",
    ):
        if name in source_parts:
            assert restored_parts.get(name) == source_parts[name], name

    restored_style_ids = _style_ids(restored_parts)
    source_style_ids = _style_ids(source_parts)
    assert "CustomOriginalStyle" in restored_style_ids
    assert source_style_ids <= restored_style_ids

    references = _paragraph_style_references(restored_parts)
    assert "CustomOriginalStyle" in references
    added_references = [value for value in references if value not in source_style_ids]
    assert added_references, "expected the Word-added style to stay referenced"
    assert added_references[0] in restored_style_ids
    # No canonical duplicate of a snapshot style may be appended: Microsoft
    # Word rejects a styles part that defines both the original style and its
    # sanitized copy (duplicate w:link pairing), even though python-docx
    # opens such a package happily.
    assert restored_style_ids - source_style_ids == set(added_references)

    # Style references that only exist in the edited file keep a definition:
    # the appended style is carried over from the sanitized output and its
    # basedOn link is resolved onto the snapshot core.
    styles = etree.fromstring(restored_parts["word/styles.xml"])
    appended = [
        s for s in styles.iter(qn("w:style"))
        if s.get(qn("w:styleId")) not in source_style_ids
    ]
    assert appended
    based_on = appended[0].find(qn("w:basedOn"))
    assert based_on is not None
    assert based_on.get(qn("w:val")) in source_style_ids

    result = Document(restored)
    texts = "\n".join(paragraph.text for paragraph in result.paragraphs)
    assert "Иванов Сергей Петрович" in texts
    assert "Added by Word Иванов Сергей Петрович" in texts
    assert report["unknown_markers"] == []


def test_edited_pair_with_inert_svg_snapshot_uses_semantic_restore(tmp_path):
    """An edited pair must not reject an inert snapshot-only SVG before fallback."""
    source = tmp_path / "synthetic-source.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.save(source)

    service = AnonymizerService(tmp_path / "library")
    document_id = service.import_file(source)
    service.anonymize(document_id)
    pair = service.export_pair(document_id, tmp_path / "portable.docx", confirmation=True)

    def add_inert_svg(archive):
        original = base64.b64decode(archive["exact_source_b64"], validate=True)
        donor = BytesIO()
        with ZipFile(BytesIO(original)) as incoming, ZipFile(donor, "w", ZIP_DEFLATED) as outgoing:
            for info in incoming.infolist():
                outgoing.writestr(info, incoming.read(info.filename))
            outgoing.writestr(
                "word/media/image2.svg",
                b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>',
            )
        snapshot = donor.getvalue()
        archive["exact_source_b64"] = base64.b64encode(snapshot).decode("ascii")
        archive["exact_source_sha256"] = sha256(snapshot).hexdigest()

    _replace_portable_snapshot(pair["recovery_path"], add_inert_svg)
    edited = Document(pair["anonymized_path"])
    edited.add_paragraph("Edited [ФИО-1]")
    edited.save(pair["anonymized_path"])
    service.storage.delete_document(document_id)

    restored = tmp_path / "restored.docx"
    report = AnonymizerService(tmp_path / "restore-library").restore_from_pair(
        pair["anonymized_path"], restored
    )

    assert "Edited Иванов Сергей Петрович" in "\n".join(
        paragraph.text for paragraph in Document(restored).paragraphs
    )
    assert report["unknown_markers"] == []


def test_edited_pair_with_malformed_snapshot_format_core_has_no_output(tmp_path):
    source = tmp_path / "synthetic-source.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.save(source)

    service = AnonymizerService(tmp_path / "library")
    document_id = service.import_file(source)
    service.anonymize(document_id)
    pair = service.export_pair(document_id, tmp_path / "portable.docx", confirmation=True)

    def corrupt_styles(archive):
        original = base64.b64decode(archive["exact_source_b64"], validate=True)
        donor = BytesIO()
        with ZipFile(BytesIO(original)) as incoming, ZipFile(donor, "w", ZIP_DEFLATED) as outgoing:
            for info in incoming.infolist():
                payload = b"<not-styles/>" if info.filename == "word/styles.xml" else incoming.read(info.filename)
                outgoing.writestr(info, payload)
        snapshot = donor.getvalue()
        archive["exact_source_b64"] = base64.b64encode(snapshot).decode("ascii")
        archive["exact_source_sha256"] = sha256(snapshot).hexdigest()

    _replace_portable_snapshot(pair["recovery_path"], corrupt_styles)
    edited = Document(pair["anonymized_path"])
    edited.add_paragraph("Edited [ФИО-1]")
    edited.save(pair["anonymized_path"])
    service.storage.delete_document(document_id)

    from local_anonymizer.documents import RestorationError

    restored = tmp_path / "restored.docx"
    with pytest.raises(RestorationError):
        AnonymizerService(tmp_path / "restore-library").restore_from_pair(
            pair["anonymized_path"], restored
        )
    assert not restored.exists()


def test_fallback_restore_without_snapshot_keeps_sanitized_core(tmp_path):
    source, pair = _prepare_snapshot_core_pair(tmp_path)

    from local_anonymizer.documents import DocxProcessor
    from local_anonymizer.service import _read_artifact_identity

    service = AnonymizerService(tmp_path / "restore-library")
    document_id, operation_id = _read_artifact_identity(pair["anonymized_path"])
    payload = AnonymizerService._read_recovery_file(pair["recovery_path"])
    mapping, archive = service.storage.decode_restore_payload(
        payload["bundle"], document_id, operation_id
    )
    archive.pop("exact_source_b64", None)
    archive.pop("exact_source_sha256", None)
    archive.pop("exact_anonymized_sha256", None)
    service.storage.connection.close()

    restored = tmp_path / "restored.docx"
    unknown = DocxProcessor().restore(
        pair["anonymized_path"], restored, mapping, package_archive=archive
    )

    with ZipFile(restored) as package:
        restored_parts = {name: package.read(name) for name in package.namelist()}
    assert "CustomOriginalStyle" not in _style_ids(restored_parts)
    assert any(
        value and value.startswith("LocalStyle")
        for value in _paragraph_style_references(restored_parts)
    )
    result = Document(restored)
    texts = "\n".join(paragraph.text for paragraph in result.paragraphs)
    assert "Added by Word Иванов Сергей Петрович" in texts
    assert unknown == []


def test_fallback_restore_fails_closed_on_tampered_snapshot(tmp_path):
    source, pair = _prepare_snapshot_core_pair(tmp_path)

    from local_anonymizer.documents import DocxProcessor, RestorationError
    from local_anonymizer.service import _read_artifact_identity

    service = AnonymizerService(tmp_path / "tamper-library")
    document_id, operation_id = _read_artifact_identity(pair["anonymized_path"])
    payload = AnonymizerService._read_recovery_file(pair["recovery_path"])
    mapping, archive = service.storage.decode_restore_payload(
        payload["bundle"], document_id, operation_id
    )
    service.storage.connection.close()
    archive["exact_source_sha256"] = "0" * 64

    restored = tmp_path / "restored.docx"
    with pytest.raises(RestorationError):
        DocxProcessor().restore(
            pair["anonymized_path"], restored, mapping, package_archive=archive
        )
    assert not restored.exists()


def test_restore_rejects_hash_consistent_non_zip_snapshot_without_output(tmp_path):
    _, pair = _prepare_snapshot_core_pair(tmp_path)
    from base64 import b64encode
    from hashlib import sha256
    from local_anonymizer.documents import DocxProcessor, RestorationError
    from local_anonymizer.service import _read_artifact_identity

    service = AnonymizerService(tmp_path / "snapshot-validation-library")
    document_id, operation_id = _read_artifact_identity(pair["anonymized_path"])
    payload = AnonymizerService._read_recovery_file(pair["recovery_path"])
    mapping, archive = service.storage.decode_restore_payload(
        payload["bundle"], document_id, operation_id
    )
    service.storage.connection.close()
    donor = b"not a DOCX"
    archive["exact_source_b64"] = b64encode(donor).decode("ascii")
    archive["exact_source_sha256"] = sha256(donor).hexdigest()

    restored = tmp_path / "restored.docx"
    with pytest.raises(RestorationError):
        DocxProcessor().restore(pair["anonymized_path"], restored, mapping, package_archive=archive)
    assert not restored.exists()


def test_public_restore_rejects_hash_consistent_non_docx_zip_snapshot_without_output(tmp_path):
    """A hash is not proof that a snapshot is a replayable OOXML package."""
    _, pair = _prepare_snapshot_core_pair(tmp_path)

    donor = BytesIO()
    with ZipFile(donor, "w", ZIP_DEFLATED) as package:
        package.writestr("not-a-docx.txt", "synthetic")

    def replace(archive):
        archive["exact_source_b64"] = base64.b64encode(donor.getvalue()).decode("ascii")
        archive["exact_source_sha256"] = sha256(donor.getvalue()).hexdigest()

    _replace_portable_snapshot(pair["recovery_path"], replace)
    restored = tmp_path / "restored.docx"

    from local_anonymizer.documents import RestorationError
    with pytest.raises(RestorationError):
        AnonymizerService(tmp_path / "library").restore_from_pair(
            pair["anonymized_path"], restored
        )
    assert not restored.exists()


@pytest.mark.parametrize("mutation", ["unsafe-external-relationship", "unknown-member"])
def test_public_restore_rejects_hash_consistent_unsafe_docx_snapshot_without_output(
    tmp_path, mutation
):
    """Exact donors must be a replay-safe DOCX subset, not merely a valid ZIP."""
    _, pair = _prepare_snapshot_core_pair(tmp_path)

    def replace(archive):
        source = base64.b64decode(archive["exact_source_b64"])
        donor = BytesIO()
        with ZipFile(BytesIO(source)) as incoming, ZipFile(donor, "w", ZIP_DEFLATED) as outgoing:
            for info in incoming.infolist():
                data = incoming.read(info.filename)
                if mutation == "unsafe-external-relationship" and info.filename == "word/_rels/document.xml.rels":
                    root = etree.fromstring(data)
                    relation = etree.SubElement(
                        root,
                        "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship",
                    )
                    relation.set("Id", "rId999")
                    relation.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink")
                    relation.set("Target", "file:///C:/secret.txt")
                    relation.set("TargetMode", "External")
                    data = etree.tostring(root, xml_declaration=True, encoding="UTF-8")
                outgoing.writestr(info, data)
            if mutation == "unknown-member":
                outgoing.writestr("word/active-payload.bin", b"not a safe DOCX part")
        archive["exact_source_b64"] = base64.b64encode(donor.getvalue()).decode("ascii")
        archive["exact_source_sha256"] = sha256(donor.getvalue()).hexdigest()

    _replace_portable_snapshot(pair["recovery_path"], replace)
    restored = tmp_path / "restored.docx"

    from local_anonymizer.documents import RestorationError
    with pytest.raises(RestorationError):
        AnonymizerService(tmp_path / "library").restore_from_pair(
            pair["anonymized_path"], restored
        )
    assert not restored.exists()


def test_appended_style_numbering_absent_from_snapshot_is_stripped(tmp_path):
    source, pair = _prepare_snapshot_core_pair(tmp_path)

    def add_unknown_numbering(parts):
        styles = etree.fromstring(parts["word/styles.xml"])
        target = next(
            style for style in styles.iter(qn("w:style"))
            if style.get(qn("w:styleId")) == "WordAddedStyle"
        )
        properties = target.find(qn("w:pPr"))
        if properties is None:
            properties = etree.SubElement(target, qn("w:pPr"))
        num_pr = etree.SubElement(properties, qn("w:numPr"))
        num_id = etree.SubElement(num_pr, qn("w:numId"))
        num_id.set(qn("w:val"), "999")
        parts["word/styles.xml"] = etree.tostring(
            styles, xml_declaration=True, encoding="UTF-8", standalone=True
        )

    _rewrite_parts(pair["anonymized_path"], add_unknown_numbering)

    restored = tmp_path / "restored.docx"
    AnonymizerService(tmp_path / "library").restore_from_pair(
        pair["anonymized_path"], restored
    )

    with ZipFile(source) as package:
        source_ids = {
            style.get(qn("w:styleId"))
            for style in etree.fromstring(
                package.read("word/styles.xml")
            ).iter(qn("w:style"))
        }
    with ZipFile(restored) as package:
        styles = etree.fromstring(package.read("word/styles.xml"))
    appended = [
        style for style in styles.iter(qn("w:style"))
        if style.get(qn("w:styleId")) not in source_ids
    ]
    assert appended
    # A numbering reference the snapshot does not define would make Word
    # reject the whole styles part, so the appended style loses its numPr
    # instead of emitting a dangling reference.
    properties = appended[0].find(qn("w:pPr"))
    assert properties is not None
    assert properties.find(qn("w:numPr")) is None
    result = Document(restored)
    assert "Added by Word Иванов Сергей Петрович" in "\n".join(
        paragraph.text for paragraph in result.paragraphs
    )


def test_fallback_restore_deduplicates_edited_only_style_ids(tmp_path):
    source, pair = _prepare_snapshot_core_pair(tmp_path)

    def duplicate_edited_style(parts):
        styles = etree.fromstring(parts["word/styles.xml"])
        original = next(
            style for style in styles.iter(qn("w:style"))
            if style.get(qn("w:styleId")) == "WordAddedStyle"
        )
        styles.append(etree.fromstring(etree.tostring(original)))
        parts["word/styles.xml"] = etree.tostring(
            styles, xml_declaration=True, encoding="UTF-8", standalone=True
        )

    _rewrite_parts(pair["anonymized_path"], duplicate_edited_style)
    restored = tmp_path / "restored.docx"
    AnonymizerService(tmp_path / "library").restore_from_pair(
        pair["anonymized_path"], restored
    )

    with ZipFile(restored) as package:
        styles = etree.fromstring(package.read("word/styles.xml"))
    restored_ids = [
        style.get(qn("w:styleId")) for style in styles.iter(qn("w:style"))
    ]
    assert len(restored_ids) == len(set(restored_ids))


def test_fallback_restore_preserves_safe_edited_numbered_list(tmp_path):
    source, pair = _prepare_snapshot_core_pair(tmp_path)

    def add_edited_list(parts):
        document = etree.fromstring(parts["word/document.xml"])
        body = document.find(qn("w:body"))
        paragraph = etree.Element(qn("w:p"))
        properties = etree.SubElement(paragraph, qn("w:pPr"))
        num_pr = etree.SubElement(properties, qn("w:numPr"))
        etree.SubElement(num_pr, qn("w:ilvl")).set(qn("w:val"), "0")
        etree.SubElement(num_pr, qn("w:numId")).set(qn("w:val"), "99")
        run = etree.SubElement(paragraph, qn("w:r"))
        etree.SubElement(run, qn("w:t")).text = "Edited list [Р¤РРћ-1]"
        body.insert(len(body) - 1, paragraph)
        parts["word/document.xml"] = etree.tostring(
            document, xml_declaration=True, encoding="UTF-8", standalone=True
        )

        numbering = etree.fromstring(parts["word/numbering.xml"])
        abstract = etree.fromstring(etree.tostring(numbering.find(qn("w:abstractNum"))))
        abstract.set(qn("w:abstractNumId"), "99")
        numbering.append(abstract)
        number = etree.Element(qn("w:num"))
        number.set(qn("w:numId"), "99")
        etree.SubElement(number, qn("w:abstractNumId")).set(qn("w:val"), "99")
        numbering.append(number)
        parts["word/numbering.xml"] = etree.tostring(
            numbering, xml_declaration=True, encoding="UTF-8", standalone=True
        )

    _rewrite_parts(pair["anonymized_path"], add_edited_list)
    restored = tmp_path / "restored.docx"
    AnonymizerService(tmp_path / "library").restore_from_pair(
        pair["anonymized_path"], restored
    )

    with ZipFile(restored) as package:
        document = etree.fromstring(package.read("word/document.xml"))
        numbering = etree.fromstring(package.read("word/numbering.xml"))
    list_id = document.xpath(
        "string(//w:p[contains(.//w:t, 'Edited list')]/w:pPr/w:numPr/w:numId/@w:val)",
        namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"},
    )
    defined_ids = {num.get(qn("w:numId")) for num in numbering.iter(qn("w:num"))}
    assert list_id
    assert list_id in defined_ids


def test_fallback_restore_remaps_colliding_edited_list_id(tmp_path):
    source, pair = _prepare_snapshot_core_pair(tmp_path)

    def replace_existing_list_definition(parts):
        document = etree.fromstring(parts["word/document.xml"])
        body = document.find(qn("w:body"))
        paragraph = etree.Element(qn("w:p"))
        properties = etree.SubElement(paragraph, qn("w:pPr"))
        num_pr = etree.SubElement(properties, qn("w:numPr"))
        etree.SubElement(num_pr, qn("w:numId")).set(qn("w:val"), "1")
        run = etree.SubElement(paragraph, qn("w:r"))
        etree.SubElement(run, qn("w:t")).text = "Colliding list [Р¤РРћ-1]"
        body.insert(len(body) - 1, paragraph)
        parts["word/document.xml"] = etree.tostring(
            document, xml_declaration=True, encoding="UTF-8", standalone=True
        )

        numbering = etree.fromstring(parts["word/numbering.xml"])
        abstract = etree.fromstring(etree.tostring(numbering.find(qn("w:abstractNum"))))
        abstract.set(qn("w:abstractNumId"), "99")
        numbering.append(abstract)
        number = next(num for num in numbering.iter(qn("w:num")) if num.get(qn("w:numId")) == "1")
        number.find(qn("w:abstractNumId")).set(qn("w:val"), "99")
        parts["word/numbering.xml"] = etree.tostring(
            numbering, xml_declaration=True, encoding="UTF-8", standalone=True
        )

    _rewrite_parts(pair["anonymized_path"], replace_existing_list_definition)
    restored = tmp_path / "restored.docx"
    AnonymizerService(tmp_path / "library").restore_from_pair(
        pair["anonymized_path"], restored
    )

    with ZipFile(restored) as package:
        document = etree.fromstring(package.read("word/document.xml"))
        numbering = etree.fromstring(package.read("word/numbering.xml"))
    list_id = document.xpath(
        "string(//w:p[contains(.//w:t, 'Colliding list')]/w:pPr/w:numPr/w:numId/@w:val)",
        namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"},
    )
    defined_ids = {num.get(qn("w:numId")) for num in numbering.iter(qn("w:num"))}
    assert list_id != "1"
    assert list_id in defined_ids


def test_numbering_merge_keeps_edited_abstract_semantics_when_num_is_unchanged():
    from local_anonymizer.documents import _merge_snapshot_numbering

    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    snapshot = etree.fromstring(
        f'<w:numbering xmlns:w="{namespace}">'
        '<w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:start w:val="1"/>'
        '<w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/><w:suff w:val="tab"/>'
        '</w:lvl></w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="1"/>'
        '</w:num></w:numbering>'
    )
    edited = etree.fromstring(
        f'<w:numbering xmlns:w="{namespace}">'
        '<w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:start w:val="7"/>'
        '<w:numFmt w:val="upperRoman"/><w:lvlText w:val="(%1)"/><w:suff w:val="space"/>'
        '</w:lvl></w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="1"/>'
        '</w:num></w:numbering>'
    )
    reference = etree.fromstring(
        f'<w:document xmlns:w="{namespace}"><w:body><w:p><w:pPr><w:numPr>'
        '<w:numId w:val="1"/></w:numPr></w:pPr></w:p></w:body></w:document>'
    )

    merged, remap, _ = _merge_snapshot_numbering(
        etree.tostring(snapshot), etree.tostring(edited), [etree.tostring(reference)],
        etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False),
        baseline_numbering=etree.tostring(snapshot),
    )

    root = etree.fromstring(merged)
    num_id = remap.get("1", "1")
    number = next(item for item in root.iter(qn("w:num")) if item.get(qn("w:numId")) == num_id)
    abstract_id = number.find(qn("w:abstractNumId")).get(qn("w:val"))
    abstract = next(item for item in root.iter(qn("w:abstractNum")) if item.get(qn("w:abstractNumId")) == abstract_id)
    assert abstract.find(".//" + qn("w:start")).get(qn("w:val")) == "7"
    assert abstract.find(".//" + qn("w:numFmt")).get(qn("w:val")) == "upperRoman"
    assert abstract.find(".//" + qn("w:lvlText")).get(qn("w:val")) == "(%1)"
    assert abstract.find(".//" + qn("w:suff")).get(qn("w:val")) == "space"


def test_numbering_merge_imports_style_only_list_reference():
    from local_anonymizer.documents import _merge_snapshot_numbering
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    empty = f'<w:numbering xmlns:w="{namespace}"/>'
    edited = (
        f'<w:numbering xmlns:w="{namespace}"><w:abstractNum w:abstractNumId="9">'
        '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/>'
        '<w:lvlText w:val="%1."/><w:suff w:val="tab"/></w:lvl></w:abstractNum>'
        '<w:num w:numId="9"><w:abstractNumId w:val="9"/></w:num></w:numbering>'
    )
    style = (
        f'<w:styles xmlns:w="{namespace}"><w:style w:type="paragraph" w:styleId="LocalStyle999">'
        '<w:pPr><w:numPr><w:numId w:val="9"/></w:numPr></w:pPr></w:style></w:styles>'
    )
    merged, _, ids = _merge_snapshot_numbering(
        empty.encode(), edited.encode(), [style.encode()], etree.XMLParser(resolve_entities=False),
    )
    assert "9" in ids
    assert etree.fromstring(merged).find(qn("w:num")) is not None


def test_numbering_merge_places_imported_num_before_cleanup_marker():
    from local_anonymizer.documents import _merge_snapshot_numbering
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    snapshot = f'<w:numbering xmlns:w="{namespace}"><w:numIdMacAtCleanup w:val="1"/></w:numbering>'
    edited = (
        f'<w:numbering xmlns:w="{namespace}"><w:abstractNum w:abstractNumId="9">'
        '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/>'
        '<w:lvlText w:val="%1."/><w:suff w:val="tab"/></w:lvl></w:abstractNum>'
        '<w:num w:numId="9"><w:abstractNumId w:val="9"/></w:num></w:numbering>'
    )
    reference = f'<w:document xmlns:w="{namespace}"><w:body><w:p><w:pPr><w:numPr><w:numId w:val="9"/></w:numPr></w:pPr></w:p></w:body></w:document>'
    merged, _, _ = _merge_snapshot_numbering(snapshot.encode(), edited.encode(), [reference.encode()], etree.XMLParser(resolve_entities=False))
    assert [etree.QName(item).localname for item in etree.fromstring(merged)] == [
        "abstractNum", "num", "numIdMacAtCleanup"
    ]


def test_public_semantic_restore_keeps_style_only_edited_list_semantics(tmp_path):
    """Semantic fallback must import a list reached solely through pStyle."""
    source = tmp_path / "style-list.docx"
    document = Document()
    document.add_paragraph("\u0418\u0432\u0430\u043d\u043e\u0432 \u0421\u0435\u0440\u0433\u0435\u0439 \u041f\u0435\u0442\u0440\u043e\u0432\u0438\u0447")
    document.add_paragraph("Remove for balanced edit")
    document.save(source)
    service = AnonymizerService(tmp_path / "library")
    document_id = service.import_file(source)
    service.anonymize(document_id)
    row = service.storage.get_document(document_id)
    mapping = service.storage.load_mapping(document_id, row["operation_id"])
    pair = service.export_pair(document_id, tmp_path / "portable.docx", confirmation=True)

    def make_style_only_list(parts):
        marker = next(value for value in mapping if value.encode() in parts["word/document.xml"])
        _inject_style(parts, "StyleOnlyList", "Style Only List", based_on="Normal")
        styles = etree.fromstring(parts["word/styles.xml"])
        style = next(item for item in styles.iter(qn("w:style")) if item.get(qn("w:styleId")) == "StyleOnlyList")
        properties = etree.SubElement(style, qn("w:pPr"))
        number = etree.SubElement(etree.SubElement(properties, qn("w:numPr")), qn("w:numId"))
        number.set(qn("w:val"), "777")
        parts["word/styles.xml"] = etree.tostring(styles, xml_declaration=True, encoding="UTF-8", standalone=True)
        _style_paragraph(parts, 0, "StyleOnlyList")
        document_root = etree.fromstring(parts["word/document.xml"])
        body = document_root.find(qn("w:body"))
        body.remove(body.findall(qn("w:p"))[1])
        added = etree.Element(qn("w:p"))
        run = etree.SubElement(added, qn("w:r"))
        etree.SubElement(run, qn("w:t")).text = "User-added structure"
        body.insert(len(body) - 1, added)
        parts["word/document.xml"] = etree.tostring(document_root, xml_declaration=True, encoding="UTF-8", standalone=True)
        numbering = etree.fromstring(parts["word/numbering.xml"])
        abstract = etree.Element(qn("w:abstractNum"), {qn("w:abstractNumId"): "777"})
        level = etree.SubElement(abstract, qn("w:lvl"), {qn("w:ilvl"): "0"})
        etree.SubElement(level, qn("w:start"), {qn("w:val"): "7"})
        etree.SubElement(level, qn("w:numFmt"), {qn("w:val"): "upperRoman"})
        etree.SubElement(level, qn("w:lvlText"), {qn("w:val"): "(%1)"})
        etree.SubElement(level, qn("w:suff"), {qn("w:val"): "space"})
        first_num = numbering.find(qn("w:num"))
        numbering.insert(numbering.index(first_num), abstract)
        number = etree.Element(qn("w:num"), {qn("w:numId"): "777"})
        etree.SubElement(number, qn("w:abstractNumId"), {qn("w:val"): "777"})
        numbering.append(number)
        parts["word/numbering.xml"] = etree.tostring(numbering, xml_declaration=True, encoding="UTF-8", standalone=True)

    _rewrite_parts(pair["anonymized_path"], make_style_only_list)
    service.storage.delete_document(document_id)
    restored = tmp_path / "restored.docx"
    service.restore_from_pair(pair["anonymized_path"], restored)

    with ZipFile(restored) as package:
        styles = etree.fromstring(package.read("word/styles.xml"))
        numbering = etree.fromstring(package.read("word/numbering.xml"))
        restored_document = etree.fromstring(package.read("word/document.xml"))
    marker, original = next(iter(mapping.items()))
    assert original in "".join(restored_document.itertext())
    marker_paragraph = next(
        paragraph for paragraph in restored_document.iter(qn("w:p"))
        if original in "".join(paragraph.itertext())
    )
    style_id = marker_paragraph.find(".//" + qn("w:pStyle")).get(qn("w:val"))
    style = next(item for item in styles.iter(qn("w:style")) if item.get(qn("w:styleId")) == style_id)
    list_id = style.find(".//" + qn("w:numId")).get(qn("w:val"))
    number = next(item for item in numbering.iter(qn("w:num")) if item.get(qn("w:numId")) == list_id)
    abstract_id = number.find(qn("w:abstractNumId")).get(qn("w:val"))
    abstract = next(item for item in numbering.iter(qn("w:abstractNum")) if item.get(qn("w:abstractNumId")) == abstract_id)
    assert abstract.find(".//" + qn("w:numFmt")).get(qn("w:val")) == "upperRoman"
    assert abstract.find(".//" + qn("w:start")).get(qn("w:val")) == "7"
    assert abstract.find(".//" + qn("w:lvlText")).get(qn("w:val")) == "(%1)"
    assert abstract.find(".//" + qn("w:suff")).get(qn("w:val")) == "space"


def test_style_merge_keeps_supported_edit_to_mapped_snapshot_style():
    from local_anonymizer.documents import _merged_snapshot_styles

    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    snapshot = etree.fromstring(
        f'<w:styles xmlns:w="{namespace}"><w:style w:type="paragraph" w:styleId="Original">'
        '<w:name w:val="Original"/><w:rPr><w:sz w:val="20"/></w:rPr></w:style></w:styles>'
    )
    edited = etree.fromstring(
        f'<w:styles xmlns:w="{namespace}"><w:style w:type="paragraph" w:styleId="LocalStyle001">'
        '<w:name w:val="Edited"/><w:rPr><w:sz w:val="32"/></w:rPr></w:style></w:styles>'
    )

    baseline = etree.fromstring(
        f'<w:styles xmlns:w="{namespace}"><w:style w:type="paragraph" w:styleId="LocalStyle001">'
        '<w:name w:val="Edited"/><w:rPr><w:sz w:val="20"/></w:rPr></w:style></w:styles>'
    )

    merged = _merged_snapshot_styles(
        etree.tostring(snapshot), etree.tostring(edited), {"LocalStyle001": "Original"}, {}, set(),
        etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False),
        baseline_styles=etree.tostring(baseline),
    )

    root = etree.fromstring(merged)
    style = next(item for item in root.iter(qn("w:style")) if item.get(qn("w:styleId")) == "Original")
    assert style.find(".//" + qn("w:sz")).get(qn("w:val")) == "32"


def test_legacy_semantic_restore_keeps_mapped_snapshot_style_authoritative(tmp_path):
    """Legacy recovery never promotes a canonicalized style over its donor."""
    source, pair = _prepare_snapshot_core_pair(tmp_path)

    def remove_baseline(archive):
        archive.pop("anonymized_format_core", None)

    _replace_portable_snapshot(pair["recovery_path"], remove_baseline)

    def edit_mapped_style(parts):
        styles = etree.fromstring(parts["word/styles.xml"])
        mapped = next(
            style for style in styles.iter(qn("w:style"))
            if style.get(qn("w:styleId",)).startswith("LocalStyle")
        )
        properties = mapped.find(qn("w:rPr"))
        if properties is None:
            properties = etree.SubElement(mapped, qn("w:rPr"))
        etree.SubElement(properties, qn("w:sz")).set(qn("w:val"), "32")
        parts["word/styles.xml"] = etree.tostring(
            styles, xml_declaration=True, encoding="UTF-8", standalone=True
        )

    _rewrite_parts(pair["anonymized_path"], edit_mapped_style)
    restored = tmp_path / "restored.docx"
    report = AnonymizerService(tmp_path / "legacy-library").restore_from_pair(
        pair["anonymized_path"], restored
    )

    with ZipFile(source) as package:
        source_styles = etree.fromstring(package.read("word/styles.xml"))
    with ZipFile(restored) as package:
        restored_styles = etree.fromstring(package.read("word/styles.xml"))
        restored_document = etree.fromstring(package.read("word/document.xml"))
    source_custom = next(
        style for style in source_styles.iter(qn("w:style"))
        if style.get(qn("w:styleId")) == "CustomOriginalStyle"
    )
    restored_custom = next(
        style for style in restored_styles.iter(qn("w:style"))
        if style.get(qn("w:styleId")) == "CustomOriginalStyle"
    )
    restored_ids = [
        style.get(qn("w:styleId")) for style in restored_styles.iter(qn("w:style"))
    ]
    source_ids = {
        style.get(qn("w:styleId")) for style in source_styles.iter(qn("w:style"))
    }

    assert etree.tostring(restored_custom) == etree.tostring(source_custom)
    assert source_ids <= set(restored_ids)
    assert len(restored_ids) == len(set(restored_ids))
    assert "[Р¤РРћ-1]" not in "".join(restored_document.itertext())
    assert report["unknown_markers"] == []


def test_public_semantic_restore_keeps_supported_edit_to_existing_normal_style(tmp_path):
    """A stable snapshot style ID must not discard a supported user edit."""
    source = tmp_path / "stable-normal.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.add_paragraph("Remove to force semantic fallback")
    document.save(source)
    service = AnonymizerService(tmp_path / "library")
    document_id = service.import_file(source)
    service.anonymize(document_id)
    row = service.storage.get_document(document_id)
    mapping = service.storage.load_mapping(document_id, row["operation_id"])
    marker, original = next(iter(mapping.items()))
    pair = service.export_pair(document_id, tmp_path / "portable.docx", confirmation=True)

    def edit_existing_normal_style(parts):
        styles = etree.fromstring(parts["word/styles.xml"])
        normal = next(
            style for style in styles.iter(qn("w:style"))
            if style.get(qn("w:styleId")) == "Normal"
        )
        properties = normal.find(qn("w:rPr"))
        if properties is None:
            properties = etree.SubElement(normal, qn("w:rPr"))
        size = properties.find(qn("w:sz"))
        if size is None:
            size = etree.SubElement(properties, qn("w:sz"))
        size.set(qn("w:val"), "32")
        parts["word/styles.xml"] = etree.tostring(
            styles, xml_declaration=True, encoding="UTF-8", standalone=True
        )
        root = etree.fromstring(parts["word/document.xml"])
        body = root.find(qn("w:body"))
        body.remove(body.findall(qn("w:p"))[1])
        added = etree.Element(qn("w:p"))
        run = etree.SubElement(added, qn("w:r"))
        etree.SubElement(run, qn("w:t")).text = "User-added structure"
        body.insert(len(body) - 1, added)
        parts["word/document.xml"] = etree.tostring(
            root, xml_declaration=True, encoding="UTF-8", standalone=True
        )

    _rewrite_parts(pair["anonymized_path"], edit_existing_normal_style)
    service.storage.delete_document(document_id)
    restored = tmp_path / "restored.docx"
    service.restore_from_pair(pair["anonymized_path"], restored)

    with ZipFile(restored) as package:
        styles = etree.fromstring(package.read("word/styles.xml"))
        restored_document = etree.fromstring(package.read("word/document.xml"))
    normal = next(
        style for style in styles.iter(qn("w:style"))
        if style.get(qn("w:styleId")) == "Normal"
    )
    assert normal.find(".//" + qn("w:sz")).get(qn("w:val")) == "32"
    assert original in "".join(restored_document.itertext())
    assert marker not in "".join(restored_document.itertext())


def test_public_restore_rejects_invalid_portable_mapping_without_output(tmp_path):
    source = tmp_path / "invalid-portable-mapping.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.save(source)
    service = AnonymizerService(tmp_path / "library")
    document_id = service.import_file(source)
    service.anonymize(document_id)
    pair = service.export_pair(document_id, tmp_path / "portable.docx", confirmation=True)

    from local_anonymizer.service import _canonical_json, _recovery_checksum

    payload = json.loads(pair["recovery_path"].read_text(encoding="utf-8"))
    payload["bundle"]["mapping"] = {"not-a-marker": ["not a string"]}
    payload["bundle"]["marker_manifest"] = ["not-a-marker"]
    payload["checksum_sha256"] = _recovery_checksum(payload)
    pair["recovery_path"].write_bytes(_canonical_json(payload))
    service.storage.delete_document(document_id)

    from local_anonymizer.documents import RestorationError

    restored = tmp_path / "restored.docx"
    with pytest.raises(RestorationError):
        AnonymizerService(tmp_path / "restore-library").restore_from_pair(
            pair["anonymized_path"], restored, recovery_path=pair["recovery_path"]
        )
    assert not restored.exists()


def test_public_restore_rejects_non_dict_portable_mapping_without_output(tmp_path):
    source = tmp_path / "non-dict-portable-mapping.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.save(source)
    service = AnonymizerService(tmp_path / "library")
    document_id = service.import_file(source)
    service.anonymize(document_id)
    pair = service.export_pair(document_id, tmp_path / "portable.docx", confirmation=True)

    from local_anonymizer.service import _canonical_json, _recovery_checksum

    payload = json.loads(pair["recovery_path"].read_text(encoding="utf-8"))
    payload["bundle"]["mapping"] = ["not-a-map"]
    payload["bundle"]["marker_manifest"] = []
    payload["checksum_sha256"] = _recovery_checksum(payload)
    pair["recovery_path"].write_bytes(_canonical_json(payload))
    service.storage.delete_document(document_id)

    from local_anonymizer.documents import RestorationError

    restored = tmp_path / "restored.docx"
    with pytest.raises(RestorationError):
        AnonymizerService(tmp_path / "restore-library").restore_from_pair(
            pair["anonymized_path"], restored, recovery_path=pair["recovery_path"]
        )
    assert not restored.exists()


def test_public_semantic_restore_keeps_edited_existing_list_definition(tmp_path):
    source = tmp_path / "stable-list.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.add_paragraph("Remove to force semantic fallback")
    document.save(source)
    service = AnonymizerService(tmp_path / "library")
    document_id = service.import_file(source)
    service.anonymize(document_id)
    row = service.storage.get_document(document_id)
    mapping = service.storage.load_mapping(document_id, row["operation_id"])
    marker, original = next(iter(mapping.items()))
    pair = service.export_pair(document_id, tmp_path / "portable.docx", confirmation=True)

    def edit_existing_list(parts):
        numbering = etree.fromstring(parts["word/numbering.xml"])
        number = next(item for item in numbering.iter(qn("w:num")))
        number_id = number.get(qn("w:numId"))
        abstract_id = number.find(qn("w:abstractNumId")).get(qn("w:val"))
        abstract = next(
            item for item in numbering.iter(qn("w:abstractNum"))
            if item.get(qn("w:abstractNumId")) == abstract_id
        )
        level = abstract.find(qn("w:lvl"))
        level.find(qn("w:start")).set(qn("w:val"), "7")
        level.find(qn("w:numFmt")).set(qn("w:val"), "upperRoman")
        level.find(qn("w:lvlText")).set(qn("w:val"), "(%1)")
        suffix = level.find(qn("w:suff"))
        if suffix is None:
            suffix = etree.SubElement(level, qn("w:suff"))
        suffix.set(qn("w:val"), "space")
        parts["word/numbering.xml"] = etree.tostring(
            numbering, xml_declaration=True, encoding="UTF-8", standalone=True
        )
        root = etree.fromstring(parts["word/document.xml"])
        body = root.find(qn("w:body"))
        paragraph = body.findall(qn("w:p"))[0]
        properties = paragraph.find(qn("w:pPr"))
        if properties is None:
            properties = etree.Element(qn("w:pPr"))
            paragraph.insert(0, properties)
        num_pr = etree.SubElement(properties, qn("w:numPr"))
        etree.SubElement(num_pr, qn("w:numId")).set(qn("w:val"), number_id)
        body.remove(body.findall(qn("w:p"))[1])
        added = etree.Element(qn("w:p"))
        run = etree.SubElement(added, qn("w:r"))
        etree.SubElement(run, qn("w:t")).text = "User-added structure"
        body.insert(len(body) - 1, added)
        parts["word/document.xml"] = etree.tostring(
            root, xml_declaration=True, encoding="UTF-8", standalone=True
        )

    _rewrite_parts(pair["anonymized_path"], edit_existing_list)
    service.storage.delete_document(document_id)
    restored = tmp_path / "restored.docx"
    service.restore_from_pair(pair["anonymized_path"], restored)

    with ZipFile(restored) as package:
        numbering = etree.fromstring(package.read("word/numbering.xml"))
        restored_document = etree.fromstring(package.read("word/document.xml"))
    restored_number_id = restored_document.find(".//" + qn("w:numId")).get(qn("w:val"))
    restored_number = next(
        item for item in numbering.iter(qn("w:num"))
        if item.get(qn("w:numId")) == restored_number_id
    )
    restored_abstract_id = restored_number.find(qn("w:abstractNumId")).get(qn("w:val"))
    restored_abstract = next(
        item for item in numbering.iter(qn("w:abstractNum"))
        if item.get(qn("w:abstractNumId")) == restored_abstract_id
    )
    assert restored_abstract.find(".//" + qn("w:start")).get(qn("w:val")) == "7"
    assert restored_abstract.find(".//" + qn("w:numFmt")).get(qn("w:val")) == "upperRoman"
    assert restored_abstract.find(".//" + qn("w:lvlText")).get(qn("w:val")) == "(%1)"
    assert restored_abstract.find(".//" + qn("w:suff")).get(qn("w:val")) == "space"
    assert original in "".join(restored_document.itertext())
    assert marker not in "".join(restored_document.itertext())


def test_portable_pair_restores_surviving_marker_after_another_is_deleted(tmp_path):
    source = tmp_path / "two-markers.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.add_paragraph("Петров Алексей Иванович")
    document.save(source)

    service = AnonymizerService(tmp_path / "library")
    document_id = service.import_file(source)
    service.anonymize(document_id)
    row = service.storage.get_document(document_id)
    mapping = service.storage.load_mapping(document_id, row["operation_id"])
    assert len(mapping) >= 2
    pair = service.export_pair(document_id, tmp_path / "portable.docx", confirmation=True)

    edited = Document(pair["anonymized_path"])
    markers = [
        marker for marker in mapping
        if any(marker in paragraph.text for paragraph in edited.paragraphs)
    ]
    assert len(markers) >= 2
    deleted_marker, surviving_marker = markers[:2]
    deleted_value = mapping[deleted_marker]
    surviving_value = mapping[surviving_marker]
    for paragraph in edited.paragraphs:
        if deleted_marker in paragraph.text:
            paragraph.text = paragraph.text.replace(deleted_marker, "deleted entirely")
        if surviving_marker in paragraph.text:
            paragraph.text = "Edited " + paragraph.text
    edited.save(pair["anonymized_path"])
    service.storage.delete_document(document_id)

    restored = tmp_path / "restored.docx"
    report = service.restore_from_pair(pair["anonymized_path"], restored)
    restored_text = "\n".join(paragraph.text for paragraph in Document(restored).paragraphs)
    assert surviving_value in restored_text
    assert deleted_value not in restored_text
    assert deleted_marker not in restored_text
    assert report["unknown_markers"] == []


def test_portable_pair_does_not_recreate_deleted_marker_table_when_paragraph_count_balances(tmp_path):
    """A structural edit must use semantic recovery, never the donor layout."""
    source = tmp_path / "balanced-structural-edit.docx"
    document = Document()
    document.add_paragraph("\u0418\u0432\u0430\u043d\u043e\u0432 \u0421\u0435\u0440\u0433\u0435\u0439 \u041f\u0435\u0442\u0440\u043e\u0432\u0438\u0447")
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "\u041f\u0435\u0442\u0440\u043e\u0432 \u0410\u043b\u0435\u043a\u0441\u0435\u0439 \u0418\u0432\u0430\u043d\u043e\u0432\u0438\u0447"
    document.save(source)

    service = AnonymizerService(tmp_path / "library")
    document_id = service.import_file(source)
    service.anonymize(document_id)
    row = service.storage.get_document(document_id)
    mapping = service.storage.load_mapping(document_id, row["operation_id"])
    pair = service.export_pair(document_id, tmp_path / "portable.docx", confirmation=True)
    before_source = source.read_bytes()
    before_pair = pair["anonymized_path"].read_bytes()
    before_recovery = pair["recovery_path"].read_bytes()

    edited = Document(pair["anonymized_path"])
    table_marker = next(marker for marker in mapping if marker in edited.tables[0].cell(0, 0).text)
    surviving_marker = next(marker for marker in mapping if marker != table_marker)
    deleted_value, surviving_value = mapping[table_marker], mapping[surviving_marker]
    edited.tables[0]._element.getparent().remove(edited.tables[0]._element)
    # Keep paragraph cardinality balanced to expose the old layout-only route.
    edited.add_paragraph("User-added paragraph")
    for paragraph in edited.paragraphs:
        if surviving_marker in paragraph.text:
            paragraph.text = "Edited " + paragraph.text
    edited.save(pair["anonymized_path"])
    edited_bytes = pair["anonymized_path"].read_bytes()
    service.storage.delete_document(document_id)

    restored = tmp_path / "restored.docx"
    report = service.restore_from_pair(pair["anonymized_path"], restored)

    result = Document(restored)
    restored_text = "\n".join(paragraph.text for paragraph in result.paragraphs)
    assert len(result.tables) == 0
    assert deleted_value not in restored_text
    assert surviving_value in restored_text
    assert "User-added paragraph" in restored_text
    assert report["unknown_markers"] == []
    assert source.read_bytes() == before_source
    assert pair["anonymized_path"].read_bytes() == edited_bytes
    assert before_pair != edited_bytes
    assert pair["recovery_path"].read_bytes() == before_recovery


def test_portable_pair_preserves_table_removal_and_new_section_headers(tmp_path):
    source = tmp_path / "structural-edits.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "Table the user deletes"
    document.save(source)

    service = AnonymizerService(tmp_path / "library")
    document_id = service.import_file(source)
    service.anonymize(document_id)
    row = service.storage.get_document(document_id)
    mapping = service.storage.load_mapping(document_id, row["operation_id"])
    marker, value = next(iter(mapping.items()))
    pair = service.export_pair(document_id, tmp_path / "portable.docx", confirmation=True)

    edited = Document(pair["anonymized_path"])
    edited.tables[0]._element.getparent().remove(edited.tables[0]._element)
    section = edited.add_section(WD_SECTION.NEW_PAGE)
    section.header.is_linked_to_previous = False
    section.footer.is_linked_to_previous = False
    section.header.paragraphs[0].text = "Second section header " + marker
    section.footer.paragraphs[0].text = "Second section footer " + marker
    edited.save(pair["anonymized_path"])
    service.storage.delete_document(document_id)

    restored = tmp_path / "restored.docx"
    report = service.restore_from_pair(pair["anonymized_path"], restored)
    result = Document(restored)
    assert len(result.tables) == 0
    assert len(result.sections) == 2
    assert value in result.sections[1].header.paragraphs[0].text
    assert value in result.sections[1].footer.paragraphs[0].text
    assert report["unknown_markers"] == []


def test_fallback_restore_rejects_referenced_list_without_definition(tmp_path):
    source, pair = _prepare_snapshot_core_pair(tmp_path)

    def add_dangling_list_reference(parts):
        document = etree.fromstring(parts["word/document.xml"])
        paragraph = document.find(".//" + qn("w:p"))
        properties = paragraph.find(qn("w:pPr"))
        if properties is None:
            properties = etree.Element(qn("w:pPr"))
            paragraph.insert(0, properties)
        num_pr = etree.SubElement(properties, qn("w:numPr"))
        etree.SubElement(num_pr, qn("w:numId")).set(qn("w:val"), "999")
        parts["word/document.xml"] = etree.tostring(
            document, xml_declaration=True, encoding="UTF-8", standalone=True
        )

    _rewrite_parts(pair["anonymized_path"], add_dangling_list_reference)
    restored = tmp_path / "restored.docx"
    from local_anonymizer.documents import RestorationError

    with pytest.raises(RestorationError, match="нумерация"):
        AnonymizerService(tmp_path / "library").restore_from_pair(
            pair["anonymized_path"], restored
        )
    assert not restored.exists()


def test_format_core_graft_wraps_malformed_edited_xml_as_restoration_error(tmp_path):
    _, pair = _prepare_snapshot_core_pair(tmp_path)
    from local_anonymizer.documents import RestorationError, _graft_snapshot_format_core
    from local_anonymizer.service import _read_artifact_identity

    service = AnonymizerService(tmp_path / "restore-library")
    document_id, operation_id = _read_artifact_identity(pair["anonymized_path"])
    payload = AnonymizerService._read_recovery_file(pair["recovery_path"])
    _, archive = service.storage.decode_restore_payload(
        payload["bundle"], document_id, operation_id
    )
    service.storage.connection.close()

    damaged = tmp_path / "damaged.docx"
    damaged.write_bytes(pair["anonymized_path"].read_bytes())
    _rewrite_parts(damaged, lambda parts: parts.__setitem__("word/document.xml", b"<w:document"))

    with pytest.raises(RestorationError):
        _graft_snapshot_format_core(damaged, archive)


def test_public_restore_normalizes_malformed_edited_xml_without_output(tmp_path):
    _, pair = _prepare_snapshot_core_pair(tmp_path)
    _rewrite_parts(pair["anonymized_path"], lambda parts: parts.__setitem__("word/document.xml", b"<w:document"))
    restored = tmp_path / "restored.docx"
    from local_anonymizer.documents import RestorationError

    with pytest.raises(RestorationError):
        AnonymizerService(tmp_path / "library").restore_from_pair(pair["anonymized_path"], restored)
    assert not restored.exists()


def test_soft_compat_mode_strips_unknown_word_formatting_without_blocking(tmp_path):
    """Soft mode cuts unsupported standard Word formatting instead of failing."""
    source = tmp_path / "soft-compat.docx"
    document = Document()
    paragraph = document.add_paragraph("Synthetic text [ФИО-1]")
    _child(paragraph._p.get_or_add_pPr(), "framePr", h="100", w="100")
    document.save(source)

    strict = _sanitize_package(source)
    assert any("word/document.xml:foreign-xml" in str(warning) for warning in strict)

    # Build a fresh copy with the same unsupported structure for the soft run.
    soft_source = tmp_path / "soft-compat-soft.docx"
    document = Document()
    paragraph = document.add_paragraph("Synthetic text [ФИО-1]")
    _child(paragraph._p.get_or_add_pPr(), "framePr", h="100", w="100")
    document.save(soft_source)

    assert _sanitize_package(soft_source, soft_compat=True) == []
    with ZipFile(soft_source) as package:
        root = etree.fromstring(package.read("word/document.xml"))
    assert root.find(".//" + qn("w:framePr")) is None


def test_invalid_keep_lines_value_remains_a_blocking_sanitizer_warning(tmp_path):
    source = tmp_path / "invalid-keep-lines.docx"
    document = Document()
    paragraph = document.add_paragraph("Synthetic only")
    _child(paragraph._p.get_or_add_pPr(), "keepLines", val="invalid-value")
    document.save(source)

    warnings = _sanitize_package(source)

    assert any("word/document.xml:foreign-xml" in str(warning) for warning in warnings)
    with ZipFile(source) as package:
        root = etree.fromstring(package.read("word/document.xml"))
    assert root.find(".//" + qn("w:keepLines")) is None


def test_bookmark_near_miss_in_a_run_remains_a_blocking_sanitizer_warning(tmp_path):
    source = tmp_path / "bookmark-near-miss.docx"
    document = Document()
    run = document.add_paragraph("Visible")._p.find(qn("w:r"))
    _child(run, "bookmarkStart", id="7", name="SyntheticBookmark")
    document.save(source)

    warnings = _sanitize_package(source)

    assert any("word/document.xml:foreign-xml" in str(warning) for warning in warnings)
    with ZipFile(source) as package:
        root = etree.fromstring(package.read("word/document.xml"))
    assert root.find(".//" + qn("w:bookmarkStart")) is None


def _inject_standard_cell_metadata_and_footer5_field(parts):
    """Model the reported Word table metadata and a complex footer5 field."""
    document_root = etree.fromstring(parts["word/document.xml"])
    body = document_root.find(qn("w:body"))
    cell_properties = document_root.findall(".//" + qn("w:tcPr"))
    assert body is not None and len(cell_properties) == 140
    for index, properties in enumerate(cell_properties):
        margins = etree.SubElement(properties, qn("w:tcMar"))
        for edge in ("top", "left", "bottom", "right", "start", "end"):
            margin = etree.SubElement(margins, qn(f"w:{edge}"))
            margin.set(qn("w:type"), "nil" if edge in {"start", "end"} else "dxa")
            margin.set(qn("w:w"), "0" if edge in {"start", "end"} else "72")
        if index < 15:
            borders = etree.SubElement(properties, qn("w:tcBorders"))
            for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
                border = etree.SubElement(borders, qn(f"w:{edge}"))
                border.set(qn("w:val"), "single")

    control = etree.Element(qn("w:sdt"))
    properties = etree.SubElement(control, qn("w:sdtPr"))
    tag = etree.SubElement(properties, qn("w:tag"))
    tag.set(qn("w:val"), "SyntheticTag")
    content = etree.SubElement(control, qn("w:sdtContent"))
    paragraph = etree.SubElement(content, qn("w:p"))
    run = etree.SubElement(paragraph, qn("w:r"))
    etree.SubElement(run, qn("w:t")).text = "Content-control [ФИО-1]"
    edited = etree.Element(qn("w:p"))
    run = etree.SubElement(edited, qn("w:r"))
    etree.SubElement(run, qn("w:t")).text = "Edited [ФИО-1]"
    section_properties = body.find(qn("w:sectPr"))
    assert section_properties is not None
    body.insert(body.index(section_properties), control)
    body.insert(body.index(section_properties), edited)
    parts["word/document.xml"] = etree.tostring(
        document_root, xml_declaration=True, encoding="UTF-8", standalone=True
    )

    footer = etree.fromstring(parts.pop("word/footer1.xml"))
    footer_paragraph = footer.find(".//" + qn("w:p"))
    assert footer_paragraph is not None
    for field_type in ("begin",):
        _child(_child(footer_paragraph, "r"), "fldChar", fldCharType=field_type)
    instruction = _child(_child(footer_paragraph, "r"), "instrText")
    instruction.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    instruction.text = " MERGEFIELD private "
    _child(_child(footer_paragraph, "r"), "fldChar", fldCharType="separate")
    cached = _child(_child(footer_paragraph, "r"), "t")
    cached.text = "Footer marker [ФИО-1]"
    _child(_child(footer_paragraph, "r"), "fldChar", fldCharType="end")
    parts["word/footer5.xml"] = etree.tostring(
        footer, xml_declaration=True, encoding="UTF-8", standalone=True
    )

    relationships = etree.fromstring(parts["word/_rels/document.xml.rels"])
    footer_relationships = [
        relationship for relationship in relationships
        if relationship.get("Target") == "footer1.xml"
    ]
    assert len(footer_relationships) == 1
    footer_relationships[0].set("Target", "footer5.xml")
    parts["word/_rels/document.xml.rels"] = etree.tostring(
        relationships, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    content_types = etree.fromstring(parts["[Content_Types].xml"])
    footer_overrides = [
        override for override in content_types
        if override.get("PartName") == "/word/footer1.xml"
    ]
    assert len(footer_overrides) == 1
    footer_overrides[0].set("PartName", "/word/footer5.xml")
    parts["[Content_Types].xml"] = etree.tostring(
        content_types, xml_declaration=True, encoding="UTF-8", standalone=True
    )


def test_standard_cell_metadata_and_footer5_field_restore_through_portable_pair(tmp_path):
    source = tmp_path / "standard-cell-metadata.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.add_table(rows=14, cols=10)
    document.sections[0].footer.paragraphs[0].text = "Footer"
    document.save(source)

    service = AnonymizerService(tmp_path / "library")
    document_id = service.import_file(source)
    service.anonymize(document_id)
    pair = service.export_pair(document_id, tmp_path / "portable.docx", confirmation=True)
    _rewrite_parts(pair["anonymized_path"], _inject_standard_cell_metadata_and_footer5_field)

    sanitized = tmp_path / "sanitized-standard-cell-metadata.docx"
    sanitized.write_bytes(pair["anonymized_path"].read_bytes())
    assert _sanitize_package(sanitized) == []
    with ZipFile(sanitized) as package:
        document_root = etree.fromstring(package.read("word/document.xml"))
        footer = etree.fromstring(package.read("word/footer5.xml"))
    namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    assert len(document_root.xpath(".//w:tcMar", namespaces=namespaces)) == 140
    for edge in ("top", "left", "bottom", "right", "start", "end"):
        assert len(document_root.xpath(f".//w:tcMar/w:{edge}", namespaces=namespaces)) == 140
    assert len(document_root.xpath(".//w:tcBorders/w:insideH", namespaces=namespaces)) == 15
    assert len(document_root.xpath(".//w:tcBorders/w:insideV", namespaces=namespaces)) == 15
    assert document_root.xpath(".//w:sdtPr/w:tag", namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}) == []
    assert footer.xpath(".//w:fldChar|.//w:instrText", namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}) == []
    assert "Footer marker [ФИО-1]" in "".join(footer.itertext())

    service.storage.delete_document(document_id)
    restored = tmp_path / "restored.docx"
    report = service.restore_from_pair(pair["anonymized_path"], restored)

    restored_document = Document(restored)
    footer_text = "\n".join(paragraph.text for paragraph in restored_document.sections[0].footer.paragraphs)
    assert "Иванов Сергей Петрович" in footer_text
    assert "[ФИО-1]" not in footer_text
    assert report["unknown_markers"] == []


@pytest.mark.parametrize(
    "near_miss",
    ("malformed-value", "border-context", "margin-border-attribute", "wrong-parent"),
)
def test_tc_mar_near_misses_remain_blocking_sanitizer_warnings(tmp_path, near_miss):
    source = tmp_path / "malformed-tc-mar.docx"
    document = Document()
    document.add_table(rows=1, cols=1).cell(0, 0).text = "Synthetic cell"
    document.save(source)

    def inject(parts):
        root = etree.fromstring(parts["word/document.xml"])
        cell_properties = root.find(".//" + qn("w:tcPr"))
        assert cell_properties is not None
        if near_miss == "border-context":
            borders = etree.SubElement(cell_properties, qn("w:tcBorders"))
            top = etree.SubElement(borders, qn("w:top"))
            top.set(qn("w:val"), "single")
            top.set(qn("w:type"), "dxa")
            top.set(qn("w:w"), "72")
        else:
            parent = cell_properties if near_miss == "malformed-value" else root.find(".//" + qn("w:tc"))
            if near_miss == "margin-border-attribute":
                parent = cell_properties
            assert parent is not None
            margins = etree.SubElement(parent, qn("w:tcMar"))
            top = etree.SubElement(margins, qn("w:top"))
            top.set(qn("w:type"), "auto" if near_miss == "malformed-value" else "dxa")
            top.set(qn("w:w"), "72")
            if near_miss == "margin-border-attribute":
                top.set(qn("w:val"), "single")
        parts["word/document.xml"] = etree.tostring(root)

    _rewrite_parts(source, inject)
    warnings = _sanitize_package(source)

    assert any("word/document.xml:foreign-xml" in str(warning) for warning in warnings)


@pytest.mark.parametrize("near_miss", ("extra-attribute", "wrong-parent", "wrong-namespace"))
def test_content_control_tag_near_misses_remain_blocking_sanitizer_warnings(tmp_path, near_miss):
    source = tmp_path / "malformed-content-control-tag.docx"
    document = Document()
    document.add_paragraph("Synthetic only")
    document.save(source)

    def inject(parts):
        root = etree.fromstring(parts["word/document.xml"])
        body = root.find(qn("w:body"))
        assert body is not None
        control = etree.Element(qn("w:sdt"))
        properties = etree.SubElement(control, qn("w:sdtPr"))
        parent = properties if near_miss != "wrong-parent" else etree.SubElement(control, qn("w:sdtContent"))
        tag = etree.SubElement(
            parent,
            "{urn:hostile}tag" if near_miss == "wrong-namespace" else qn("w:tag"),
        )
        tag.set(qn("w:val"), "SyntheticTag")
        if near_miss == "extra-attribute":
            tag.set(qn("w:bad"), "unexpected")
        content = parent if near_miss == "wrong-parent" else etree.SubElement(control, qn("w:sdtContent"))
        paragraph = etree.SubElement(content, qn("w:p"))
        run = etree.SubElement(paragraph, qn("w:r"))
        etree.SubElement(run, qn("w:t")).text = "Visible"
        section_properties = body.find(qn("w:sectPr"))
        assert section_properties is not None
        body.insert(body.index(section_properties), control)
        parts["word/document.xml"] = etree.tostring(root)

    _rewrite_parts(source, inject)
    warnings = _sanitize_package(source)

    assert any("word/document.xml:foreign-xml" in str(warning) for warning in warnings)
