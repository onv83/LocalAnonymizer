"""B55: unsupported ODT marks and sensitive structural identifiers."""
from zipfile import ZipFile, ZIP_STORED

import pytest
from lxml import etree

from local_anonymizer.odt import (
    OdtProcessor, OFFICE_NS, TEXT_NS, MANIFEST_NS, extract_odt_text,
)

STYLE_NS = "urn:oasis:names:tc:opendocument:xmlns:style:1.0"
CANARY = "audit.person@example.com"


def write_odt(path, *, body="ordinary", content_styles="", styles=""):
    ns = f'xmlns:office="{OFFICE_NS}" xmlns:text="{TEXT_NS}" xmlns:style="{STYLE_NS}"'
    parts = {
        "content.xml": f'<office:document-content {ns}><office:automatic-styles>{content_styles}</office:automatic-styles><office:body><office:text><text:p>{body}</text:p></office:text></office:body></office:document-content>',
        "styles.xml": f'<office:document-styles {ns}><office:styles>{styles}</office:styles></office:document-styles>',
        "meta.xml": f'<office:document-meta {ns}><office:meta/></office:document-meta>',
    }
    parts["META-INF/manifest.xml"] = (
        f'<manifest:manifest xmlns:manifest="{MANIFEST_NS}"><manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>'
        + ''.join(f'<manifest:file-entry manifest:full-path="{name}" manifest:media-type="text/xml"/>' for name in parts)
        + '</manifest:manifest>'
    )
    with ZipFile(path, "w") as package:
        package.writestr("mimetype", "application/vnd.oasis.opendocument.text", compress_type=ZIP_STORED)
        for name, payload in parts.items():
            package.writestr(name, payload)


@pytest.mark.parametrize("mark", ["reference-mark", "reference-mark-start", "reference-mark-end"])
@pytest.mark.parametrize("preceding", ["before ", "<text:span>before </text:span>"])
def test_reference_marks_removed_without_losing_tail(tmp_path, mark, preceding):
    source, output = tmp_path / "source.odt", tmp_path / "output.odt"
    write_odt(source, body=f'{preceding}<text:{mark} text:name="{CANARY}"/>after')
    original = source.read_bytes()
    OdtProcessor().anonymize(source, output)
    with ZipFile(output) as package:
        assert all(CANARY.encode() not in package.read(n) for n in package.namelist())
        root = etree.fromstring(package.read("content.xml"))
        assert not list(root.iter(f"{{{TEXT_NS}}}{mark}"))
    assert extract_odt_text(output) == "before after"
    assert source.read_bytes() == original


@pytest.mark.parametrize("part", ["content.xml", "styles.xml"])
@pytest.mark.parametrize("attribute", [
    "style:name", "style:display-name", "style:parent-style-name",
    "style:next-style-name", "style:list-style-name", "style:master-page-name",
    "style:page-layout-name", "style:data-style-name", "style:apply-style-name",
    "text:style-name", "text:class-names", "text:name", "text:ref-name",
])
def test_sensitive_style_identifiers_fail_closed(tmp_path, part, attribute):
    source, output = tmp_path / "source.odt", tmp_path / "output.odt"
    fragment = f'<style:style {attribute}="{CANARY}" style:family="paragraph"/>'
    write_odt(source, **{"content_styles" if part == "content.xml" else "styles": fragment})
    original = source.read_bytes()
    with pytest.raises(ValueError, match="ODT.*идентификатор") as error:
        OdtProcessor().anonymize(source, output)
    assert CANARY not in str(error.value)
    assert not output.exists()
    assert source.read_bytes() == original


def test_sensitive_paragraph_style_reference_preserves_existing_target(tmp_path):
    source, output = tmp_path / "source.odt", tmp_path / "output.odt"
    write_odt(source, body=f'<text:span text:style-name="{CANARY}">ordinary</text:span>')
    output.write_bytes(b"existing output")
    with pytest.raises(ValueError, match="ODT.*идентификатор"):
        OdtProcessor().anonymize(source, output)
    assert output.read_bytes() == b"existing output"


def test_ordinary_style_graph_is_preserved_byte_for_byte(tmp_path):
    source, output = tmp_path / "source.odt", tmp_path / "output.odt"
    write_odt(
        source,
        body='<text:span text:style-name="Emphasis" text:class-names="Emphasis Strong">ordinary</text:span>',
        content_styles='<style:style style:name="Emphasis" style:family="text" style:parent-style-name="Strong"><style:text-properties xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" fo:font-style="italic"/></style:style>',
        styles='<style:style style:name="Strong" style:display-name="Strong" style:family="text"/><style:style style:name="Body" style:family="paragraph" style:next-style-name="Body"/>',
    )
    OdtProcessor().anonymize(source, output)
    with ZipFile(source) as original, ZipFile(output) as sanitized:
        for part in ("content.xml", "styles.xml"):
            assert sanitized.read(part) == original.read(part)
