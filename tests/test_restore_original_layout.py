"""Restore must rebuild on the original snapshot, preserving Word fields and styles."""
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from lxml import etree

from local_anonymizer.service import AnonymizerService
from local_anonymizer.documents import RestorationError, _preflight_docx_package

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"

TOC_PARAGRAPH = (
    '<w:p xmlns:w="{w}"><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
    '<w:r><w:instrText xml:space="preserve"> TOC \\o "1-1" </w:instrText></w:r>'
    '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
    '<w:r><w:t>Contents entry</w:t></w:r>'
    '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
)
BOOKMARK_START = '<w:bookmarkStart xmlns:w="{w}" w:id="90" w:name="_Toc900001"/>'
BOOKMARK_END = '<w:bookmarkEnd xmlns:w="{w}" w:id="90"/>'
HYPERLINK_URL = "https://example.invalid/reference"


def _build_source(path):
    document = Document()
    custom = document.styles.add_style("SyntheticCustomStyle", WD_STYLE_TYPE.PARAGRAPH)
    custom.font.size = None
    document.add_paragraph("Title paragraph", style="Title")
    document.add_paragraph("Иванов Сергей Петрович")
    document.add_paragraph("Plain synthetic paragraph", style="SyntheticCustomStyle")
    document.save(path)

    with ZipFile(path) as archive:
        parts = {info.filename: archive.read(info.filename) for info in archive.infolist()}
    document_xml = etree.fromstring(parts["word/document.xml"])
    body = document_xml.find(f"{{{W}}}body")

    toc = etree.fromstring(TOC_PARAGRAPH.format(w=W))
    body.insert(0, toc)

    custom_paragraph = None
    for paragraph in body.iter(f"{{{W}}}p"):
        style = paragraph.find(f"{{{W}}}pPr/{{{W}}}pStyle")
        if style is not None and style.get(f"{{{W}}}val", "").startswith("SyntheticCustom"):
            custom_paragraph = paragraph
            break
    assert custom_paragraph is not None
    start = etree.fromstring(BOOKMARK_START.format(w=W))
    end = etree.fromstring(BOOKMARK_END.format(w=W))
    body.insert(list(body).index(custom_paragraph), start)
    body.insert(list(body).index(custom_paragraph) + 1, end)

    rels = etree.fromstring(parts["word/_rels/document.xml.rels"])
    link_rel = etree.SubElement(rels, f"{{{PR}}}Relationship")
    link_rel.set("Id", "rId900")
    link_rel.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink")
    link_rel.set("Target", HYPERLINK_URL)
    link_rel.set("TargetMode", "External")
    name_paragraph = None
    for paragraph in body.iter(f"{{{W}}}p"):
        if "Иванов" in "".join(t.text or "" for t in paragraph.iter(f"{{{W}}}t")):
            name_paragraph = paragraph
            break
    assert name_paragraph is not None
    run = name_paragraph.find(f"{{{W}}}r")
    link = etree.SubElement(name_paragraph, f"{{{W}}}hyperlink")
    link.set(f"{{{R}}}id", "rId900")
    name_paragraph.remove(run)
    link.append(run)

    inner_start = etree.SubElement(custom_paragraph, f"{{{W}}}bookmarkStart")
    inner_start.set(f"{{{W}}}id", "91")
    inner_start.set(f"{{{W}}}name", "inner-edit-bookmark")
    custom_paragraph.insert(1 if custom_paragraph.find(f"{{{W}}}pPr") is not None else 0, inner_start)
    inner_end = etree.SubElement(custom_paragraph, f"{{{W}}}bookmarkEnd")
    inner_end.set(f"{{{W}}}id", "91")

    parts["word/document.xml"] = etree.tostring(
        document_xml, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    parts["word/_rels/document.xml.rels"] = etree.tostring(
        rels, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)


def _simulate_word_resave(path, *, rename_styles=True, edit_text=True):
    with ZipFile(path) as archive:
        parts = {info.filename: archive.read(info.filename) for info in archive.infolist()}
    document_xml = etree.fromstring(parts["word/document.xml"])
    styles_xml = etree.fromstring(parts["word/styles.xml"])
    settings_xml = etree.fromstring(parts["word/settings.xml"])

    if rename_styles:
        renames = {"Title": "a3", "Normal": "a"}
        for style in styles_xml.iter(f"{{{W}}}style"):
            sid = style.get(f"{{{W}}}styleId")
            if sid in renames:
                style.set(f"{{{W}}}styleId", renames[sid])
        for element in styles_xml.iter():
            if etree.QName(element).localname in {"basedOn", "next", "link"}:
                value = element.get(f"{{{W}}}val")
                if value in renames:
                    element.set(f"{{{W}}}val", renames[value])
        for element in document_xml.iter():
            if etree.QName(element).localname in {"pStyle", "rStyle"}:
                value = element.get(f"{{{W}}}val")
                if value in renames:
                    element.set(f"{{{W}}}val", renames[value])

    if edit_text:
        for paragraph in document_xml.iter(f"{{{W}}}p"):
            texts = [t for t in paragraph.iter(f"{{{W}}}t")]
            if texts and "Plain synthetic paragraph" in "".join(t.text or "" for t in texts):
                texts[0].text = (texts[0].text or "") + " edited"
                break

    zoom = etree.SubElement(settings_xml, f"{{{W}}}zoom")
    zoom.set(f"{{{W}}}percent", "120")

    parts["word/document.xml"] = etree.tostring(
        document_xml, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    parts["word/styles.xml"] = etree.tostring(
        styles_xml, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    parts["word/settings.xml"] = etree.tostring(
        settings_xml, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)


def _export_pair(tmp_path):
    service = AnonymizerService(tmp_path / "app")
    source = tmp_path / "source.docx"
    _build_source(source)
    document_id = service.import_file(source)
    service.anonymize(document_id)
    pair = service.export_pair(document_id, tmp_path / "edited.docx")
    service.storage.delete_document(document_id)
    return service, pair["anonymized_path"]


def _read_parts(path):
    with ZipFile(path) as archive:
        return {
            "document": etree.fromstring(archive.read("word/document.xml")),
            "styles": etree.fromstring(archive.read("word/styles.xml")),
            "rels": etree.fromstring(archive.read("word/_rels/document.xml.rels")),
        }


def test_restore_rebuilds_original_layout_after_word_resave(tmp_path):
    service, edited = _export_pair(tmp_path)
    _simulate_word_resave(edited, rename_styles=True, edit_text=True)

    restored = tmp_path / "restored.docx"
    report = service.restore_from_pair(edited, restored)

    assert report["unknown_markers"] == []
    parts = _read_parts(restored)
    document_xml = parts["document"]
    styles_xml = parts["styles"]
    rels = parts["rels"]
    text = "".join(t.text or "" for t in document_xml.iter(f"{{{W}}}t"))
    assert "Иванов Сергей Петрович" in text
    assert "Plain synthetic paragraph edited" in text
    assert list(document_xml.iter(f"{{{W}}}fldChar")), "TOC field runs must return"
    assert any(
        "TOC" in (node.text or "") for node in document_xml.iter(f"{{{W}}}instrText")
    ), "TOC instruction text must return"
    assert any(
        node.get(f"{{{W}}}name") == "_Toc900001"
        for node in document_xml.iter(f"{{{W}}}bookmarkStart")
    ), "bookmarks must return"
    assert any(
        node.get(f"{{{W}}}name") == "inner-edit-bookmark"
        for node in document_xml.iter(f"{{{W}}}bookmarkStart")
    ), "bookmarks inside an edited paragraph must be re-anchored from the original"
    assert any(
        node.get(f"{{{R}}}id") for node in document_xml.iter(f"{{{W}}}hyperlink")
    ), "hyperlink structure must return"
    assert any(
        rel.get("TargetMode") == "External" and rel.get("Target") == HYPERLINK_URL
        for rel in rels
    ), "original hyperlink relationship must return"
    style_ids = {
        style.get(f"{{{W}}}styleId") for style in styles_xml.iter(f"{{{W}}}style")
    }
    assert "Title" in style_ids
    assert "SyntheticCustomStyle" in style_ids
    assert any(
        style.get(f"{{{W}}}val") == "Title"
        for style in document_xml.iter(f"{{{W}}}pStyle")
    ), "original style identifiers must be referenced again"
    _preflight_docx_package(restored)


def test_restore_rebuilds_original_layout_without_style_renames(tmp_path):
    service, edited = _export_pair(tmp_path)
    _simulate_word_resave(edited, rename_styles=False, edit_text=True)

    restored = tmp_path / "restored.docx"
    report = service.restore_from_pair(edited, restored)

    assert report["unknown_markers"] == []
    parts = _read_parts(restored)
    assert list(parts["document"].iter(f"{{{W}}}fldChar"))
    assert any(
        rel.get("Target") == HYPERLINK_URL for rel in parts["rels"]
    )


def test_restore_with_added_paragraph_still_uses_legacy_path(tmp_path):
    service, edited = _export_pair(tmp_path)
    document = Document(edited)
    document.add_paragraph("Word edit remains")
    document.save(edited)

    restored = tmp_path / "restored.docx"
    report = service.restore_from_pair(edited, restored)

    assert report["unknown_markers"] == []
    with ZipFile(restored) as archive:
        body = etree.fromstring(archive.read("word/document.xml"))
    texts = "".join(body.itertext())
    assert "Иванов Сергей Петрович" in texts
    assert "Word edit remains" in texts


def test_hostile_graft_candidate_fails_closed(tmp_path):
    service, edited = _export_pair(tmp_path)
    with ZipFile(edited) as archive:
        parts = {info.filename: archive.read(info.filename) for info in archive.infolist()}
    document_xml = etree.fromstring(parts["word/document.xml"])
    for paragraph in document_xml.iter(f"{{{W}}}p"):
        texts = [t for t in paragraph.iter(f"{{{W}}}t")]
        if texts and "Plain synthetic paragraph" in "".join(t.text or "" for t in texts):
            texts[0].text = (texts[0].text or "") + " edited"
            properties = paragraph.find(f"{{{W}}}pPr")
            if properties is None:
                properties = etree.SubElement(paragraph, f"{{{W}}}pPr")
                paragraph.insert(0, properties)
            hostile = etree.SubElement(properties, "{urn:hostile}payload")
            hostile.text = "CANARY"
            break
    parts["word/document.xml"] = etree.tostring(
        document_xml, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    with ZipFile(edited, "w", ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)

    restored = tmp_path / "restored.docx"
    with pytest.raises((RestorationError, RuntimeError, ValueError)):
        service.restore_from_pair(edited, restored)
    assert not restored.exists()
