import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest
from lxml import etree

from local_anonymizer.app import AppApi
from local_anonymizer.odt import OdtProcessor, extract_odt_text, read_odt_artifact_stamp
from local_anonymizer.service import AnonymizerService
from local_anonymizer.storage import MappingError


OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
META = "urn:oasis:names:tc:opendocument:xmlns:meta:1.0"
MANIFEST = "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
STYLE = "urn:oasis:names:tc:opendocument:xmlns:style:1.0"
XLINK = "http://www.w3.org/1999/xlink"


def _write_odt(
    path: Path,
    *,
    duplicate_content: bool = False,
    extra_parts=None,
    styles_header: str = "",
    include_meta: bool = True,
) -> None:
    content = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="{OFFICE}" xmlns:text="{TEXT}" office:version="1.3">
  <office:automatic-styles><text:list-style text:name="KeepStyle"/></office:automatic-styles>
  <office:body><office:text>
    <text:h text:outline-level="1" text:style-name="Heading">Отчёт</text:h>
    <text:p text:style-name="Body"><text:span text:style-name="Bold">Иванов </text:span><text:span text:style-name="Italic">Сергей Петрович</text:span></text:p>
  </office:text></office:body>
</office:document-content>'''.encode()
    styles = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="{OFFICE}" xmlns:text="{TEXT}" xmlns:style="{STYLE}" office:version="1.3">
  <office:styles><text:outline-style text:name="KeepOutline"/></office:styles>
  <office:master-styles><style:master-page style:name="Default"><style:header><text:p text:style-name="Header">{styles_header}</text:p></style:header></style:master-page></office:master-styles>
</office:document-styles>'''.encode()
    meta = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-meta xmlns:office="{OFFICE}" xmlns:meta="{META}" office:version="1.3">
  <office:meta><meta:generator>LibreOffice</meta:generator></office:meta>
</office:document-meta>'''.encode()
    manifest = f'''<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="{MANIFEST}" manifest:version="1.3">
  <manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>
  <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
  <manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>
  {f'<manifest:file-entry manifest:full-path="meta.xml" manifest:media-type="text/xml"/>' if include_meta else ''}
</manifest:manifest>'''.encode()
    with ZipFile(path, "w") as package:
        package.writestr("mimetype", "application/vnd.oasis.opendocument.text", compress_type=ZIP_STORED)
        package.writestr("content.xml", content, compress_type=ZIP_DEFLATED)
        if duplicate_content:
            package.writestr("content.xml", content, compress_type=ZIP_DEFLATED)
        package.writestr("styles.xml", styles, compress_type=ZIP_DEFLATED)
        if include_meta:
            package.writestr("meta.xml", meta, compress_type=ZIP_DEFLATED)
        package.writestr("META-INF/manifest.xml", manifest, compress_type=ZIP_DEFLATED)
        for name, payload in (extra_parts or {}).items():
            package.writestr(name, payload, compress_type=ZIP_DEFLATED)


def _content_root(path: Path):
    with ZipFile(path) as package:
        return etree.fromstring(package.read("content.xml"))


def _rewrite_package_part(path: Path, name: str, payload: bytes) -> None:
    temporary = path.with_suffix(".tmp.odt")
    with ZipFile(path) as source, ZipFile(temporary, "w") as target:
        for info in source.infolist():
            target.writestr(info, payload if info.filename == name else source.read(info.filename))
    temporary.replace(path)


def _visible_text(path: Path) -> str:
    root = _content_root(path)
    return "\n".join(
        "".join(block.itertext())
        for block in root.xpath(".//text:p | .//text:h", namespaces={"text": TEXT})
    )


def _set_structural_whitespace_name(path: Path) -> None:
    with ZipFile(path) as package:
        content = etree.fromstring(package.read("content.xml"))
    paragraph = content.xpath(".//text:p", namespaces={"text": TEXT})[0]
    for child in list(paragraph):
        paragraph.remove(child)
    paragraph.text = "Иванов"
    spaces = etree.SubElement(paragraph, f"{{{TEXT}}}s")
    spaces.set(f"{{{TEXT}}}c", "2")
    spaces.tail = "Сергей"
    tab = etree.SubElement(paragraph, f"{{{TEXT}}}tab")
    tab.tail = "Петрович"
    line_break = etree.SubElement(paragraph, f"{{{TEXT}}}line-break")
    line_break.tail = "Отдел"
    _rewrite_package_part(
        path,
        "content.xml",
        etree.tostring(content, xml_declaration=True, encoding="UTF-8"),
    )


def test_odt_anonymize_restore_preserves_package_formatting_and_exact_source(tmp_path):
    source = tmp_path / "formatted.odt"
    anonymized = tmp_path / "formatted-anonymized.odt"
    restored = tmp_path / "formatted-restored.odt"
    _write_odt(source)
    source_bytes = source.read_bytes()
    with ZipFile(source) as package:
        source_styles = package.read("styles.xml")

    result = OdtProcessor().anonymize(source, anonymized)

    assert "[ФИО-1]" in _visible_text(anonymized)
    assert "Иванов Сергей Петрович" not in _visible_text(anonymized)
    root = _content_root(anonymized)
    assert root.xpath("string(.//text:p/@text:style-name)", namespaces={"text": TEXT}) == "Body"
    assert root.xpath(".//text:span[@text:style-name='Bold']", namespaces={"text": TEXT})
    assert root.xpath(".//text:span[@text:style-name='Italic']", namespaces={"text": TEXT})
    with ZipFile(anonymized) as package:
        assert package.read("styles.xml") == source_styles
        assert package.infolist()[0].filename == "mimetype"
        assert package.infolist()[0].compress_type == ZIP_STORED
    assert source.read_bytes() == source_bytes

    unknown = OdtProcessor().restore(
        anonymized, restored, result.mapping, package_archive=result.package_archive
    )

    assert unknown == []
    assert restored.read_bytes() == source_bytes


def test_odt_rejects_duplicate_members_and_active_or_embedded_content(tmp_path):
    duplicate = tmp_path / "duplicate.odt"
    _write_odt(duplicate, duplicate_content=True)
    with pytest.raises(ValueError, match="повторяющиеся ZIP-части"):
        OdtProcessor().anonymize(duplicate, tmp_path / "duplicate-out.odt")

    for name in ("Basic/Standard/Module1.xml", "bAsIc/Standard/Module1.xml", "Scripts/python/example.py", "Object 1/content.xml"):
        source = tmp_path / (name.replace("/", "-") + ".odt")
        _write_odt(source, extra_parts={name: b"sensitive"})
        with pytest.raises(ValueError, match="активное или встроенное содержимое"):
            OdtProcessor().anonymize(source, tmp_path / "blocked.odt")


def test_odt_anonymizes_styles_headers_and_requires_existing_metadata(tmp_path):
    source = tmp_path / "header.odt"
    anonymized = tmp_path / "header-anonymized.odt"
    _write_odt(source, styles_header="Петров Пётр Сергеевич")

    result = OdtProcessor().anonymize(source, anonymized)

    with ZipFile(anonymized) as package:
        styles = package.read("styles.xml").decode("utf-8")
    assert "Петров Пётр Сергеевич" not in styles
    assert "[ФИО-" in styles
    assert "Петров Пётр Сергеевич" in result.mapping.values()

    missing_meta = tmp_path / "missing-meta.odt"
    _write_odt(missing_meta, include_meta=False)
    with pytest.raises(ValueError, match="meta.xml"):
        OdtProcessor().anonymize(missing_meta, tmp_path / "missing-meta-out.odt")


def test_odt_sanitizes_external_text_links_and_exact_restore_recovers_them(tmp_path):
    source = tmp_path / "external.odt"
    anonymized = tmp_path / "external-anonymized.odt"
    restored = tmp_path / "external-restored.odt"
    _write_odt(source)
    with ZipFile(source) as package:
        content = etree.fromstring(package.read("content.xml"))
    paragraph = content.xpath(".//text:p", namespaces={"text": TEXT})[0]
    link = etree.SubElement(paragraph, f"{{{TEXT}}}a")
    link.set(f"{{{XLINK}}}href", "HTTPS://example.invalid/sensitive")
    link.text = "ссылка"
    _rewrite_package_part(source, "content.xml", etree.tostring(content, xml_declaration=True, encoding="UTF-8"))
    source_bytes = source.read_bytes()

    assert "ссылка" in extract_odt_text(source)
    result = OdtProcessor().anonymize(source, anonymized)
    with ZipFile(anonymized) as package:
        anonymized_content = etree.fromstring(package.read("content.xml"))
    sanitized_link = anonymized_content.xpath(".//text:a", namespaces={"text": TEXT})[0]
    assert sanitized_link.get(f"{{{XLINK}}}href") == "#"

    assert OdtProcessor().restore(
        anonymized, restored, result.mapping, package_archive=result.package_archive
    ) == []
    assert restored.read_bytes() == source_bytes


def test_odt_still_rejects_external_non_text_relationships(tmp_path):
    source = tmp_path / "external-image.odt"
    _write_odt(source)
    with ZipFile(source) as package:
        content = etree.fromstring(package.read("content.xml"))
    paragraph = content.xpath(".//text:p", namespaces={"text": TEXT})[0]
    image = etree.SubElement(paragraph, "{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}image")
    image.set(f"{{{XLINK}}}href", "HTTPS://example.invalid/sensitive")
    _rewrite_package_part(
        source,
        "content.xml",
        etree.tostring(content, xml_declaration=True, encoding="UTF-8"),
    )

    with pytest.raises(ValueError, match="внешние ссылки"):
        extract_odt_text(source)


def test_odt_strips_annotations_but_exact_restore_recovers_them(tmp_path):
    source = tmp_path / "comments.odt"
    anonymized = tmp_path / "comments-anonymized.odt"
    restored = tmp_path / "comments-restored.odt"
    _write_odt(source)
    with ZipFile(source) as package:
        content = etree.fromstring(package.read("content.xml"))
    paragraph = content.xpath(".//text:p", namespaces={"text": TEXT})[0]
    paragraph.clear()
    paragraph.text = "Before"
    annotation = etree.SubElement(paragraph, f"{{{OFFICE}}}annotation")
    creator = etree.SubElement(annotation, "{http://purl.org/dc/elements/1.1/}creator")
    creator.text = "Alice"
    note = etree.SubElement(annotation, f"{{{TEXT}}}p")
    note.text = "secret note"
    annotation.tail = "After"
    etree.SubElement(paragraph, f"{{{OFFICE}}}annotation-end")
    _rewrite_package_part(
        source,
        "content.xml",
        etree.tostring(content, xml_declaration=True, encoding="UTF-8"),
    )
    source_bytes = source.read_bytes()

    extracted = extract_odt_text(source)
    assert extracted.endswith("BeforeAfter")
    assert "secret note" not in extracted
    assert "Alice" not in extracted
    result = OdtProcessor().anonymize(source, anonymized)
    with ZipFile(anonymized) as package:
        output_content = package.read("content.xml")
    assert b"annotation" not in output_content
    assert b"secret note" not in output_content
    assert b"Alice" not in output_content

    assert OdtProcessor().restore(
        anonymized, restored, result.mapping, package_archive=result.package_archive
    ) == []
    assert restored.read_bytes() == source_bytes


def test_odt_structural_whitespace_is_visible_and_safe_to_replace(tmp_path):
    source = tmp_path / "structural-whitespace.odt"
    anonymized = tmp_path / "structural-whitespace-anonymized.odt"
    restored = tmp_path / "structural-whitespace-restored.odt"
    _write_odt(source)
    _set_structural_whitespace_name(source)
    source_bytes = source.read_bytes()

    assert "Иванов  Сергей\tПетрович\nОтдел" in extract_odt_text(source)

    result = OdtProcessor().anonymize(source, anonymized)

    assert "Иванов" not in extract_odt_text(anonymized)
    assert "[ФИО-" in extract_odt_text(anonymized)
    assert "Иванов  Сергей\tПетрович" in result.mapping.values()

    assert OdtProcessor().restore(
        anonymized,
        restored,
        result.mapping,
        package_archive=result.package_archive,
    ) == []
    assert restored.read_bytes() == source_bytes


@pytest.mark.parametrize(
    "count",
    ["0", "-1", "not-a-number", "1_0", "+1", " 1", "4097"],
)
def test_odt_rejects_invalid_or_excessive_structural_space_counts(tmp_path, count):
    source = tmp_path / f"bad-space-{count}.odt"
    _write_odt(source)
    with ZipFile(source) as package:
        content = etree.fromstring(package.read("content.xml"))
    paragraph = content.xpath(".//text:p", namespaces={"text": TEXT})[0]
    space = etree.SubElement(paragraph, f"{{{TEXT}}}s")
    space.set(f"{{{TEXT}}}c", count)
    _rewrite_package_part(
        source,
        "content.xml",
        etree.tostring(content, xml_declaration=True, encoding="UTF-8"),
    )

    with pytest.raises(ValueError, match="пробел"):
        OdtProcessor().anonymize(source, tmp_path / "bad-space-out.odt")


@pytest.mark.parametrize(("count", "expected"), [(None, " "), ("4096", " " * 4096)])
def test_odt_accepts_structural_space_count_boundaries(tmp_path, count, expected):
    source = tmp_path / "space-boundary.odt"
    _write_odt(source)
    with ZipFile(source) as package:
        content = etree.fromstring(package.read("content.xml"))
    paragraph = content.xpath(".//text:p", namespaces={"text": TEXT})[0]
    paragraph.clear()
    paragraph.text = "A"
    space = etree.SubElement(paragraph, f"{{{TEXT}}}s")
    if count is not None:
        space.set(f"{{{TEXT}}}c", count)
    space.tail = "B"
    _rewrite_package_part(
        source,
        "content.xml",
        etree.tostring(content, xml_declaration=True, encoding="UTF-8"),
    )

    assert f"A{expected}B" in extract_odt_text(source)


def test_odt_rejects_cumulative_structural_space_overflow(tmp_path):
    source = tmp_path / "cumulative-space-overflow.odt"
    _write_odt(source)
    with ZipFile(source) as package:
        content = etree.fromstring(package.read("content.xml"))
    paragraph = content.xpath(".//text:p", namespaces={"text": TEXT})[0]
    for count in ("2048", "2049"):
        space = etree.SubElement(paragraph, f"{{{TEXT}}}s")
        space.set(f"{{{TEXT}}}c", count)
    _rewrite_package_part(
        source,
        "content.xml",
        etree.tostring(content, xml_declaration=True, encoding="UTF-8"),
    )

    with pytest.raises(ValueError, match="пробел"):
        OdtProcessor().anonymize(source, tmp_path / "cumulative-space-overflow-out.odt")


@pytest.mark.parametrize("tag", ["s", "tab", "line-break"])
def test_odt_rejects_nonempty_structural_whitespace_nodes(tmp_path, tag):
    source = tmp_path / f"nonempty-{tag}.odt"
    _write_odt(source)
    with ZipFile(source) as package:
        content = etree.fromstring(package.read("content.xml"))
    paragraph = content.xpath(".//text:p", namespaces={"text": TEXT})[0]
    structural = etree.SubElement(paragraph, f"{{{TEXT}}}{tag}")
    structural.text = "HIDDEN_SENSITIVE_TEXT"
    _rewrite_package_part(
        source,
        "content.xml",
        etree.tostring(content, xml_declaration=True, encoding="UTF-8"),
    )

    with pytest.raises(ValueError, match="структурный пробел"):
        OdtProcessor().anonymize(source, tmp_path / "nonempty-out.odt")


@pytest.mark.parametrize("tag", ["s", "tab", "line-break"])
def test_odt_rejects_unknown_structural_whitespace_attributes(tmp_path, tag):
    source = tmp_path / f"attribute-{tag}.odt"
    _write_odt(source)
    with ZipFile(source) as package:
        content = etree.fromstring(package.read("content.xml"))
    paragraph = content.xpath(".//text:p", namespaces={"text": TEXT})[0]
    structural = etree.SubElement(paragraph, f"{{{TEXT}}}{tag}")
    structural.set("secret", "HIDDEN_SENSITIVE_TEXT")
    _rewrite_package_part(
        source,
        "content.xml",
        etree.tostring(content, xml_declaration=True, encoding="UTF-8"),
    )

    with pytest.raises(ValueError, match="атрибут"):
        OdtProcessor().anonymize(source, tmp_path / "attribute-out.odt")


@pytest.mark.parametrize("tab_ref", ["0", "-1", "1_0", "+1", " 1", "4097", "secret"])
def test_odt_rejects_invalid_tab_reference(tmp_path, tab_ref):
    source = tmp_path / "tab-ref.odt"
    _write_odt(source)
    with ZipFile(source) as package:
        content = etree.fromstring(package.read("content.xml"))
    paragraph = content.xpath(".//text:p", namespaces={"text": TEXT})[0]
    tab = etree.SubElement(paragraph, f"{{{TEXT}}}tab")
    tab.set(f"{{{TEXT}}}tab-ref", tab_ref)
    _rewrite_package_part(
        source,
        "content.xml",
        etree.tostring(content, xml_declaration=True, encoding="UTF-8"),
    )

    with pytest.raises(ValueError, match="табуляц"):
        OdtProcessor().anonymize(source, tmp_path / "tab-ref-out.odt")


def test_odt_accepts_standard_tab_reference(tmp_path):
    source = tmp_path / "tab-ref-valid.odt"
    anonymized = tmp_path / "tab-ref-valid-out.odt"
    _write_odt(source)
    _set_structural_whitespace_name(source)
    with ZipFile(source) as package:
        content = etree.fromstring(package.read("content.xml"))
    tab = content.xpath(".//text:tab", namespaces={"text": TEXT})[0]
    tab.set(f"{{{TEXT}}}tab-ref", "2")
    _rewrite_package_part(
        source,
        "content.xml",
        etree.tostring(content, xml_declaration=True, encoding="UTF-8"),
    )

    result = OdtProcessor().anonymize(source, anonymized)

    assert "Иванов  Сергей\tПетрович" in result.mapping.values()


def test_service_odt_roundtrip_stamps_artifact_without_changing_windows_doc_path(tmp_path):
    source = tmp_path / "service.odt"
    _write_odt(source)
    service = AnonymizerService(tmp_path / "app")

    document_id = service.import_file(source)
    preview = service.preview_document(document_id)
    report = service.anonymize(document_id)
    anonymized = Path(report["output_path"])

    assert preview["format"] == "odt"
    assert "Иванов Сергей Петрович" in preview["text"]
    assert anonymized.suffix == ".odt"
    assert "[ФИО-1]" in _visible_text(anonymized)
    with pytest.raises(ValueError, match="уже обезличен"):
        service.import_file(anonymized)

    restored = service.restore(document_id, anonymized)
    assert "Иванов Сергей Петрович" in _visible_text(Path(restored["output_path"]))
    assert hashlib.sha256(source.read_bytes()).hexdigest() == hashlib.sha256(
        Path(restored["output_path"]).read_bytes()
    ).hexdigest()


def test_edited_odt_restore_keeps_user_edits_and_clears_artifact_stamp(tmp_path):
    source = tmp_path / "edited-source.odt"
    _write_odt(source)
    service = AnonymizerService(tmp_path / "app")
    document_id = service.import_file(source)
    report = service.anonymize(document_id)
    edited = tmp_path / "edited-anonymized.odt"
    edited.write_bytes(Path(report["output_path"]).read_bytes())

    root = _content_root(edited)
    office_text = root.find(f".//{{{OFFICE}}}text")
    paragraph = etree.SubElement(office_text, f"{{{TEXT}}}p")
    paragraph.set(f"{{{TEXT}}}style-name", "UserEdit")
    paragraph.text = "Добавлено пользователем [ФИО-999]"
    _rewrite_package_part(
        edited,
        "content.xml",
        etree.tostring(root, xml_declaration=True, encoding="UTF-8"),
    )

    restored = tmp_path / "edited-restored.odt"
    restored_report = service.restore(document_id, edited, restored)

    restored_text = _visible_text(restored)
    assert "Иванов Сергей Петрович" in restored_text
    assert "Добавлено пользователем [ФИО-999]" in restored_text
    assert restored_report["unknown_markers"] == ["[ФИО-999]"]
    assert read_odt_artifact_stamp(restored) is None
    restored_root = _content_root(restored)
    assert restored_root.xpath(
        ".//text:p[@text:style-name='UserEdit']", namespaces={"text": TEXT}
    )


def test_app_file_dialogs_offer_odt_for_import_and_restore(tmp_path):
    source = tmp_path / "dialog.odt"
    _write_odt(source)

    class Window:
        def __init__(self):
            self.calls = []

        def create_file_dialog(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return [str(source)]

    window = Window()
    api = AppApi(tmp_path / "app")
    api.set_window(window)

    assert api.choose_files()["ok"] is True
    assert "*.odt" in window.calls[0][1]["file_types"][0]

    window.calls.clear()
    with pytest.raises(MappingError):
        api.choose_restore_pair()
    assert "*.odt" in window.calls[0][1]["file_types"][0]
