from __future__ import annotations

from html import escape
from pathlib import Path
import re
import zipfile

from lxml import etree

from .odt import _preflight_odt_package


NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
}

_STYLE_NAME = f"{{{NS['style']}}}name"
_STYLE_FAMILY = f"{{{NS['style']}}}family"
_STYLE_PARENT = f"{{{NS['style']}}}parent-style-name"
_TEXT_STYLE = f"{{{NS['text']}}}style-name"
_TABLE_STYLE = f"{{{NS['table']}}}style-name"
_OUTLINE_LEVEL = f"{{{NS['text']}}}outline-level"
_COL_SPAN = f"{{{NS['table']}}}number-columns-spanned"
_ROW_SPAN = f"{{{NS['table']}}}number-rows-spanned"
_REPEAT = f"{{{NS['text']}}}c"

_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")
_FONT_SIZE = re.compile(r"(?:[1-9]\d?(?:\.\d+)?|100)(?:pt|px)\Z")
_SAFE_INT = re.compile(r"[1-9]\d{0,3}\Z")


def _parse_xml(data: bytes):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                             recover=False, huge_tree=False)
    return etree.fromstring(data, parser=parser)


def _style_maps(*roots) -> dict[tuple[str, str], dict[str, str]]:
    raw: dict[tuple[str, str], tuple[str | None, dict[str, str]]] = {}
    for root in roots:
        for node in root.xpath(".//style:style", namespaces=NS):
            name = node.get(_STYLE_NAME)
            family = node.get(_STYLE_FAMILY)
            if not name or family not in {"paragraph", "text", "table-cell"}:
                continue
            props: dict[str, str] = {}
            text_props = node.find("style:text-properties", namespaces=NS)
            paragraph_props = node.find("style:paragraph-properties", namespaces=NS)
            cell_props = node.find("style:table-cell-properties", namespaces=NS)
            if text_props is not None:
                weight = text_props.get(f"{{{NS['fo']}}}font-weight")
                posture = text_props.get(f"{{{NS['fo']}}}font-style")
                underline = text_props.get(f"{{{NS['style']}}}text-underline-style")
                size = text_props.get(f"{{{NS['fo']}}}font-size")
                color = text_props.get(f"{{{NS['fo']}}}color")
                if weight == "bold":
                    props["bold"] = "1"
                if posture == "italic":
                    props["italic"] = "1"
                if underline and underline != "none":
                    props["underline"] = "1"
                if size and _FONT_SIZE.fullmatch(size):
                    props["font-size"] = size
                if color and _HEX_COLOR.fullmatch(color):
                    props["color"] = color.lower()
            if paragraph_props is not None:
                alignment = paragraph_props.get(f"{{{NS['fo']}}}text-align")
                if alignment in {"left", "right", "center", "justify"}:
                    props["align"] = alignment
            if cell_props is not None:
                background = cell_props.get(f"{{{NS['fo']}}}background-color")
                if background and _HEX_COLOR.fullmatch(background):
                    props["background-color"] = background.lower()
            raw[(family, name)] = (node.get(_STYLE_PARENT), props)

    resolved: dict[tuple[str, str], dict[str, str]] = {}

    def resolve(key: tuple[str, str], trail: frozenset[tuple[str, str]] = frozenset()):
        if key in resolved:
            return resolved[key]
        if key in trail or key not in raw:
            return {}
        parent, own = raw[key]
        result = dict(resolve((key[0], parent), trail | {key})) if parent else {}
        result.update(own)
        resolved[key] = result
        return result

    for key in raw:
        resolve(key)
    return resolved


def _style_attr(props: dict[str, str], *, include_alignment: bool = False) -> str:
    names = ("font-size", "color", "background-color")
    values = [f"{name}:{props[name]}" for name in names if name in props]
    return f' style="{escape(";".join(values), quote=True)}"' if values else ""


def _wrap_text(value: str, props: dict[str, str]) -> str:
    result = value
    if props.get("underline"):
        result = f"<u>{result}</u>"
    if props.get("italic"):
        result = f"<em>{result}</em>"
    if props.get("bold"):
        result = f"<strong>{result}</strong>"
    style = _style_attr(props)
    if style:
        result = f"<span{style}>{result}</span>"
    return result


def _inline(node, styles: dict[tuple[str, str], dict[str, str]]) -> str:
    parts = [escape(node.text or "")]
    annotation = f"{{{NS['office']}}}annotation"
    for child in node:
        if child.tag == annotation:
            rendered = ""
        elif child.tag == f"{{{NS['text']}}}line-break":
            rendered = "<br>"
        elif child.tag == f"{{{NS['text']}}}tab":
            rendered = '<span class="docx-tab">\t</span>'
        elif child.tag == f"{{{NS['text']}}}s":
            raw = child.get(_REPEAT, "1")
            count = min(int(raw), 4096) if _SAFE_INT.fullmatch(raw) else 1
            rendered = " " * count
        elif child.tag == f"{{{NS['text']}}}span":
            props = styles.get(("text", child.get(_TEXT_STYLE, "")), {})
            rendered = _wrap_text(_inline(child, styles), props)
        else:
            # Links, bookmarks and unknown inline ODF nodes contribute text only.
            rendered = _inline(child, styles)
        parts.append(rendered)
        parts.append(escape(child.tail or ""))
    return "".join(parts)


def _block(node, styles: dict[tuple[str, str], dict[str, str]]) -> str:
    tag = node.tag
    if tag == f"{{{NS['office']}}}annotation":
        return ""
    if tag in {f"{{{NS['text']}}}p", f"{{{NS['text']}}}h"}:
        props = styles.get(("paragraph", node.get(_TEXT_STYLE, "")), {})
        alignment = props.get("align")
        classes = "docx-paragraph" + (f" align-{alignment}" if alignment else "")
        level = node.get(_OUTLINE_LEVEL, "1")
        element = f"h{level}" if tag.endswith("}h") and level in {"1", "2", "3", "4", "5", "6"} else "p"
        content = _inline(node, styles)
        if props.get("underline"):
            content = f"<u>{content}</u>"
        if props.get("italic"):
            content = f"<em>{content}</em>"
        if props.get("bold"):
            content = f"<strong>{content}</strong>"
        return f'<{element} class="{classes}"{_style_attr(props)}>{content}</{element}>'
    if tag == f"{{{NS['text']}}}list":
        items = []
        for item in node:
            if item.tag == f"{{{NS['text']}}}list-item":
                items.append("<li>" + "".join(_block(child, styles) for child in item) + "</li>")
        return "<ul>" + "".join(items) + "</ul>"
    if tag == f"{{{NS['table']}}}table":
        rows = "".join(_block(child, styles) for child in node
                       if child.tag == f"{{{NS['table']}}}table-row")
        return f'<table class="docx-table"><tbody>{rows}</tbody></table>'
    if tag == f"{{{NS['table']}}}table-row":
        cells = "".join(_block(child, styles) for child in node
                        if child.tag != f"{{{NS['table']}}}covered-table-cell")
        return f"<tr>{cells}</tr>"
    if tag == f"{{{NS['table']}}}table-cell":
        attrs = []
        for source, target in ((_COL_SPAN, "colspan"), (_ROW_SPAN, "rowspan")):
            value = node.get(source)
            if value and _SAFE_INT.fullmatch(value) and int(value) > 1:
                attrs.append(f'{target}="{int(value)}"')
        props = styles.get(("table-cell", node.get(_TABLE_STYLE, "")), {})
        if style := _style_attr(props):
            attrs.append(style.strip())
        suffix = (" " + " ".join(attrs)) if attrs else ""
        return f"<td{suffix}>" + "".join(_block(child, styles) for child in node) + "</td>"
    return "".join(_block(child, styles) for child in node)


def render_odt_preview(path: str | Path) -> str:
    """Render a presentation-only, escaped ODT subset without active content."""
    _preflight_odt_package(Path(path))
    with zipfile.ZipFile(path) as archive:
        content = _parse_xml(archive.read("content.xml"))
        style_roots = [content]
        if "styles.xml" in archive.namelist():
            style_roots.append(_parse_xml(archive.read("styles.xml")))
    styles = _style_maps(*style_roots)
    bodies = content.xpath("/office:document-content/office:body/office:text", namespaces=NS)
    rendered = "".join(_block(child, styles) for body in bodies for child in body)
    return f'<article class="docx-preview odt-preview">{rendered}</article>'
