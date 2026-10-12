from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree

SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


def xlsx_sheet_parts(source: Path) -> dict[str, str]:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    with ZipFile(source) as archive:
        workbook = etree.fromstring(archive.read("xl/workbook.xml"), parser)
        relationships = etree.fromstring(
            archive.read("xl/_rels/workbook.xml.rels"), parser
        )
    targets = {
        relationship.get("Id"): relationship.get("Target", "")
        for relationship in relationships
    }
    relationship_id = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    result: dict[str, str] = {}
    for sheet in workbook.xpath(".//x:sheet", namespaces={"x": SHEET_NS}):
        target = targets[sheet.get(relationship_id)]
        if target.startswith("/"):
            part = target.lstrip("/")
        else:
            part = str(Path("xl", target).as_posix())
        result[sheet.get("name")] = part
    return result


def _replace_text_nodes(nodes, value: str) -> None:
    old_lengths = [len(node.text or "") for node in nodes]
    cursor = 0
    for index, node in enumerate(nodes):
        replacement = (
            value[cursor:]
            if index == len(nodes) - 1
            else value[cursor:cursor + old_lengths[index]]
        )
        cursor += old_lengths[index]
        node.text = replacement
        if replacement.startswith(" ") or replacement.endswith(" "):
            node.set(XML_SPACE, "preserve")
        else:
            node.attrib.pop(XML_SPACE, None)


def _set_cell_value(cell, value: object, rich_source=None) -> None:
    if rich_source is None and cell.get("t") == "inlineStr":
        rich_source = cell.find(f"{{{SHEET_NS}}}is")
    for child in list(cell):
        if etree.QName(child).localname in {"v", "is"}:
            cell.remove(child)
    formula = cell.find(f"{{{SHEET_NS}}}f")
    if isinstance(value, str) and value.startswith("="):
        if formula is None:
            formula = etree.SubElement(cell, f"{{{SHEET_NS}}}f")
        formula.text = value[1:]
        cell.attrib.pop("t", None)
        return
    if formula is not None:
        cell.remove(formula)
    if isinstance(value, str):
        cell.set("t", "inlineStr")
        inline = etree.SubElement(cell, f"{{{SHEET_NS}}}is")
        if rich_source is not None:
            for child in rich_source:
                if etree.QName(child).localname in {"rPh", "phoneticPr"}:
                    continue
                inline.append(etree.fromstring(etree.tostring(child)))
        nodes = inline.xpath(".//x:t", namespaces={"x": SHEET_NS})
        if not nodes:
            nodes = [etree.SubElement(inline, f"{{{SHEET_NS}}}t")]
        _replace_text_nodes(nodes, value)
    else:
        cell.set("t", "n")
        stored = etree.SubElement(cell, f"{{{SHEET_NS}}}v")
        stored.text = str(value)


def rewrite_xlsx_package(
    source: Path,
    output: Path,
    changes: dict[tuple[str, str], object],
) -> None:
    """Patch cells and sensitive OOXML surfaces without an openpyxl save."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    worksheet_parts = set(xlsx_sheet_parts(source).values())
    pending_changes = set(changes)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{output.stem}-", suffix=".xlsx", dir=output.parent)
    os.close(fd)
    temporary = Path(name)
    removed_prefixes = ("xl/comments", "xl/externalLinks/")
    try:
        with ZipFile(source) as incoming, ZipFile(temporary, "w", ZIP_DEFLATED) as outgoing:
            names = set(incoming.namelist())
            shared_items = []
            if "xl/sharedStrings.xml" in names:
                shared_root = etree.fromstring(incoming.read("xl/sharedStrings.xml"), parser)
                shared_items = shared_root.xpath("./x:si", namespaces={"x": SHEET_NS})
            comment_vml = {
                member
                for member in names
                if re.fullmatch(r"xl/drawings/(?:commentsDrawing|vmlDrawing)\d+\.vml", member)
            }
            removed = {
                member for member in names if member.startswith(removed_prefixes)
            } | comment_vml | {"docProps/custom.xml", "xl/sharedStrings.xml"}
            for info in incoming.infolist():
                if info.filename in removed:
                    continue
                payload = incoming.read(info.filename)
                if not info.filename.endswith((".xml", ".rels")):
                    outgoing.writestr(info, payload)
                    continue
                root = etree.fromstring(payload, parser)
                changed = False
                if info.filename in worksheet_parts:
                    ns = {"x": SHEET_NS}
                    for cell in root.xpath(".//x:c", namespaces=ns):
                        key = (info.filename, cell.get("r", ""))
                        rich_source = None
                        shared_value = None
                        inline_value = None
                        if cell.get("t") == "s":
                            value_node = cell.find(f"{{{SHEET_NS}}}v")
                            if value_node is None or not (value_node.text or "").isdigit():
                                raise ValueError("Некорректная ссылка XLSX shared string")
                            index = int(value_node.text)
                            if index >= len(shared_items):
                                raise ValueError("Ссылка XLSX shared string вне допустимого диапазона")
                            rich_source = shared_items[index]
                            shared_value = "".join(
                                rich_source.xpath(
                                    ".//x:t[not(ancestor::x:rPh)]/text()",
                                    namespaces=ns,
                                )
                            )
                        elif cell.get("t") == "inlineStr":
                            inline = cell.find(f"{{{SHEET_NS}}}is")
                            if inline is not None and inline.xpath(
                                ".//x:rPh|.//x:phoneticPr", namespaces=ns
                            ):
                                rich_source = inline
                                inline_value = "".join(
                                    inline.xpath(
                                        ".//x:t[not(ancestor::x:rPh)]/text()",
                                        namespaces=ns,
                                    )
                                )
                        if key in changes or shared_value is not None or inline_value is not None:
                            fallback_value = shared_value if shared_value is not None else inline_value
                            _set_cell_value(
                                cell,
                                changes.get(key, fallback_value),
                                rich_source,
                            )
                            pending_changes.discard(key)
                            changed = True
                    for element in root.xpath(
                        ".//x:hyperlinks|.//x:legacyDrawing|.//x:legacyDrawingHF",
                        namespaces=ns,
                    ):
                        element.getparent().remove(element)
                        changed = True
                    for element in root.xpath(
                        ".//x:oddHeader|.//x:oddFooter|.//x:evenHeader|.//x:evenFooter|.//x:firstHeader|.//x:firstFooter",
                        namespaces=ns,
                    ):
                        if element.text:
                            element.text = None
                            changed = True
                    for validation in root.xpath(".//x:dataValidation", namespaces=ns):
                        for attribute in ("prompt", "promptTitle", "error", "errorTitle"):
                            if attribute in validation.attrib:
                                validation.attrib.pop(attribute)
                                changed = True
                elif info.filename == "xl/workbook.xml":
                    ns = {"x": SHEET_NS}
                    for element in root.xpath(
                        ".//x:definedNames|.//x:externalReferences", namespaces=ns
                    ):
                        element.getparent().remove(element)
                        changed = True
                elif info.filename.endswith(".rels"):
                    for relationship in list(root):
                        rel_type = relationship.get("Type", "")
                        target_mode = relationship.get("TargetMode", "")
                        if target_mode == "External" or rel_type.endswith(
                            ("/comments", "/vmlDrawing", "/externalLink", "/sharedStrings")
                        ):
                            root.remove(relationship)
                            changed = True
                elif info.filename == "docProps/core.xml":
                    for element in list(root):
                        local_name = etree.QName(element).localname
                        if local_name in {"created", "modified"}:
                            # Empty xsi:type="dcterms:W3CDTF" values make Excel
                            # reject the workbook, so remove typed dates entirely.
                            root.remove(element)
                            changed = True
                        elif element.text:
                            element.text = None
                            changed = True
                elif info.filename == "[Content_Types].xml":
                    for element in list(root):
                        part = element.get("PartName", "").lstrip("/")
                        if part in removed or part.startswith(removed_prefixes):
                            root.remove(element)
                            changed = True
                if changed:
                    payload = etree.tostring(
                        root, xml_declaration=True, encoding="UTF-8", standalone=True
                    )
                outgoing.writestr(info, payload)
            if pending_changes:
                raise ValueError("Не все XLSX-ячейки были записаны в выходной пакет")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
