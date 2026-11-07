"""Synthetic Word settings regressions; no real-user XML fixtures."""
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
from docx import Document
from lxml import etree

from local_anonymizer.service import AnonymizerService
from local_anonymizer.documents import _sanitize_package

from local_anonymizer.documents import _scrub_unknown_docx_xml

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def test_word_saved_zoom_is_discarded_without_blocking_restore():
    # Word persists the user's view zoom, not document formatting.
    root = etree.fromstring(
        f'<w:settings xmlns:w="{W}"><w:zoom w:percent="160"/></w:settings>'
    )
    clean, blocked = _scrub_unknown_docx_xml("word/settings.xml", root)
    assert not blocked
    assert len(clean) == 0


@pytest.mark.parametrize("percent", ["10", "100", "160", "500"])
def test_zoom_safe_range_is_removed(percent):
    root = etree.fromstring(
        f'<w:settings xmlns:w="{W}"><w:zoom w:percent="{percent}"/></w:settings>'
    )
    clean, blocked = _scrub_unknown_docx_xml("word/settings.xml", root)
    assert not blocked
    assert len(clean) == 0


@pytest.mark.parametrize("fragment", [
    '<w:zoom w:percent="9"/>',
    '<w:zoom w:percent="501"/>',
    '<w:zoom w:percent="0160"/>',
    '<w:zoom w:percent="+160"/>',
    '<w:zoom w:percent="160%"/>',
    '<w:zoom w:percent="CANARY"/>',
    '<w:zoom w:percent="987654321"/>',
    '<w:zoom w:percent="160" w:val="CANARY"/>',
    '<w:zoom w:percent="160" x:val="CANARY"/>',
    '<w:zoom w:percent="160" percent="CANARY"/>',
    '<w:zoom x:percent="160"/>',
    '<w:zoom w:percent="160">CANARY</w:zoom>',
    '<w:zoom w:percent="160"/>CANARY',
    '<w:zoom w:percent="100"><w:rsids/></w:zoom>',
    '<w:zoom w:percent="160"><x:hidden>CANARY</x:hidden></w:zoom>',
    '<w:compat><w:zoom w:percent="160"/></w:compat>',
    '<x:zoom w:percent="CANARY"/>',
    '<w:compat><w:compatSetting w:name="compatibilityMode" w:uri="CANARY" w:val="15"/></w:compat>',
    '<w:compat><w:compatSetting w:name="ProjectCanary2026" w:uri="http://schemas.microsoft.com/office/word" w:val="1"/></w:compat>',
    '<w:compat><w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="99"/></w:compat>',
])
def test_hostile_settings_are_still_blocked(fragment):
    root = etree.fromstring(
        f'<w:settings xmlns:w="{W}" xmlns:x="urn:hostile">{fragment}</w:settings>'
    )
    clean, blocked = _scrub_unknown_docx_xml("word/settings.xml", root)
    assert blocked
    assert b"CANARY" not in etree.tostring(clean)


@pytest.mark.parametrize("part,root_tag,container", [
    ("word/document.xml", "document", "body"),
    ("word/styles.xml", "styles", "style"),
    ("word/webSettings.xml", "webSettings", "divs"),
])
def test_zoom_permission_does_not_cross_parts(part, root_tag, container):
    root = etree.fromstring(
        f'<w:{root_tag} xmlns:w="{W}"><w:{container}>'
        f'<w:zoom w:percent="160"/></w:{container}></w:{root_tag}>'
    )
    clean, blocked = _scrub_unknown_docx_xml(part, root)
    assert blocked
    assert b"160" not in etree.tostring(clean)


@pytest.mark.parametrize(("part", "xml"), [
    (
        "word/document.xml",
        '<w:document xmlns:w="{w}"><w:body><w:sdt><w:sdtPr>'
        '<w:id w:val="9999999999"/></w:sdtPr><w:sdtContent><w:p/></w:sdtContent>'
        '</w:sdt></w:body></w:document>',
    ),
    (
        "word/document.xml",
        '<w:document xmlns:w="{w}"><w:body><w:tbl><w:tr><w:trPr>'
        '<w:cnfStyle w:val="000000000000" w:firstRow="1"/></w:trPr></w:tr>'
        '</w:tbl></w:body></w:document>',
    ),
    (
        "word/styles.xml",
        '<w:styles xmlns:w="{w}"><w:latentStyles w:defUIPriority="42"/></w:styles>',
    ),
    (
        "word/numbering.xml",
        '<w:numbering xmlns:w="{w}" xmlns:x="urn:hostile"><w:abstractNum w:abstractNumId="0">'
        '<w:lvl w:ilvl="0" tplc="0409001D"/></w:abstractNum></w:numbering>',
    ),
    (
        "word/numbering.xml",
        '<w:numbering xmlns:w="{w}" xmlns:x="urn:hostile"><w:abstractNum w:abstractNumId="0">'
        '<w:lvl w:ilvl="0" x:tplc="0409001D"/></w:abstractNum></w:numbering>',
    ),
    (
        "word/styles.xml",
        '<w:styles xmlns:w="{w}" xmlns:x="urn:hostile"><w:latentStyles x:defUIPriority="99"/></w:styles>',
    ),
])
def test_word_metadata_lookalikes_are_blocked(part, xml):
    root = etree.fromstring(xml.format(w=W))
    clean, blocked = _scrub_unknown_docx_xml(part, root)
    assert blocked
    assert b"9999999999" not in etree.tostring(clean)
    assert b"defUIPriority=\"42\"" not in etree.tostring(clean)


def _replace_settings(path, settings):
    with ZipFile(path) as archive:
        parts = {info.filename: archive.read(info.filename) for info in archive.infolist()}
    parts["word/settings.xml"] = settings
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)


def _replace_parts(path, replacements):
    with ZipFile(path) as archive:
        parts = {info.filename: archive.read(info.filename) for info in archive.infolist()}
    parts.update(replacements)
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)


def test_public_pair_restore_after_synthetic_word_zoom_edit(tmp_path):
    service = AnonymizerService(tmp_path / "app")
    source = tmp_path / "source.docx"
    doc = Document()
    doc.add_paragraph("Иванов Сергей Петрович")
    doc.add_paragraph("password: Secret123!")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).merge(table.cell(1, 0)).text = "Merged"
    table.cell(0, 1).paragraphs[0].add_run("Bold").bold = True
    doc.save(source)
    doc_id = service.import_file(source)
    service.anonymize(doc_id)
    pair = service.export_pair(doc_id, tmp_path / "edited.docx")
    edited = pair["anonymized_path"]
    doc = Document(edited)
    doc.add_paragraph("Word edit remains")
    doc.save(edited)
    with ZipFile(edited) as archive:
        settings = etree.fromstring(archive.read("word/settings.xml"))
    for zoom in list(settings.findall(f"{{{W}}}zoom")):
        settings.remove(zoom)
    etree.SubElement(settings, f"{{{W}}}zoom").set(f"{{{W}}}percent", "160")
    _replace_settings(edited, etree.tostring(settings))
    service.storage.delete_document(doc_id)
    restored = tmp_path / "restored.docx"
    report = service.restore_from_pair(edited, restored)
    assert report["unknown_markers"] == []
    with ZipFile(restored) as archive:
        body = etree.fromstring(archive.read("word/document.xml"))
        payload = b"".join(archive.read(name) for name in archive.namelist())
    texts = "".join(body.itertext())
    assert "Иванов Сергей Петрович" in texts
    assert "Word edit remains" in texts
    assert "Secret123!" in texts
    assert len(body.findall(f".//{{{W}}}tbl")) == 1
    assert len(body.findall(f".//{{{W}}}vMerge")) == 2
    assert body.find(f".//{{{W}}}b") is not None
    assert _sanitize_package(restored) == []


def test_public_pair_restore_accepts_word_layout_and_session_metadata_after_edit(tmp_path):
    service = AnonymizerService(tmp_path / "app")
    source = tmp_path / "source.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "Word table"
    document.add_paragraph("Numbered", style="List Number")
    document.save(source)
    document_id = service.import_file(source)
    service.anonymize(document_id)
    pair = service.export_pair(document_id, tmp_path / "edited.docx")
    edited = pair["anonymized_path"]

    with ZipFile(edited) as archive:
        document_xml = etree.fromstring(archive.read("word/document.xml"))
        numbering_xml = etree.fromstring(archive.read("word/numbering.xml"))
        settings_xml = etree.fromstring(archive.read("word/settings.xml"))
        styles_xml = etree.fromstring(archive.read("word/styles.xml"))
    body = document_xml.find(f"{{{W}}}body")
    content_control = etree.Element(f"{{{W}}}sdt")
    properties = etree.SubElement(content_control, f"{{{W}}}sdtPr")
    etree.SubElement(properties, f"{{{W}}}id").set(f"{{{W}}}val", "123456")
    content = etree.SubElement(content_control, f"{{{W}}}sdtContent")
    paragraph = etree.SubElement(content, f"{{{W}}}p")
    run = etree.SubElement(paragraph, f"{{{W}}}r")
    etree.SubElement(run, f"{{{W}}}t").text = "Content control text"
    body.insert(0, content_control)
    table_row = document_xml.find(f".//{{{W}}}tr")
    row_properties = table_row.find(f"{{{W}}}trPr")
    if row_properties is None:
        row_properties = etree.Element(f"{{{W}}}trPr")
        table_row.insert(0, row_properties)
    cnf_style = etree.SubElement(row_properties, f"{{{W}}}cnfStyle")
    cnf_style.set(f"{{{W}}}val", "100000000000")
    cnf_style.set(f"{{{W}}}firstRow", "1")
    level = numbering_xml.find(f".//{{{W}}}lvl")
    level.set(f"{{{W}}}tplc", "0409001D")
    compatibility = settings_xml.find(f"{{{W}}}compat")
    if compatibility is None:
        compatibility = etree.SubElement(settings_xml, f"{{{W}}}compat")
    setting = etree.SubElement(compatibility, f"{{{W}}}compatSetting")
    setting.set(f"{{{W}}}name", "compatibilityMode")
    setting.set(f"{{{W}}}uri", "http://schemas.microsoft.com/office/word")
    setting.set(f"{{{W}}}val", "15")
    word_compatibility = etree.SubElement(compatibility, f"{{{W}}}compatSetting")
    word_compatibility.set(f"{{{W}}}name", "enableOpenTypeFeatures")
    word_compatibility.set(f"{{{W}}}uri", "http://schemas.microsoft.com/office/word")
    word_compatibility.set(f"{{{W}}}val", "1")
    latent = styles_xml.find(f"{{{W}}}latentStyles")
    if latent is None:
        latent = etree.SubElement(styles_xml, f"{{{W}}}latentStyles")
    latent.set(f"{{{W}}}defUIPriority", "99")
    _replace_parts(edited, {
        "word/document.xml": etree.tostring(document_xml),
        "word/numbering.xml": etree.tostring(numbering_xml),
        "word/settings.xml": etree.tostring(settings_xml),
        "word/styles.xml": etree.tostring(styles_xml),
    })
    service.storage.delete_document(document_id)

    restored = tmp_path / "restored.docx"
    report = service.restore_from_pair(edited, restored)

    assert report["unknown_markers"] == []
    restored_text = "\n".join(paragraph.text for paragraph in Document(restored).paragraphs)
    with ZipFile(restored) as archive:
        restored_body = etree.fromstring(archive.read("word/document.xml"))
    assert "Иванов Сергей Петрович" in restored_text
    assert "Content control text" in "".join(restored_body.itertext())
    assert _sanitize_package(restored) == []
