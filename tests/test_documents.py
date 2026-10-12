import base64
import copy
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

import pytest
from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.shared import Inches, Pt, RGBColor
from lxml import etree

from local_anonymizer.documents import (
    DocxProcessor,
    RestorationError,
    _trusted_docx_strings,
    _trusted_wml_schema,
)


def _all_xml(path: Path) -> bytes:
    with ZipFile(path) as z:
        return b"".join(z.read(n) for n in z.namelist() if n.endswith((".xml", ".rels")))


def _rewrite_docx_parts(path: Path, transforms: dict[str, callable]) -> None:
    replacement = path.with_suffix(".rewrite.docx")
    with ZipFile(path) as incoming, ZipFile(replacement, "w", ZIP_DEFLATED) as outgoing:
        for info in incoming.infolist():
            payload = incoming.read(info.filename)
            if info.filename in transforms:
                payload = transforms[info.filename](payload)
            outgoing.writestr(info, payload)
    replacement.replace(path)


def test_docx_anonymize_and_restore_do_not_reserialize_with_python_docx(tmp_path, monkeypatch):
    source = tmp_path / "source.docx"
    anonymized = tmp_path / "anonymized.docx"
    restored = tmp_path / "restored.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.save(source)
    _trusted_wml_schema()
    _trusted_docx_strings()

    def forbidden_save(*args, **kwargs):
        raise AssertionError("python-docx must not reserialize the OOXML package")

    monkeypatch.setattr("docx.document.Document.save", forbidden_save)
    result = DocxProcessor().anonymize(source, anonymized)
    assert "[ФИО-1]" in Document(anonymized).paragraphs[0].text
    DocxProcessor().restore(anonymized, restored, result.mapping)
    assert Document(restored).paragraphs[0].text == "Иванов Сергей Петрович"


def test_docx_vm_inventory_names_are_removed_from_package_and_restore_exactly(tmp_path):
    source = tmp_path / "vm-source.docx"
    anonymized = tmp_path / "vm-anonymized.docx"
    restored = tmp_path / "vm-restored.docx"
    vm_names = ["qzx-monitor0101", "qzx-repo0101", "qzx-print0101", "qzx-fs0101", "qzx-journal0101"]
    document = Document()
    table = document.add_table(rows=0, cols=1)
    for name in vm_names:
        table.add_row().cells[0].text = name
    document.save(source)

    result = DocxProcessor().anonymize(source, anonymized)

    package_xml = _all_xml(anonymized)
    assert all(name.encode() not in package_xml for name in vm_names)
    assert set(result.mapping.values()) == set(vm_names)
    DocxProcessor().restore(anonymized, restored, result.mapping)
    restored_values = [row.cells[0].text for row in Document(restored).tables[0].rows]
    assert restored_values == vm_names


def test_docx_contextual_inventory_values_are_removed_and_exactly_restored(tmp_path):
    source = tmp_path / "context-source.docx"
    anonymized = tmp_path / "context-anonymized.docx"
    restored = tmp_path / "context-restored.docx"
    sensitive = [
        "lab-nas", "vm-pc", "ALPHAHQ", "BETA-LAB",
        "Computers_ACME/Production/Site-A", "Servers/Legacy-RDP",
        "Example Secure Client", "Northwind Banking Plug-in",
    ]
    document = Document()

    hosts = document.add_table(rows=1, cols=4)
    for index, value in enumerate(("Имя хоста", "IP-адрес", "vCPU", "RAM")):
        hosts.rows[0].cells[index].text = value
    for values in (("lab-nas", "[IP-74]", "32", "128"), ("vm-pc", "[IP-75]", "16", "32")):
        cells = hosts.add_row().cells
        for index, value in enumerate(values):
            cells[index].text = value

    netbios = document.add_table(rows=2, cols=3)
    for index, value in enumerate(("Параметр", "Площадка 1", "Площадка 2")):
        netbios.rows[0].cells[index].text = value
    for index, value in enumerate(("NetBIOS", "ALPHAHQ", "BETA-LAB")):
        netbios.rows[1].cells[index].text = value

    ous = document.add_table(rows=1, cols=4)
    for index, value in enumerate(("OU или контейнер AD", "Компьютерных УЗ", "Включено", "Отключено")):
        ous.rows[0].cells[index].text = value
    for values in (("Computers_ACME/Production/Site-A", "21", "21", "0"), ("Servers/Legacy-RDP", "12", "11", "1")):
        cells = ous.add_row().cells
        for index, value in enumerate(values):
            cells[index].text = value

    software = document.add_table(rows=2, cols=3)
    software.cell(0, 0).text = "Инвентаризация программного обеспечения"
    software.cell(0, 1).text = "Установок"
    software.cell(0, 2).text = "Доля"
    software.cell(1, 0).text = "Example Secure Client"
    software.cell(1, 1).text = "10"
    software.cell(1, 2).text = "1,6%"
    row = software.add_row().cells
    row[0].text = "Northwind Banking Plug-in"
    row[1].text = "4"
    row[2].text = "0,6%"
    document.save(source)
    source_bytes = source.read_bytes()

    result = DocxProcessor().anonymize(source, anonymized)

    package_xml = _all_xml(anonymized)
    assert all(value.encode("utf-8") not in package_xml for value in sensitive)
    assert set(sensitive).issubset(set(result.mapping.values()))

    DocxProcessor().restore(
        anonymized,
        restored,
        result.mapping,
        package_archive=result.package_archive,
    )
    assert restored.read_bytes() == source_bytes


def test_docx_graphic_is_removed_from_anonymized_package_and_restored_exactly(tmp_path):
    source = tmp_path / "graphic-source.docx"
    image = tmp_path / "synthetic.png"
    anonymized = tmp_path / "graphic-anonymized.docx"
    restored = tmp_path / "graphic-restored.docx"
    image_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    image.write_bytes(image_bytes)
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.add_picture(str(image), width=Inches(1))
    document.save(source)

    result = DocxProcessor().anonymize(source, anonymized)

    with ZipFile(anonymized) as package:
        assert image_bytes not in (package.read(name) for name in package.namelist())
        assert not any(name.startswith("word/media/") for name in package.namelist())
    assert result.package_archive

    DocxProcessor().restore(
        anonymized,
        restored,
        result.mapping,
        package_archive=result.package_archive,
    )

    with ZipFile(restored) as package:
        restored_images = [
            package.read(name)
            for name in package.namelist()
            if name.startswith("word/media/")
        ]
        relationships = etree.fromstring(package.read("word/_rels/document.xml.rels"))
        assert restored_images == [image_bytes]
        assert relationships.xpath(
            "//*[local-name()='Relationship' and contains(@Type, '/image')]"
        )
    restored_document = Document(restored)
    assert restored_document.inline_shapes
    assert restored_document.paragraphs[0].text == "Иванов Сергей Петрович"


def test_docx_unedited_anonymized_package_restores_source_bytes_exactly(tmp_path):
    source = tmp_path / "exact-source.docx"
    image = tmp_path / "synthetic.png"
    anonymized = tmp_path / "exact-anonymized.docx"
    restored = tmp_path / "exact-restored.docx"
    image.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    ))
    document = Document()
    document.add_paragraph("Сервер QZX-SRV-0101")
    document.add_picture(str(image), width=Inches(1))
    document.save(source)

    result = DocxProcessor().anonymize(source, anonymized)
    DocxProcessor().restore(
        anonymized,
        restored,
        result.mapping,
        package_archive=result.package_archive,
    )

    assert restored.read_bytes() == source.read_bytes()


def test_docx_graphic_restores_original_zip_member_metadata(tmp_path):
    source = tmp_path / "graphic-metadata-source.docx"
    image = tmp_path / "synthetic.png"
    anonymized = tmp_path / "graphic-metadata-anonymized.docx"
    restored = tmp_path / "graphic-metadata-restored.docx"
    image.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    ))
    document = Document()
    document.add_paragraph("Сервер QZX-SRV-0101")
    document.add_picture(str(image), width=Inches(1))
    document.save(source)

    with ZipFile(source) as package:
        media_name = next(name for name in package.namelist() if name.startswith("word/media/"))

    replacement = source.with_suffix(".metadata.docx")
    with ZipFile(source) as incoming, ZipFile(replacement, "w") as outgoing:
        for original_info in incoming.infolist():
            payload = incoming.read(original_info.filename)
            if original_info.filename != media_name:
                outgoing.writestr(original_info, payload)
                continue
            info = ZipInfo(media_name, date_time=(2003, 4, 5, 6, 7, 8))
            info.compress_type = ZIP_STORED
            info.comment = b"GRAPHIC-METADATA"
            info.extra = b"\x99\x99\x04\x00TEST"
            info.create_system = 3
            info.create_version = 45
            info.extract_version = 20
            info.internal_attr = 1
            info.external_attr = 0o100640 << 16
            outgoing.writestr(info, payload)
    replacement.replace(source)

    with ZipFile(source) as package:
        expected = package.getinfo(media_name)
    result = DocxProcessor().anonymize(source, anonymized)
    DocxProcessor().restore(
        anonymized, restored, result.mapping, package_archive=result.package_archive
    )

    with ZipFile(restored) as package:
        actual = package.getinfo(media_name)
    assert actual.compress_type == expected.compress_type
    assert actual.date_time == expected.date_time
    assert actual.comment == expected.comment
    assert actual.extra == expected.extra
    assert actual.create_system == expected.create_system
    assert actual.create_version == expected.create_version
    assert actual.extract_version == expected.extract_version
    assert actual.internal_attr == expected.internal_attr
    assert actual.external_attr == expected.external_attr


def test_docx_vml_scheme_without_binary_part_round_trips_through_protected_archive(tmp_path):
    source = tmp_path / "vml-source.docx"
    anonymized = tmp_path / "vml-anonymized.docx"
    restored = tmp_path / "vml-restored.docx"
    document = Document()
    run = document.add_paragraph().add_run()
    pict = etree.fromstring(
        b'<w:pict xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        b'xmlns:v="urn:schemas-microsoft-com:vml"><v:shape id="synthetic-scheme" '
        b'style="width:100pt;height:40pt"><v:textbox><w:txbxContent><w:p><w:r>'
        b'<w:t>\xd0\x98\xd0\xb2\xd0\xb0\xd0\xbd\xd0\xbe\xd0\xb2 \xd0\xa1\xd0\xb5\xd1\x80\xd0\xb3\xd0\xb5\xd0\xb9 \xd0\x9f\xd0\xb5\xd1\x82\xd1\x80\xd0\xbe\xd0\xb2\xd0\xb8\xd1\x87</w:t></w:r></w:p></w:txbxContent></v:textbox>'
        b'</v:shape></w:pict>'
    )
    run._r.append(pict)
    document.save(source)

    result = DocxProcessor().anonymize(source, anonymized)

    with ZipFile(anonymized) as package:
        document_xml = package.read("word/document.xml")
        assert b"synthetic-scheme" not in document_xml
        assert "Иванов Сергей Петрович".encode() not in document_xml
        assert "[СХЕМА-1]".encode() in document_xml

    DocxProcessor().restore(
        anonymized,
        restored,
        result.mapping,
        package_archive=result.package_archive,
    )

    with ZipFile(restored) as package:
        document_xml = package.read("word/document.xml")
        assert b"synthetic-scheme" in document_xml
        assert "Иванов Сергей Петрович".encode() in document_xml
    Document(restored)


def test_docx_graphics_are_preserved_when_redaction_checkbox_is_off(tmp_path):
    source = tmp_path / "source.docx"
    image = tmp_path / "synthetic.png"
    anonymized = tmp_path / "anonymized.docx"
    image_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    image.write_bytes(image_bytes)
    document = Document()
    document.add_paragraph("Обычный текст")
    document.add_picture(str(image), width=Inches(1))
    document.save(source)

    result = DocxProcessor().anonymize(source, anonymized, redact_graphics=False)

    with ZipFile(anonymized) as package:
        media = [package.read(name) for name in package.namelist() if name.startswith("word/media/")]
        assert image_bytes in media
        assert "[СХЕМА-".encode() not in package.read("word/document.xml")
    assert result.package_archive["fragments"] == []


def test_docx_restore_rejects_tampered_graphics_archive_binary(tmp_path):
    source = tmp_path / "source.docx"
    image = tmp_path / "synthetic.png"
    anonymized = tmp_path / "anonymized.docx"
    restored = tmp_path / "restored.docx"
    image.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    ))
    document = Document()
    document.add_paragraph("Обычный текст")
    document.add_picture(str(image), width=Inches(1))
    document.save(source)
    result = DocxProcessor().anonymize(source, anonymized)
    archive = copy.deepcopy(result.package_archive)
    part_name = next(iter(archive["parts"]))
    archive["parts"][part_name] = base64.b64encode(b"MZ-not-an-image").decode("ascii")

    with pytest.raises(RestorationError, match="графическ"):
        DocxProcessor().restore(
            anonymized, restored, result.mapping, package_archive=archive
        )

    assert not restored.exists()


def test_docx_restore_rejects_unapproved_graphics_zip_metadata(tmp_path):
    source = tmp_path / "source.docx"
    image = tmp_path / "synthetic.png"
    anonymized = tmp_path / "anonymized.docx"
    restored = tmp_path / "restored.docx"
    image.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    ))
    document = Document()
    document.add_paragraph("Обычный текст")
    document.add_picture(str(image), width=Inches(1))
    document.save(source)
    result = DocxProcessor().anonymize(source, anonymized)
    archive = copy.deepcopy(result.package_archive)
    part_name = next(iter(archive["part_metadata"]))
    archive["part_metadata"][part_name]["compress_type"] = 99

    with pytest.raises(RestorationError, match="сжатие"):
        DocxProcessor().restore(
            anonymized, restored, result.mapping, package_archive=archive
        )

    assert not restored.exists()

    archive["part_metadata"][part_name]["compress_type"] = ZIP_STORED
    archive["part_metadata"][part_name]["extra"] = base64.b64encode(
        b"\x99\x99\x05\x00x"
    ).decode("ascii")
    with pytest.raises(RestorationError, match="метаданные ZIP"):
        DocxProcessor().restore(
            anonymized, restored, result.mapping, package_archive=archive
        )

    assert not restored.exists()


def test_docx_restore_rejects_unapproved_graphics_content_type(tmp_path):
    source = tmp_path / "source.docx"
    image = tmp_path / "synthetic.png"
    anonymized = tmp_path / "anonymized.docx"
    restored = tmp_path / "restored.docx"
    image.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    ))
    document = Document()
    document.add_paragraph("Обычный текст")
    document.add_picture(str(image), width=Inches(1))
    document.save(source)
    result = DocxProcessor().anonymize(source, anonymized)
    archive = copy.deepcopy(result.package_archive)
    archive["content_types"].append(base64.b64encode(
        b'<Default xmlns="http://schemas.openxmlformats.org/package/2006/content-types" '
        b'Extension="png" ContentType="application/x-msdownload"/>'
    ).decode("ascii"))

    with pytest.raises(RestorationError, match="тип"):
        DocxProcessor().restore(
            anonymized, restored, result.mapping, package_archive=archive
        )

    assert not restored.exists()


def test_docx_restore_rejects_dtd_in_protected_graphics_fragment(tmp_path):
    source = tmp_path / "source.docx"
    image = tmp_path / "synthetic.png"
    anonymized = tmp_path / "anonymized.docx"
    restored = tmp_path / "restored.docx"
    image.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    ))
    document = Document()
    document.add_paragraph("Обычный текст")
    document.add_picture(str(image), width=Inches(1))
    document.save(source)
    result = DocxProcessor().anonymize(source, anonymized)
    archive = copy.deepcopy(result.package_archive)
    archive["fragments"][0]["xml"] = base64.b64encode(
        b'<!DOCTYPE w:pict [<!ENTITY canary "ARCHIVE_DTD_CANARY">]>'
        b'<w:pict xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b'&canary;</w:pict>'
    ).decode("ascii")

    with pytest.raises(RestorationError, match="XML"):
        DocxProcessor().restore(
            anonymized, restored, result.mapping, package_archive=archive
        )

    assert not restored.exists()


@pytest.mark.parametrize(
    "payload",
    [
        b'<w:object xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>',
        b'<o:OLEObject xmlns:o="urn:schemas-microsoft-com:office:office" '
        b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        b'r:id="rId1"/>',
        b'<a:hlinkClick xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        b'r:id="rId1" tooltip="https://example.invalid/payload"/>',
    ],
    ids=["active-object", "embedded-ole", "external-url"],
)
def test_docx_restore_rejects_active_or_external_xml_in_graphics_archive(
    tmp_path, payload
):
    source = tmp_path / "source.docx"
    image = tmp_path / "synthetic.png"
    anonymized = tmp_path / "anonymized.docx"
    restored = tmp_path / "restored.docx"
    image.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    ))
    document = Document()
    document.add_paragraph("Обычный текст")
    document.add_picture(str(image), width=Inches(1))
    document.save(source)
    result = DocxProcessor().anonymize(source, anonymized)
    archive = copy.deepcopy(result.package_archive)
    fragment = etree.fromstring(base64.b64decode(archive["fragments"][0]["xml"]))
    fragment.append(etree.fromstring(payload))
    archive["fragments"][0]["xml"] = base64.b64encode(
        etree.tostring(fragment)
    ).decode("ascii")

    with pytest.raises(RestorationError, match="XML"):
        DocxProcessor().restore(
            anonymized, restored, result.mapping, package_archive=archive
        )

    assert not restored.exists()


def test_docx_deleted_graphics_placeholder_does_not_restore_dangling_relationship(tmp_path):
    source = tmp_path / "source.docx"
    image = tmp_path / "synthetic.png"
    anonymized = tmp_path / "anonymized.docx"
    edited = tmp_path / "edited.docx"
    restored = tmp_path / "restored.docx"
    image.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    ))
    document = Document()
    document.add_paragraph("Обычный текст")
    document.add_picture(str(image), width=Inches(1))
    document.save(source)
    result = DocxProcessor().anonymize(source, anonymized)
    changed = Document(anonymized)
    for paragraph in changed.paragraphs:
        if "[СХЕМА-" in paragraph.text:
            paragraph.clear()
            paragraph.add_run("Схема удалена редактором")
    changed.save(edited)

    DocxProcessor().restore(
        edited, restored, result.mapping, package_archive=result.package_archive
    )

    with ZipFile(restored) as package:
        assert not any(name.startswith("word/media/") for name in package.namelist())
        relationships = etree.fromstring(package.read("word/_rels/document.xml.rels"))
        assert not relationships.xpath(
            "//*[local-name()='Relationship' and contains(@Type, '/image')]"
        )
    Document(restored)


def test_docx_deleting_one_of_two_graphics_restores_only_retained_placeholder(tmp_path):
    source = tmp_path / "source.docx"
    first_image = tmp_path / "first.png"
    second_image = tmp_path / "second.png"
    anonymized = tmp_path / "anonymized.docx"
    edited = tmp_path / "edited.docx"
    restored = tmp_path / "restored.docx"
    first_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    second_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR42mP8z8BQDwAFgAH/q640GAAAAABJRU5ErkJggg=="
    )
    first_image.write_bytes(first_bytes)
    second_image.write_bytes(second_bytes)
    document = Document()
    document.add_paragraph("Обычный текст")
    document.add_picture(str(first_image), width=Inches(1))
    document.add_picture(str(second_image), width=Inches(1))
    document.save(source)
    result = DocxProcessor().anonymize(source, anonymized)
    assert len(result.package_archive["fragments"]) == 2
    changed = Document(anonymized)
    for paragraph in changed.paragraphs:
        if "[СХЕМА-2]" in paragraph.text:
            paragraph.clear()
            paragraph.add_run("Вторая схема удалена")
    changed.save(edited)

    DocxProcessor().restore(
        edited, restored, result.mapping, package_archive=result.package_archive
    )

    with ZipFile(restored) as package:
        restored_media = [
            package.read(name)
            for name in package.namelist()
            if name.startswith("word/media/")
        ]
        relationships = etree.fromstring(package.read("word/_rels/document.xml.rels"))
        document_xml = etree.fromstring(package.read("word/document.xml"))
    assert restored_media == [first_bytes]
    assert len(relationships.xpath(
        "//*[local-name()='Relationship' and contains(@Type, '/image')]"
    )) == 1
    assert len(document_xml.xpath(".//w:drawing", namespaces={
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    })) == 1
    Document(restored)


def test_docx_graphics_placeholder_does_not_collide_with_existing_text(tmp_path):
    source = tmp_path / "source.docx"
    image = tmp_path / "synthetic.png"
    anonymized = tmp_path / "anonymized.docx"
    restored = tmp_path / "restored.docx"
    image.write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    ))
    document = Document()
    document.add_paragraph("Пользовательский текст [СХЕМА-1]")
    document.add_picture(str(image), width=Inches(1))
    document.save(source)

    result = DocxProcessor().anonymize(source, anonymized)
    assert result.package_archive["fragments"][0]["marker"] == "[СХЕМА-2]"
    DocxProcessor().restore(
        anonymized, restored, result.mapping, package_archive=result.package_archive
    )

    restored_document = Document(restored)
    assert restored_document.paragraphs[0].text == "Пользовательский текст [СХЕМА-1]"
    assert len(restored_document.inline_shapes) == 1


def test_docx_anonymize_preserves_byte_identical_unchanged_xml_parts(tmp_path):
    source = tmp_path / "source-byte-preserving.docx"
    output = tmp_path / "anonymized-byte-preserving.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.save(source)

    expected = {}

    def alternate_xml_serialization(payload):
        declaration_end = payload.find(b"?>")
        assert declaration_end >= 0
        body = payload[declaration_end + 2 :].lstrip(b"\r\n")
        changed = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n' + body
        expected["payload"] = changed
        return changed

    _rewrite_docx_parts(
        source,
        {"customXml/item1.xml": alternate_xml_serialization},
    )

    DocxProcessor().anonymize(source, output)

    with ZipFile(output) as package:
        actual = package.read("customXml/item1.xml")
    assert actual == expected["payload"]


def test_docx_split_runs_tables_headers_and_restore_unknown(tmp_path):
    src = tmp_path / "source.docx"
    anon = tmp_path / "anon.docx"
    restored = tmp_path / "restored.docx"
    doc = Document()
    p = doc.add_paragraph(); p.add_run("Иванов ").bold = True; p.add_run("Сергей ").italic = True; p.add_run("Петрович tail").underline = True
    outer = doc.add_table(1, 1); cell = outer.cell(0, 0); nested = cell.add_table(1, 1); q = nested.cell(0, 0).paragraphs[0]; q.add_run("s.iva"); q.add_run("nov@почта.ru")
    h = doc.sections[0].header.paragraphs[0]; h.add_run("+7 999 "); h.add_run("123-45-67")
    f = doc.sections[0].footer.paragraphs[0]; f.add_run("ООО «Аль"); f.add_run("фа»")
    doc.save(src)

    result = DocxProcessor().anonymize(src, anon)
    assert src.read_bytes() != anon.read_bytes()
    out = Document(anon)
    assert out.paragraphs[0].text == "[ФИО-1] tail"
    assert out.paragraphs[0].runs[0].bold is True
    assert out.paragraphs[0].runs[-1].underline is True
    assert "[ПОЧТА-1]" in outer_text(Document(anon))
    assert "[ТЕЛЕФОН-1]" in Document(anon).sections[0].header.paragraphs[0].text
    assert "[ОРГАНИЗАЦИЯ-1]" in Document(anon).sections[0].footer.paragraphs[0].text

    edited = Document(anon); edited.add_paragraph("неизвестно [ФИО-999]"); edited.save(anon)
    unknown = DocxProcessor().restore(anon, restored, result.mapping)
    restored_doc = Document(restored)
    assert restored_doc.paragraphs[0].text == "Иванов Сергей Петрович tail"
    assert "[ФИО-999]" in restored_doc.paragraphs[-1].text
    assert unknown == ["[ФИО-999]"]


def test_docx_restore_preserves_word_generated_table_row_height(tmp_path):
    source = tmp_path / "source.docx"
    anonymized = tmp_path / "anonymized.docx"
    edited = tmp_path / "edited.docx"
    restored = tmp_path / "restored.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.add_table(rows=1, cols=1).cell(0, 0).text = "Ячейка"
    document.save(source)
    result = DocxProcessor().anonymize(source, anonymized)

    word_saved = Document(anonymized)
    row_properties = OxmlElement("w:trPr")
    row_height = OxmlElement("w:trHeight")
    row_height.set(qn("w:val"), "497")
    row_properties.append(row_height)
    word_saved.tables[0].rows[0]._tr.insert(0, row_properties)
    word_saved.save(edited)

    DocxProcessor().restore(edited, restored, result.mapping)

    restored_row = Document(restored).tables[0].rows[0]._tr
    assert restored_row.xpath("./w:trPr/w:trHeight/@w:val") == ["497"]


def outer_text(doc):
    values = []
    def walk(table):
        for row in table.rows:
            for cell in row.cells:
                values.extend(p.text for p in cell.paragraphs)
                for nested in cell.tables: walk(nested)
    for table in doc.tables: walk(table)
    return "\n".join(values)


def test_docx_sanitizes_metadata_deletions_external_relationships_and_flags_unsupported(tmp_path):
    src, out = tmp_path / "dirty.docx", tmp_path / "clean.docx"
    doc = Document(); doc.add_paragraph("Иванов Сергей Петрович")
    doc.core_properties.author = "CANARY_AUTHOR"
    p = doc.paragraphs[0]._p
    deletion = OxmlElement("w:del"); run = OxmlElement("w:r"); txt = OxmlElement("w:delText"); txt.text = "CANARY_DELETED"; run.append(txt); deletion.append(run); p.append(deletion)
    doc.part.rels.add_relationship("http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", "https://CANARY_EXTERNAL.invalid", "rExternal", is_external=True)
    doc.save(src)
    report = DocxProcessor().anonymize(src, out)
    xml = _all_xml(out)
    for canary in (b"CANARY_AUTHOR", b"CANARY_DELETED", b"CANARY_EXTERNAL"):
        assert canary not in xml
    Document(out)
    assert report.ready


def test_docx_physically_removes_custom_properties_part_and_package_references(tmp_path):
    source = tmp_path / "custom-properties.docx"
    output = tmp_path / "custom-properties.anonymized.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.save(source)

    content_types_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
    relationships_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    custom_relationship = (
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties"
    )

    def add_content_type(payload):
        root = etree.fromstring(payload)
        override = etree.SubElement(root, f"{{{content_types_ns}}}Override")
        override.set("PartName", "/docProps/custom.xml")
        override.set(
            "ContentType",
            "application/vnd.openxmlformats-officedocument.custom-properties+xml",
        )
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    def add_relationship(payload):
        root = etree.fromstring(payload)
        relationship = etree.SubElement(root, f"{{{relationships_ns}}}Relationship")
        relationship.set("Id", "rId99")
        relationship.set("Type", custom_relationship)
        relationship.set("Target", "docProps/custom.xml")
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    _rewrite_docx_parts(
        source,
        {
            "[Content_Types].xml": add_content_type,
            "_rels/.rels": add_relationship,
        },
    )
    replacement = source.with_suffix(".with-custom.docx")
    with ZipFile(source) as incoming, ZipFile(replacement, "w", ZIP_DEFLATED) as outgoing:
        for info in incoming.infolist():
            outgoing.writestr(info, incoming.read(info.filename))
        outgoing.writestr(
            "docProps/custom.xml",
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" '
            b'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
            b'<property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" name="Secret">'
            b'<vt:lpwstr>CUSTOM_PROPERTY_CANARY</vt:lpwstr></property></Properties>',
        )
    replacement.replace(source)

    report = DocxProcessor().anonymize(source, output)

    with ZipFile(output) as package:
        names = set(package.namelist())
        relationships = etree.fromstring(package.read("_rels/.rels"))
        content_types = etree.fromstring(package.read("[Content_Types].xml"))
    assert "docProps/custom.xml" not in names
    assert not relationships.xpath(
        "//*[local-name()='Relationship'][@Type=$type or @Target='docProps/custom.xml']",
        type=custom_relationship,
    )
    assert not content_types.xpath(
        "//*[local-name()='Override'][@PartName='/docProps/custom.xml']"
    )
    assert report.ready
    Document(output)


def test_docx_rejects_doctype_without_publishing_output(tmp_path):
    source = tmp_path / "doctype.docx"
    output = tmp_path / "doctype.anonymized.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.save(source)

    def add_doctype(payload):
        declaration_end = payload.index(b"?>") + 2
        return (
            payload[:declaration_end]
            + b'<!DOCTYPE Types [<!ENTITY canary "DOCTYPE_SECRET_CANARY">]>'
            + payload[declaration_end:]
        )

    _rewrite_docx_parts(source, {"[Content_Types].xml": add_doctype})

    with pytest.raises(ValueError, match="DTD"):
        DocxProcessor().anonymize(source, output)

    assert not output.exists()


def test_docx_removes_metadata_comments_without_failing(tmp_path):
    source = tmp_path / "metadata-comment.docx"
    output = tmp_path / "metadata-comment.anonymized.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.save(source)

    def add_comment(payload):
        root = etree.fromstring(payload)
        root.insert(0, etree.Comment("METADATA_COMMENT_SECRET_CANARY"))
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    _rewrite_docx_parts(source, {"docProps/core.xml": add_comment})

    report = DocxProcessor().anonymize(source, output)

    assert report.ready
    assert b"METADATA_COMMENT_SECRET_CANARY" not in _all_xml(output)
    Document(output)


def test_docx_removes_xml_comments_from_non_metadata_parts(tmp_path):
    source = tmp_path / "styles-comment.docx"
    output = tmp_path / "styles-comment.anonymized.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.save(source)

    def add_comment(payload):
        root = etree.fromstring(payload)
        root.insert(0, etree.Comment("STYLES_COMMENT_SECRET_CANARY"))
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    _rewrite_docx_parts(source, {"word/styles.xml": add_comment})

    report = DocxProcessor().anonymize(source, output)

    assert report.ready
    assert b"STYLES_COMMENT_SECRET_CANARY" not in _all_xml(output)
    Document(output)


def test_docx_external_hyperlink_is_unwrapped_without_dangling_relationship_reference(tmp_path):
    src, out = tmp_path / "linked.docx", tmp_path / "clean.docx"
    doc = Document()
    paragraph = doc.add_paragraph("Ссылка: ")
    rel_id = doc.part.relate_to(
        "https://EXTERNAL_RELATIONSHIP_CANARY.invalid/path",
        RELATIONSHIP_TYPE.HYPERLINK,
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), rel_id)
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = "видимый текст"
    run.append(text)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)
    doc.save(src)

    report = DocxProcessor().anonymize(src, out)

    with ZipFile(out) as package:
        relationships = etree.fromstring(package.read("word/_rels/document.xml.rels"))
        relationship_ids = {relationship.get("Id") for relationship in relationships}
        document_xml = etree.fromstring(package.read("word/document.xml"))
        referenced_ids = set(document_xml.xpath(
            "//@r:id",
            namespaces={"r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"},
        ))
    assert referenced_ids <= relationship_ids
    assert "EXTERNAL_RELATIONSHIP_CANARY" not in _all_xml(out).decode("utf-8")
    assert "видимый текст" in "".join(document_xml.itertext())
    assert report.ready


def test_docx_preserves_context_valid_dynamic_formatting_values(tmp_path):
    src, out = tmp_path / "formatted.docx", tmp_path / "formatted.anonymized.docx"
    doc = Document()
    section = doc.sections[0]
    section.left_margin = Inches(0.7)
    section.right_margin = Inches(0.8)
    paragraph = doc.add_paragraph("Иванов Сергей Петрович")
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.runs[0]
    run.font.name = "Arial"
    run.font.size = Pt(13)
    run.font.color.rgb = RGBColor(0x60, 0x5E, 0x5C)
    table = doc.add_table(rows=1, cols=1)
    table.autofit = False
    table.cell(0, 0).width = Inches(2.37)
    table.cell(0, 0).vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.BOTTOM
    table.cell(0, 0).text = "ячейка"
    doc.save(src)

    DocxProcessor().anonymize(src, out)
    reopened = Document(out)

    assert reopened.sections[0].left_margin == Inches(0.7)
    assert reopened.sections[0].right_margin == Inches(0.8)
    assert reopened.paragraphs[0].alignment == WD_ALIGN_PARAGRAPH.RIGHT
    assert reopened.paragraphs[0].runs[0].font.size == Pt(13)
    assert reopened.paragraphs[0].runs[0].font.color.rgb == RGBColor(0x60, 0x5E, 0x5C)
    assert reopened.tables[0].cell(0, 0).vertical_alignment == WD_CELL_VERTICAL_ALIGNMENT.BOTTOM


def test_docx_preserves_required_dynamic_attributes_across_word_parts(tmp_path):
    src, out = tmp_path / "required.docx", tmp_path / "required.anonymized.docx"
    doc = Document()
    run = doc.add_paragraph("Иванов Сергей Петрович").add_run(" без жирного")
    run.bold = False
    doc.add_table(rows=1, cols=3).cell(0, 0).merge(doc.tables[0].cell(0, 2)).text = "ячейка"
    doc.save(src)

    def mutate(name, changes):
        def apply(payload):
            root = etree.fromstring(payload)
            namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
                          "a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
            for xpath, attribute, value in changes:
                nodes = root.xpath(xpath, namespaces=namespaces)
                assert nodes, (name, xpath)
                nodes[0].set(attribute, value)
            return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        return apply

    def add_web_div(payload):
        root = etree.fromstring(payload)
        divs = etree.SubElement(root, qn("w:divs"))
        div = etree.SubElement(divs, qn("w:div"))
        div.set(qn("w:id"), "413207870")
        for local, value in (("bodyDiv", "1"), ("marLeft", "0")):
            node = etree.SubElement(div, qn(f"w:{local}"))
            node.set(qn("w:val"), value)
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    def add_style_dynamics(payload):
        root = etree.fromstring(payload)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        style = root.xpath("//w:style[1]", namespaces=ns)[0]
        ppr = style.find(qn("w:pPr"))
        if ppr is None:
            ppr = etree.SubElement(style, qn("w:pPr"))
        num_pr = etree.SubElement(ppr, qn("w:numPr"))
        for local, value in (("ilvl", "7"), ("numId", "41")):
            node = etree.SubElement(num_pr, qn(f"w:{local}"))
            node.set(qn("w:val"), value)
        widow = etree.SubElement(ppr, qn("w:widowControl"))
        widow.set(qn("w:val"), "0")
        rpr = style.find(qn("w:rPr"))
        if rpr is None:
            rpr = etree.SubElement(style, qn("w:rPr"))
        kern = etree.SubElement(rpr, qn("w:kern"))
        kern.set(qn("w:val"), "26")
        layout = etree.SubElement(rpr, qn("w:eastAsianLayout"))
        layout.set(qn("w:id"), "128")
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    _rewrite_docx_parts(src, {
        "word/document.xml": mutate("document", [
            ("//w:pgSz[1]", qn("w:orient"), "landscape"),
        ]),
        "word/numbering.xml": mutate("numbering", [
            ("//w:abstractNum[1]", qn("w:abstractNumId"), "36"),
            ("//w:abstractNumId[1]", qn("w:val"), "36"),
        ]),
        "word/theme/theme1.xml": mutate("theme", [
            ("//a:theme", "name", "Office-Design"),
            ("//a:latin[1]", "typeface", "Arial"),
            ("//a:ln[1]", "w", "6350"),
            ("//a:srgbClr[1]", "val", "FFFFFF"),
        ]),
        "word/styles.xml": add_style_dynamics,
        "word/webSettings.xml": add_web_div,
    })

    DocxProcessor().anonymize(src, out)

    with ZipFile(out) as package:
        document = etree.fromstring(package.read("word/document.xml"))
        numbering = etree.fromstring(package.read("word/numbering.xml"))
        styles = etree.fromstring(package.read("word/styles.xml"))
        theme = etree.fromstring(package.read("word/theme/theme1.xml"))
        web_settings = etree.fromstring(package.read("word/webSettings.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
          "a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    assert document.xpath("//w:gridSpan/@w:val", namespaces=ns) == ["3"]
    assert "0" in document.xpath("//w:b/@w:val", namespaces=ns)
    assert document.xpath("//w:pgSz[1]/@w:orient", namespaces=ns) == ["landscape"]
    assert numbering.xpath("//w:abstractNum[1]/@w:abstractNumId", namespaces=ns) == ["36"]
    assert numbering.xpath("(//w:abstractNumId)[1]/@w:val", namespaces=ns) == ["36"]
    assert theme.xpath("//a:theme/@name", namespaces=ns) == ["Office Theme"]
    assert theme.xpath("(//a:latin)[1]/@typeface", namespaces=ns) == ["Arial"]
    assert theme.xpath("(//a:ln)[1]/@w", namespaces=ns) == ["6350"]
    assert theme.xpath("(//a:srgbClr)[1]/@val", namespaces=ns) == ["FFFFFF"]
    assert "7" in styles.xpath("//w:ilvl/@w:val", namespaces=ns)
    assert "41" in styles.xpath("//w:numId/@w:val", namespaces=ns)
    assert "26" in styles.xpath("//w:kern/@w:val", namespaces=ns)
    assert "128" in styles.xpath("//w:eastAsianLayout/@w:id", namespaces=ns)
    assert web_settings.xpath("//w:bodyDiv/@w:val", namespaces=ns) == ["1"]
    assert web_settings.xpath("//w:div[1]/@w:id", namespaces=ns) == ["413207870"]
    assert web_settings.xpath("//w:marLeft[1]/@w:val", namespaces=ns) == ["0"]


def test_atomic_failure_keeps_previous_output(tmp_path, monkeypatch):
    src, out = tmp_path / "src.docx", tmp_path / "out.docx"
    d = Document(); d.add_paragraph("Иванов Сергей Петрович"); d.save(src)
    out.write_bytes(b"previous")
    monkeypatch.setattr("local_anonymizer.documents.os.replace", lambda *a: (_ for _ in ()).throw(OSError("fail")))
    with pytest.raises(OSError):
        DocxProcessor().anonymize(src, out)
    assert out.read_bytes() == b"previous"


def test_docx_xml_comments_are_removed_without_breaking_anonymization(tmp_path):
    clean = tmp_path / "clean.docx"
    source = tmp_path / "commented.docx"
    output = tmp_path / "anonymized.docx"
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович")
    document.save(clean)

    with ZipFile(clean) as incoming, ZipFile(source, "w") as outgoing:
        for info in incoming.infolist():
            payload = incoming.read(info.filename)
            if info.filename == "word/document.xml":
                payload = payload.replace(b"<w:body>", b"<!--COMMENT_CANARY--><w:body>", 1)
            outgoing.writestr(info, payload)

    result = DocxProcessor().anonymize(source, output)

    assert result.ready is True
    assert not result.warnings
    assert b"COMMENT_CANARY" not in _all_xml(output)
    assert "[ФИО-1]" in "".join(node.text or "" for node in Document(output).element.xpath(".//w:t"))


def test_docx_hyperlink_visible_text_is_anonymized_before_ready(tmp_path):
    src, out = tmp_path / "hyperlink.docx", tmp_path / "hyperlink.anonymized.docx"
    doc = Document(); paragraph = doc.add_paragraph("Контакт: ")
    hyperlink = OxmlElement("w:hyperlink")
    run = OxmlElement("w:r"); text = OxmlElement("w:t"); text.text = "Иванов Сергей Петрович"; run.append(text); hyperlink.append(run)
    paragraph._p.append(hyperlink); doc.save(src)
    result = DocxProcessor().anonymize(src, out)
    assert result.ready
    assert "Иванов Сергей Петрович".encode("utf-8") not in _all_xml(out)
    assert "[ФИО-1]" in "".join(node.text or "" for node in Document(out).element.xpath(".//w:t"))


def test_docx_publication_strips_simple_and_complex_field_instructions_package_wide(tmp_path):
    src = tmp_path / "fields.docx"
    anonymized = tmp_path / "fields.anonymized.docx"
    restored = tmp_path / "fields.restored.docx"
    doc = Document()

    simple = OxmlElement("w:fldSimple")
    simple.set(qn("w:instr"), ' HYPERLINK "https://SIMPLE_FIELD_CANARY.invalid" ')
    simple_run = OxmlElement("w:r")
    simple_text = OxmlElement("w:t")
    simple_text.text = "safe simple result"
    simple_run.append(simple_text)
    simple.append(simple_run)
    doc.add_paragraph()._p.append(simple)

    table_simple = OxmlElement("w:fldSimple")
    table_simple.set(qn("w:instr"), ' HYPERLINK "https://TABLE_FIELD_CANARY.invalid" ')
    table_run = OxmlElement("w:r")
    table_text = OxmlElement("w:t")
    table_text.text = "safe table result"
    table_run.append(table_text)
    table_simple.append(table_run)
    doc.add_table(1, 1).cell(0, 0).paragraphs[0]._p.append(table_simple)

    def add_complex_field(paragraph, first_canary, second_canary, result):
        for field_type in ("begin",):
            run = OxmlElement("w:r")
            field = OxmlElement("w:fldChar")
            field.set(qn("w:fldCharType"), field_type)
            run.append(field)
            paragraph._p.append(run)
        for instruction in (first_canary, second_canary):
            run = OxmlElement("w:r")
            text = OxmlElement("w:instrText")
            text.text = instruction
            run.append(text)
            paragraph._p.append(run)
        for field_type in ("separate",):
            run = OxmlElement("w:r")
            field = OxmlElement("w:fldChar")
            field.set(qn("w:fldCharType"), field_type)
            run.append(field)
            paragraph._p.append(run)
        paragraph.add_run(result)
        run = OxmlElement("w:r")
        field = OxmlElement("w:fldChar")
        field.set(qn("w:fldCharType"), "end")
        run.append(field)
        paragraph._p.append(run)

    add_complex_field(
        doc.sections[0].header.paragraphs[0],
        ' HYPERLINK "https://HEADER_SPLIT_',
        'FIELD_CANARY.invalid" ',
        "safe header result",
    )
    add_complex_field(
        doc.sections[0].footer.paragraphs[0],
        ' HYPERLINK "https://FOOTER_SPLIT_',
        'FIELD_CANARY.invalid" ',
        "safe footer result",
    )
    doc.save(src)

    report = DocxProcessor().anonymize(src, anonymized)
    assert report.ready
    assert report.warnings == []
    anonymized_xml = _all_xml(anonymized)
    for canary in (
        b"SIMPLE_FIELD_CANARY",
        b"TABLE_FIELD_CANARY",
        b"HEADER_SPLIT_",
        b"FOOTER_SPLIT_",
    ):
        assert canary not in anonymized_xml
    for active_field_token in (b"fldSimple", b"instrText", b"fldChar", b"HYPERLINK"):
        assert active_field_token not in anonymized_xml
    for visible_result in (
        b"safe simple result",
        b"safe table result",
        b"safe header result",
        b"safe footer result",
    ):
        assert visible_result in anonymized_xml

    assert DocxProcessor().restore(src, restored, {}) == []
    restored_xml = _all_xml(restored)
    assert b"FIELD_CANARY" not in restored_xml
    assert b"fldSimple" not in restored_xml
    assert b"instrText" not in restored_xml
    assert b"fldChar" not in restored_xml
