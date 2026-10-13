from html import unescape
import re
import zipfile
from pathlib import Path

from local_anonymizer.app import AppApi


MIMETYPE = "application/vnd.oasis.opendocument.text"


def _write_formatted_odt(path: Path) -> None:
    content = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
 xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
 xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
 xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
 xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
 xmlns:xlink="http://www.w3.org/1999/xlink">
 <office:automatic-styles>
  <style:style style:name="HeadingFancy" style:family="paragraph">
   <style:paragraph-properties fo:text-align="center"/>
   <style:text-properties fo:font-size="18pt" fo:font-weight="bold" fo:color="#123456"/>
  </style:style>
  <style:style style:name="Accent" style:family="text">
   <style:text-properties fo:font-style="italic" style:text-underline-style="solid"/>
  </style:style>
  <style:style style:name="CellShade" style:family="table-cell">
   <style:table-cell-properties fo:background-color="#ffeecc"/>
  </style:style>
 </office:automatic-styles>
 <office:body><office:text>
  <text:h text:outline-level="1" text:style-name="HeadingFancy">Отчёт &lt;script&gt;alert(1)&lt;/script&gt;</text:h>
  <text:p>Владелец <text:span text:style-name="Accent">Иванов Сергей Петрович</text:span><text:line-break/>строка<text:tab/>после табуляции</text:p>
  <text:list><text:list-item><text:p>Первый пункт</text:p></text:list-item><text:list-item><text:p>Второй пункт</text:p></text:list-item></text:list>
  <table:table>
   <table:table-row><table:table-cell table:number-columns-spanned="2" table:style-name="CellShade"><text:p>Объединённая ячейка</text:p></table:table-cell><table:covered-table-cell/></table:table-row>
   <table:table-row><table:table-cell><text:p>Лево</text:p></table:table-cell><table:table-cell><text:p>Право</text:p></table:table-cell></table:table-row>
  </table:table>
  <text:p><text:a xlink:href="https://example.invalid/private">безопасный текст ссылки</text:a></text:p>
  <office:annotation><dc:creator xmlns:dc="http://purl.org/dc/elements/1.1/">Alice</dc:creator><text:p>секретный комментарий</text:p></office:annotation>
 </office:text></office:body>
</office:document-content>"""
    styles = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"/>"""
    manifest = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">
 <manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>
 <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
 <manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>
 <manifest:file-entry manifest:full-path="meta.xml" manifest:media-type="text/xml"/>
</manifest:manifest>"""
    meta = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"><office:meta/></office:document-meta>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        archive.writestr("content.xml", content)
        archive.writestr("styles.xml", styles)
        archive.writestr("meta.xml", meta)
        archive.writestr("META-INF/manifest.xml", manifest)


def _visible_text(fragment: str) -> str:
    return unescape(re.sub(r"<[^>]*>", "", fragment))


def test_odt_preview_renders_safe_formatting_in_application(tmp_path):
    source = tmp_path / "formatted.odt"
    _write_formatted_odt(source)
    api = AppApi(root=tmp_path / "app")
    document_id = api.import_paths([str(source)])["ids"][0]

    preview = api.preview_document(document_id)
    rich = preview["rich_html"]

    assert preview["format"] == "odt"
    assert 'class="docx-preview odt-preview"' in rich
    assert '<h1 class="docx-paragraph align-center" style="font-size:18pt;color:#123456"><strong>' in rich
    assert "<em><u>Иванов Сергей Петрович</u></em>" in rich
    assert '<table class="docx-table">' in rich and 'colspan="2"' in rich
    assert 'style="background-color:#ffeecc"' in rich
    assert "<ul>" in rich and "Первый пункт" in rich
    assert "<br>" in rich and 'class="docx-tab"' in rich
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rich and "<script" not in rich
    assert "href=" not in rich and "example.invalid" not in rich
    assert "секретный комментарий" not in rich and "Alice" not in rich
    assert str(tmp_path) not in rich


def test_anonymized_odt_preview_preserves_formatting_and_hides_original(tmp_path):
    source = tmp_path / "formatted-sensitive.odt"
    _write_formatted_odt(source)
    api = AppApi(root=tmp_path / "app")
    document_id = api.import_paths([str(source)])["ids"][0]

    preview = api.preview_anonymized_document(document_id)

    assert preview["format"] == "odt"
    assert "Иванов Сергей Петрович" not in preview["rich_html"]
    assert "[ФИО-1]" in _visible_text(preview["rich_html"])
    assert "<em><u>" in preview["rich_html"]
    assert '<table class="docx-table">' in preview["rich_html"]
    assert preview["replacement_count"] >= 1
