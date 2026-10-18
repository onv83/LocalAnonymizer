from __future__ import annotations

import base64
from html import escape
import re

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.exceptions import InvalidXmlError
from docx.oxml.ns import qn
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from docx.text.run import Run


_HEADING_RE = re.compile(r"Heading\s*([1-6])$", re.IGNORECASE)
_ALIGNMENT_CLASSES = {
    WD_ALIGN_PARAGRAPH.LEFT: "align-left",
    WD_ALIGN_PARAGRAPH.CENTER: "align-center",
    WD_ALIGN_PARAGRAPH.RIGHT: "align-right",
    WD_ALIGN_PARAGRAPH.JUSTIFY: "align-justify",
    WD_ALIGN_PARAGRAPH.DISTRIBUTE: "align-justify",
}
_PREVIEW_IMAGE_LIMIT = 16 * 1024 * 1024
_PREVIEW_IMAGE_TYPES = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
}


def _safe_format_value(getter):
    try:
        return getter()
    except (AttributeError, InvalidXmlError, TypeError, ValueError):
        return None


def _image_html(node, run_element, paragraph: Paragraph) -> str:
    relationship_id = node.get(qn("r:embed")) or node.get(qn("r:id"))
    if not relationship_id:
        return ""
    try:
        relationship = paragraph.part.rels[relationship_id]
        if relationship.is_external:
            return ""
        image_part = relationship.target_part
        content_type = str(image_part.content_type).lower()
        blob = bytes(image_part.blob)
    except (AttributeError, KeyError, TypeError, ValueError):
        return ""
    signatures = _PREVIEW_IMAGE_TYPES.get(content_type)
    if not signatures or not any(blob.startswith(signature) for signature in signatures):
        return ""
    if not blob or len(blob) > _PREVIEW_IMAGE_LIMIT:
        return ""

    style = "max-width:100%;height:auto"
    extents = run_element.xpath(".//wp:extent")
    if extents:
        try:
            width = max(1, min(1600, round(int(extents[0].get("cx")) / 9525)))
            style = f"max-width:100%;width:{width}px;height:auto"
        except (TypeError, ValueError):
            pass
    encoded = base64.b64encode(blob).decode("ascii")
    return (
        f'<img class="docx-image" alt="Встроенное изображение" '
        f'src="data:{content_type};base64,{encoded}" style="{style}">'
    )


def _run_content(run_element, paragraph: Paragraph) -> str:
    parts: list[str] = []
    for node in run_element.iter():
        local = node.tag.rsplit("}", 1)[-1]
        if local == "t":
            parts.append(escape(node.text or ""))
        elif local in {"br", "cr"}:
            parts.append("<br>")
        elif local == "tab":
            parts.append('<span class="docx-tab">\t</span>')
        elif local in {"blip", "imagedata"}:
            parts.append(_image_html(node, run_element, paragraph))
    return "".join(parts)


def _run_html(run_element, paragraph: Paragraph) -> str:
    content = _run_content(run_element, paragraph)
    if not content:
        return ""
    run = Run(run_element, paragraph)
    if _safe_format_value(lambda: run.underline):
        content = f"<u>{content}</u>"
    if _safe_format_value(lambda: run.italic):
        content = f"<em>{content}</em>"
    if _safe_format_value(lambda: run.bold):
        content = f"<strong>{content}</strong>"

    declarations: list[str] = []
    size = _safe_format_value(lambda: run.font.size)
    if size is not None:
        points = max(8.0, min(72.0, float(size.pt)))
        rendered = str(int(points)) if points.is_integer() else f"{points:.1f}"
        declarations.append(f"font-size:{rendered}pt")
    rgb = _safe_format_value(lambda: run.font.color.rgb)
    if rgb is not None and re.fullmatch(r"[0-9A-Fa-f]{6}", str(rgb)):
        declarations.append(f"color:#{str(rgb).upper()}")
    if declarations:
        content = f'<span style="{";".join(declarations)}">{content}</span>'
    return content


def _paragraph_html(paragraph: Paragraph, anchor: str) -> str:
    content = "".join(
        _run_html(node, paragraph)
        for node in paragraph._p.xpath(".//w:r[not(ancestor::w:del)]")
    )
    alignment = _ALIGNMENT_CLASSES.get(_safe_format_value(lambda: paragraph.alignment))
    classes = "docx-paragraph" + (f" {alignment}" if alignment else "")
    style_nodes = paragraph._p.xpath("./w:pPr/w:pStyle")
    style_id = style_nodes[0].get(qn("w:val"), "") if style_nodes else ""
    match = _HEADING_RE.fullmatch(style_id or "")
    tag = f"h{match.group(1)}" if match else "p"
    return (
        f'<{tag} class="{classes}" data-preview-anchor="{escape(anchor, quote=True)}">'
        f'{content or "<br>"}</{tag}>'
    )


def _container_blocks(container):
    element = container.element.body if hasattr(container, "element") and hasattr(container.element, "body") else container._element
    for child in element.iterchildren():
        local = child.tag.rsplit("}", 1)[-1]
        if local == "p":
            yield Paragraph(child, container)
        elif local == "tbl":
            yield Table(child, container)


def _cell_html(cell: _Cell, anchor: str) -> str:
    return "".join(
        _block_html(block, f"{anchor}/b{block_index}")
        for block_index, block in enumerate(_container_blocks(cell))
    )


def _grid_span(cell_element) -> int:
    value = _safe_format_value(lambda: cell_element.grid_span)
    try:
        return max(1, min(1000, int(value or 1)))
    except (TypeError, ValueError):
        return 1


def _vertical_merge(cell_element):
    return _safe_format_value(lambda: cell_element.vMerge)


def _row_cell_at_column(row_element, wanted_column: int):
    column = 0
    for cell_element in row_element.tc_lst:
        span = _grid_span(cell_element)
        if column == wanted_column:
            return cell_element, span
        if column > wanted_column or wanted_column < column + span:
            return None
        column += span
    return None


def _vertical_span(row_elements, row_index: int, column: int, grid_span: int) -> int:
    span = 1
    for later_row in row_elements[row_index + 1 :]:
        found = _row_cell_at_column(later_row, column)
        if found is None:
            break
        cell_element, later_grid_span = found
        if _vertical_merge(cell_element) != "continue" or later_grid_span != grid_span:
            break
        span += 1
    return span


def _table_html(table: Table, anchor: str) -> str:
    row_elements = list(table._tbl.tr_lst)
    rows: list[str] = []
    for row_index, row_element in enumerate(row_elements):
        rendered_cells: list[str] = []
        column = 0
        for cell_element in row_element.tc_lst:
            grid_span = _grid_span(cell_element)
            vertical_merge = _vertical_merge(cell_element)
            if vertical_merge == "continue":
                column += grid_span
                continue
            attributes: list[str] = []
            if grid_span > 1:
                attributes.append(f' colspan="{grid_span}"')
            if vertical_merge == "restart":
                row_span = _vertical_span(row_elements, row_index, column, grid_span)
                if row_span > 1:
                    attributes.append(f' rowspan="{row_span}"')
            cell = _Cell(cell_element, table)
            rendered_cells.append(
                f"<td{''.join(attributes)}>{_cell_html(cell, f'{anchor}/r{row_index}/c{column}')}</td>"
            )
            column += grid_span
        rows.append(
            f'<tr data-preview-anchor="{escape(f"{anchor}/r{row_index}", quote=True)}">'
            f'{"".join(rendered_cells)}</tr>'
        )
    return '<table class="docx-table"><tbody>' + "".join(rows) + "</tbody></table>"


def _block_html(block, anchor: str) -> str:
    if isinstance(block, Paragraph):
        return _paragraph_html(block, anchor)
    return _table_html(block, anchor)


def _part_section(document, attr: str, class_name: str, title: str) -> str:
    rendered: list[str] = []
    seen: set[int] = set()
    for section in document.sections:
        part = getattr(section, attr)
        identity = id(part._element)
        if identity in seen:
            continue
        seen.add(identity)
        part_index = len(seen) - 1
        body = "".join(
            _block_html(block, f"{class_name}/{part_index}/b{block_index}")
            for block_index, block in enumerate(_container_blocks(part))
        )
        if any((node.text or "").strip() for node in part._element.xpath(".//w:t")):
            rendered.append(f'<section class="{class_name}"><h2>{escape(title)}</h2>{body}</section>')
    return "".join(rendered)


def render_docx_preview(document) -> str:
    """Render a read-only DOCX preview from a fixed HTML allowlist.

    User text is escaped. Relationship targets, style names, field codes,
    and arbitrary OOXML attributes are never serialized. Safe embedded PNG/JPEG
    images are rendered as local data URIs; external and unsupported images are omitted.
    """
    body = "".join(
        _block_html(block, f"body/b{block_index}")
        for block_index, block in enumerate(_container_blocks(document))
    )
    header = _part_section(document, "header", "docx-header", "Верхний колонтитул")
    footer = _part_section(document, "footer", "docx-footer", "Нижний колонтитул")
    return f'<article class="docx-preview"><section class="docx-body">{body}</section>{header}{footer}</article>'
