"""Restore must rebuild on the original snapshot, preserving Word fields and styles."""
import hashlib
import shutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.enum.style import WD_STYLE_TYPE
from lxml import etree

from local_anonymizer.service import AnonymizerService
from local_anonymizer.documents import (
    RestorationError, _is_benign_run_toggle_markup,
    _paragraph_format_signature, _preflight_docx_package,
)

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


def test_formatting_only_edit_cannot_drop_original_field_runs(tmp_path, monkeypatch):
    service, edited = _export_pair(tmp_path)
    with ZipFile(edited) as archive:
        parts = {info.filename: archive.read(info.filename) for info in archive.infolist()}
    document_xml = etree.fromstring(parts["word/document.xml"])
    field_paragraph = next(
        paragraph for paragraph in document_xml.iter(f"{{{W}}}p")
        if "Contents entry" in "".join(node.text or "" for node in paragraph.iter(f"{{{W}}}t"))
    )
    first_run = next(field_paragraph.iter(f"{{{W}}}r"))
    properties = first_run.find(f"{{{W}}}rPr")
    if properties is None:
        properties = etree.Element(f"{{{W}}}rPr")
        first_run.insert(0, properties)
    etree.SubElement(properties, f"{{{W}}}noProof")
    parts["word/document.xml"] = etree.tostring(
        document_xml, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    with ZipFile(edited, "w", ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    layout_results = _spy_layout_results(monkeypatch)

    restored = tmp_path / "restored.docx"
    report = service.restore_from_pair(edited, restored)

    assert report["unknown_markers"] == []
    assert layout_results and all(result is not None for result in layout_results)
    parts = _read_parts(restored)
    assert list(parts["document"].iter(f"{{{W}}}fldChar"))
    assert any(
        "TOC" in (node.text or "") for node in parts["document"].iter(f"{{{W}}}instrText")
    )


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


def _build_multigroup_source(path):
    """One paragraph: plain name run, hard break, bold name run (two text groups)."""
    document = Document()
    document.add_paragraph("placeholder")
    document.save(path)
    with ZipFile(path) as archive:
        parts = {info.filename: archive.read(info.filename) for info in archive.infolist()}
    document_xml = etree.fromstring(parts["word/document.xml"])
    paragraph = next(iter(document_xml.iter(f"{{{W}}}p")))
    run = paragraph.find(f"{{{W}}}r")
    paragraph.remove(run)
    first = etree.SubElement(paragraph, f"{{{W}}}r")
    first_text = etree.SubElement(first, f"{{{W}}}t")
    first_text.text = "Иванов Сергей Петрович"
    breaker = etree.SubElement(paragraph, f"{{{W}}}r")
    etree.SubElement(breaker, f"{{{W}}}br")
    third = etree.SubElement(paragraph, f"{{{W}}}r")
    third_properties = etree.SubElement(third, f"{{{W}}}rPr")
    third.insert(0, third_properties)
    etree.SubElement(third_properties, f"{{{W}}}b")
    third_text = etree.SubElement(third, f"{{{W}}}t")
    third_text.text = "Смирнова Анна Олеговна"
    parts["word/document.xml"] = etree.tostring(
        document_xml, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)


def _export_multigroup_pair(tmp_path):
    service = AnonymizerService(tmp_path / "app")
    source = tmp_path / "source.docx"
    _build_multigroup_source(source)
    document_id = service.import_file(source)
    service.anonymize(document_id)
    pair = service.export_pair(document_id, tmp_path / "edited.docx")
    service.storage.delete_document(document_id)
    return service, pair["anonymized_path"]


def _edit_multigroup(edited, first_text, second_text=None):
    with ZipFile(edited) as archive:
        parts = {info.filename: archive.read(info.filename) for info in archive.infolist()}
    document_xml = etree.fromstring(parts["word/document.xml"])
    paragraph = next(iter(document_xml.iter(f"{{{W}}}p")))
    texts = [node for node in paragraph.iter(f"{{{W}}}t")]
    texts[0].text = first_text
    if second_text is not None:
        texts[-1].text = second_text
    run = paragraph.find(f"{{{W}}}r")
    if run.find(f"{{{W}}}rPr") is None:
        properties = etree.SubElement(run, f"{{{W}}}rPr")
        run.insert(0, properties)
        etree.SubElement(properties, f"{{{W}}}b")
    parts["word/document.xml"] = etree.tostring(
        document_xml, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    with ZipFile(edited, "w", ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)


def _restored_text(path):
    with ZipFile(path) as archive:
        root = etree.fromstring(archive.read("word/document.xml"))
    return "".join(node.text or "" for node in root.iter(f"{{{W}}}t"))


def _spy_layout_results(monkeypatch):
    from local_anonymizer import documents

    results = []
    real_layout = documents._restore_original_layout

    def spy(*args, **kwargs):
        result = real_layout(*args, **kwargs)
        results.append(result)
        return result

    monkeypatch.setattr(documents, "_restore_original_layout", spy)
    return results


def test_multigroup_paragraph_graft_restores_every_group(tmp_path, monkeypatch):
    service, edited = _export_multigroup_pair(tmp_path)
    _edit_multigroup(edited, "Правка один", "Правка два")
    layout_results = _spy_layout_results(monkeypatch)

    restored = tmp_path / "restored.docx"
    report = service.restore_from_pair(edited, restored)

    assert layout_results and all(result is not None for result in layout_results)

    assert report["unknown_markers"] == []
    text = _restored_text(restored)
    assert "Правка один" in text
    assert "Правка два" in text
    assert "[ФИО-" not in text


def test_multigroup_paragraph_graft_with_partial_group_change(tmp_path, monkeypatch):
    service, edited = _export_multigroup_pair(tmp_path)
    _edit_multigroup(edited, "Изменено пользователем")
    layout_results = _spy_layout_results(monkeypatch)

    restored = tmp_path / "restored.docx"
    report = service.restore_from_pair(edited, restored)

    assert layout_results and all(result is not None for result in layout_results)

    assert report["unknown_markers"] == []
    text = _restored_text(restored)
    assert "Изменено пользователем" in text
    assert "Смирнова Анна Олеговна" in text
    assert "[ФИО-" not in text


def test_word_saved_pair_with_graphics_restores_user_edits_and_layout(
    tmp_path, monkeypatch
):
    """A real Word-saved pair: two pictures, table, numbering and hard breaks."""
    fixture_dir = Path(__file__).parent / "fixtures" / "word-restore"
    expected_hashes = {
        "source.docx": "cf02f17fc483fc2942130aab21717f797d6d8cb2a696fe8b4037eff1cc4d1e33",
        "edited.docx": "728566195da21769ab859cfb7ec9cbbca1114a323aedf262bb8ca30d82d1ab19",
        "recovery.larecovery": "5c83ee24ec8eed9a42cbb0db69a7f9be0b7ffae529e1f48db0b2e4933cad13a7",
    }
    for name, expected in expected_hashes.items():
        assert hashlib.sha256((fixture_dir / name).read_bytes()).hexdigest() == expected

    edited = tmp_path / "edited.docx"
    recovery = tmp_path / "recovery.larecovery"
    shutil.copyfile(fixture_dir / "edited.docx", edited)
    shutil.copyfile(fixture_dir / "recovery.larecovery", recovery)

    from local_anonymizer import documents

    layout_results = []
    real_layout = documents._restore_original_layout

    def layout_spy(*args, **kwargs):
        result = real_layout(*args, **kwargs)
        layout_results.append(result)
        return result

    monkeypatch.setattr(documents, "_restore_original_layout", layout_spy)
    restored = tmp_path / "restored.docx"
    report = AnonymizerService(tmp_path / "app").restore_from_pair(
        edited, restored, recovery_path=recovery
    )

    assert report["unknown_markers"] == []
    assert layout_results and all(result is not None for result in layout_results)

    with ZipFile(fixture_dir / "source.docx") as archive:
        source_media = {
            name: archive.read(name) for name in archive.namelist()
            if name.startswith("word/media/")
        }
        source_parts = {name: archive.read(name) for name in (
            "word/document.xml", "word/settings.xml", "word/styles.xml", "word/numbering.xml"
        )}
    with ZipFile(restored) as archive:
        restored_media = {
            name: archive.read(name) for name in archive.namelist()
            if name.startswith("word/media/")
        }
        restored_parts = {name: archive.read(name) for name in source_parts}
    assert len(source_media) == 2
    assert restored_media == source_media
    for name in ("word/settings.xml", "word/styles.xml", "word/numbering.xml"):
        assert restored_parts[name] == source_parts[name]

    source_root = etree.fromstring(source_parts["word/document.xml"])
    restored_root = etree.fromstring(restored_parts["word/document.xml"])
    assert len(list(restored_root.iter(f"{{{W}}}drawing"))) == len(
        list(source_root.iter(f"{{{W}}}drawing"))
    ) == 2
    assert len(list(restored_root.iter(f"{{{W}}}br"))) == len(
        list(source_root.iter(f"{{{W}}}br"))
    )
    assert len(list(restored_root.iter(f"{{{W}}}vMerge"))) == len(
        list(source_root.iter(f"{{{W}}}vMerge"))
    ) > 0

    def paragraph_with_text(root, needle):
        return next(
            paragraph for paragraph in root.iter(f"{{{W}}}p")
            if needle in "".join(node.text or "" for node in paragraph.iter(f"{{{W}}}t"))
        )

    assert etree.tostring(
        paragraph_with_text(restored_root, "Синтетический документ"), method="c14n"
    ) == etree.tostring(
        paragraph_with_text(source_root, "Синтетический документ"), method="c14n"
    )
    text = "".join(node.text or "" for node in restored_root.iter(f"{{{W}}}t"))
    assert "Иванов Сергей Петрович — первая правка" in text
    assert "Смирнова Анна Олеговна — вторая правка" in text
    assert "Подпись ко второму рисунку — правка рядом с рисунком" in text
    assert "[ФИО-" not in text
    assert "[СХЕМА-" not in text

    restored_document = Document(restored)
    names = next(p for p in restored_document.paragraphs if "Иванов Сергей Петрович" in p.text)
    assert any(run.bold and "Иванов Сергей Петрович" in run.text for run in names.runs)
    assert any(run.italic and "Смирнова Анна Олеговна" in run.text for run in names.runs)


def test_paragraph_format_signature_ignores_namespaces_but_preserves_run_order():
    first = etree.fromstring(
        f'<w:p xmlns:w="{W}"><w:r><w:rPr><w:b/></w:rPr><w:t>a</w:t></w:r>'
        f'<w:r><w:rPr><w:i/></w:rPr><w:t>b</w:t></w:r></w:p>'.encode()
    )
    swapped = etree.fromstring(
        f'<w:p xmlns:w="{W}"><w:r><w:rPr><w:i/></w:rPr><w:t>a</w:t></w:r>'
        f'<w:r><w:rPr><w:b/></w:rPr><w:t>b</w:t></w:r></w:p>'.encode()
    )
    namespace_noise = etree.fromstring(
        f'<w:p xmlns:w="{W}" xmlns:unused="urn:unused">'
        f'<w:r><w:rPr><w:b/></w:rPr><w:t>a</w:t></w:r>'
        f'<w:r><w:rPr><w:i/></w:rPr><w:t>b</w:t></w:r></w:p>'.encode()
    )
    language_noise = etree.fromstring(
        f'<w:p xmlns:w="{W}"><w:pPr><w:rPr><w:lang w:val="ru-RU"/></w:rPr></w:pPr>'
        f'<w:r><w:rPr><w:b/><w:lang w:val="en-US"/></w:rPr><w:t>a</w:t></w:r>'
        f'<w:r><w:rPr><w:i/></w:rPr><w:t>b</w:t></w:r></w:p>'.encode()
    )

    assert _paragraph_format_signature(first) != _paragraph_format_signature(swapped)
    assert _paragraph_format_signature(first) == _paragraph_format_signature(namespace_noise)
    assert _paragraph_format_signature(first) == _paragraph_format_signature(language_noise)

    styled_original = etree.fromstring(
        f'<w:p xmlns:w="{W}"><w:pPr><w:pStyle w:val="TOC1"/></w:pPr>'
        f'<w:r><w:rPr><w:rStyle w:val="Hyperlink"/></w:rPr><w:t>a</w:t></w:r></w:p>'.encode()
    )
    styled_anonymized = etree.fromstring(
        f'<w:p xmlns:w="{W}"><w:pPr><w:pStyle w:val="LocalStyle023"/></w:pPr>'
        f'<w:r><w:rPr><w:rStyle w:val="LocalStyle015"/></w:rPr><w:t>a</w:t></w:r></w:p>'.encode()
    )
    assert _paragraph_format_signature(styled_original) != _paragraph_format_signature(styled_anonymized)
    assert _paragraph_format_signature(styled_original, ignore_style_ids=True) == (
        _paragraph_format_signature(styled_anonymized, ignore_style_ids=True)
    )
    assert _paragraph_format_signature(
        first, ignore_style_ids=True, merge_equivalent_runs=True
    ) != _paragraph_format_signature(
        swapped, ignore_style_ids=True, merge_equivalent_runs=True
    )

    merged_original = etree.fromstring(
        f'<w:p xmlns:w="{W}">'
        f'<w:r><w:rPr><w:rStyle w:val="Hyperlink"/><w:i/></w:rPr><w:t>a</w:t></w:r>'
        f'<w:r><w:rPr><w:i/></w:rPr><w:t>b</w:t></w:r>'
        f'<w:r><w:rPr><w:rStyle w:val="Hyperlink"/><w:i/></w:rPr><w:t>c</w:t></w:r>'
        f'<w:r><w:rPr><w:i/></w:rPr><w:t>d</w:t></w:r></w:p>'.encode()
    )
    merged_edited = etree.fromstring(
        f'<w:p xmlns:w="{W}">'
        f'<w:r><w:rPr><w:rStyle w:val="LocalStyle015"/><w:i/></w:rPr><w:t>a</w:t></w:r>'
        f'<w:r><w:rPr><w:i/></w:rPr><w:t>b</w:t></w:r></w:p>'.encode()
    )
    assert _paragraph_format_signature(
        merged_original, ignore_style_ids=True, merge_equivalent_runs=True
    ) == _paragraph_format_signature(
        merged_edited, ignore_style_ids=True, merge_equivalent_runs=True
    )


def test_graft_run_toggle_allows_only_finite_values_on_leaf_bold_italic():
    parent = etree.QName(f"{{{W}}}rPr")
    valid = etree.fromstring(f'<w:b xmlns:w="{W}" w:val="0"/>')
    wrong_value = etree.fromstring(f'<w:b xmlns:w="{W}" w:val="CANARY"/>')
    wrong_parent = etree.QName(f"{{{W}}}pPr")
    with_child = etree.fromstring(f'<w:i xmlns:w="{W}"><w:b/></w:i>')

    assert _is_benign_run_toggle_markup(valid, parent)
    assert not _is_benign_run_toggle_markup(wrong_value, parent)
    assert not _is_benign_run_toggle_markup(valid, wrong_parent)
    assert not _is_benign_run_toggle_markup(with_child, parent)


def test_formatting_only_run_swap_is_restored_with_user_formatting(tmp_path, monkeypatch):
    source = tmp_path / "source.docx"
    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("Alpha").bold = True
    paragraph.add_run(" beta").italic = True
    numbering = document.part.numbering_part.element
    num_id = next(element.get(f"{{{W}}}numId") for element in numbering.iter(f"{{{W}}}num"))
    num_properties = OxmlElement("w:numPr")
    level = OxmlElement("w:ilvl")
    level.set(f"{{{W}}}val", "0")
    num = OxmlElement("w:numId")
    num.set(f"{{{W}}}val", num_id)
    num_properties.extend((level, num))
    paragraph._p.get_or_add_pPr().insert(0, num_properties)
    document.save(source)
    service = AnonymizerService(tmp_path / "app")
    document_id = service.import_file(source)
    service.anonymize(document_id)
    pair = service.export_pair(document_id, tmp_path / "edited.docx")
    service.storage.delete_document(document_id)
    edited = pair["anonymized_path"]

    changed = Document(edited)
    paragraph = changed.paragraphs[0]
    paragraph.runs[0].bold = False
    paragraph.runs[0].italic = True
    paragraph.runs[1].italic = False
    paragraph.runs[1].bold = True
    changed.save(edited)
    layout_results = _spy_layout_results(monkeypatch)

    restored = tmp_path / "restored.docx"
    report = service.restore_from_pair(edited, restored)

    assert report["unknown_markers"] == []
    assert layout_results and all(result is not None for result in layout_results)
    restored_paragraph = Document(restored).paragraphs[0]
    assert restored_paragraph.text == "Alpha beta"
    assert restored_paragraph.runs[0].bold is False
    assert restored_paragraph.runs[0].italic is True
    assert restored_paragraph.runs[1].italic is False
    assert restored_paragraph.runs[1].bold is True


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
