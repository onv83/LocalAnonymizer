from __future__ import annotations

import base64
import difflib
import hashlib
from io import BytesIO
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from lxml import etree

from .documents import (
    DocumentResult,
    _preflight_docx_package,
    _restore_text,
    _source_archive_is_reversible,
    _unknown_markers,
)
from .engine import Anonymizer, warnings_require_review


ODT_MIMETYPE = "application/vnd.oasis.opendocument.text"
OFFICE_NS = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
META_NS = "urn:oasis:names:tc:opendocument:xmlns:meta:1.0"
XLINK_NS = "http://www.w3.org/1999/xlink"
MANIFEST_NS = "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
_ARTIFACT_FIELD = "LocalAnonymizerArtifact"
# Keep structural-space expansion bounded: exact diffing is quadratic for long repeated runs.
_MAX_EXPANDED_SPACES = 4_096
_MAX_TAB_REFERENCE = 4_096
_NS = {
    "office": OFFICE_NS,
    "text": TEXT_NS,
    "meta": META_NS,
    "xlink": XLINK_NS,
    "manifest": MANIFEST_NS,
}


def _parser() -> etree.XMLParser:
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, recover=False)


def _structural_space_count(element) -> int:
    raw_count = element.get(f"{{{TEXT_NS}}}c", "1")
    if re.fullmatch(r"[0-9]+", raw_count) is None:
        raise ValueError("ODT содержит некорректное число пробелов")
    count = int(raw_count)
    if count < 1 or count > _MAX_EXPANDED_SPACES:
        raise ValueError("ODT содержит некорректное число пробелов")
    return count


def _validate_structural_whitespace(element) -> None:
    qname = etree.QName(element)
    allowed_attributes = {
        "s": {f"{{{TEXT_NS}}}c"},
        "tab": {f"{{{TEXT_NS}}}tab-ref"},
        "line-break": set(),
    }[qname.localname]
    unexpected = set(element.attrib) - allowed_attributes
    if unexpected:
        raise ValueError("ODT содержит неподдерживаемый атрибут структурного пробела")

    if qname.localname == "tab":
        raw_reference = element.get(f"{{{TEXT_NS}}}tab-ref")
        if raw_reference is not None and (
            re.fullmatch(r"[1-9][0-9]*", raw_reference) is None
            or int(raw_reference) > _MAX_TAB_REFERENCE
        ):
            raise ValueError("ODT содержит некорректную ссылку табуляции")


def _preflight_odt_package(path: Path) -> None:
    try:
        _preflight_docx_package(path)
    except ValueError as exc:
        raise ValueError(str(exc).replace("DOCX", "ODT")) from exc
    with ZipFile(path) as package:
        infos = package.infolist()
        names = [info.filename for info in infos]
        normalized_names = [unicodedata.normalize("NFC", name).casefold() for name in names]
        if len(normalized_names) != len(set(normalized_names)):
            raise ValueError("ODT содержит повторяющиеся ZIP-части")
        required = {"mimetype", "content.xml", "styles.xml", "meta.xml", "META-INF/manifest.xml"}
        missing = sorted(required.difference(names))
        if missing:
            raise ValueError(f"ODT не содержит обязательные части: {', '.join(missing)}")
        first = infos[0]
        if first.filename != "mimetype" or first.compress_type != ZIP_STORED:
            raise ValueError("ODT должен начинаться с несжатой части mimetype")
        try:
            mimetype = package.read("mimetype").decode("ascii")
        except UnicodeDecodeError as exc:
            raise ValueError("Некорректный mimetype ODT") from exc
        if mimetype != ODT_MIMETYPE:
            raise ValueError("Файл не является документом ODT")
        blocked = [
            name
            for name in names
            if not name.endswith("/")
            and (
                name.casefold().startswith(("basic/", "scripts/", "object ", "objectreplacements/"))
                or name.casefold().endswith((".class", ".jar", ".js", ".py"))
            )
        ]
        if blocked:
            raise ValueError(
                "ODT содержит активное или встроенное содержимое: " + ", ".join(blocked)
            )
        media = [
            name
            for name in names
            if not name.endswith("/") and name.startswith(("Pictures/", "Thumbnails/"))
        ]
        if media:
            raise ValueError(
                "ODT с графикой пока не поддерживается безопасно: " + ", ".join(media)
            )
        for info in infos:
            unix_mode = (info.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                raise ValueError(f"ODT содержит символическую ссылку: {info.filename}")
        unexpected_directories = [
            name for name in names if name.endswith("/") and name != "META-INF/"
        ]
        if unexpected_directories:
            raise ValueError(
                "ODT содержит неподдерживаемые каталоги: " + ", ".join(unexpected_directories)
            )
        allowed_files = {
            "mimetype",
            "content.xml",
            "styles.xml",
            "meta.xml",
            "settings.xml",
            "META-INF/manifest.xml",
        }
        unknown = [name for name in names if not name.endswith("/") and name not in allowed_files]
        if unknown:
            raise ValueError("ODT содержит неподдерживаемые части: " + ", ".join(unknown))

        manifest = etree.fromstring(package.read("META-INF/manifest.xml"), parser=_parser())
        if manifest.xpath(".//manifest:encryption-data", namespaces=_NS):
            raise ValueError("Зашифрованные части ODT не поддерживаются")
        declared: list[str] = []
        for entry in manifest.xpath(".//manifest:file-entry", namespaces=_NS):
            value = entry.get(f"{{{MANIFEST_NS}}}full-path")
            if not value:
                raise ValueError("Манифест ODT содержит пустой путь")
            declared.append(value)
        folded_declared = [unicodedata.normalize("NFC", value).casefold() for value in declared]
        if len(folded_declared) != len(set(folded_declared)):
            raise ValueError("Манифест ODT содержит повторяющиеся пути")
        declared_files = {value for value in declared if value != "/" and not value.endswith("/")}
        actual_files = {
            name for name in names
            if name not in {"mimetype", "META-INF/manifest.xml"} and not name.endswith("/")
        }
        if declared_files != actual_files:
            raise ValueError("Манифест ODT не соответствует содержимому пакета")

        for name in ("content.xml", "styles.xml", "meta.xml", "settings.xml"):
            if name not in names:
                continue
            root = etree.fromstring(package.read(name), parser=_parser())
            expanded_spaces = 0
            for element in root.iter():
                qname = etree.QName(element)
                local = qname.localname.casefold()
                if qname.namespace == TEXT_NS and local in {"s", "tab", "line-break"}:
                    _validate_structural_whitespace(element)
                    if element.text or len(element):
                        raise ValueError("ODT содержит непустой структурный пробел")
                if qname.namespace == TEXT_NS and local == "s":
                    count = _structural_space_count(element)
                    expanded_spaces += count
                    if expanded_spaces > _MAX_EXPANDED_SPACES:
                        raise ValueError("ODT содержит некорректное число пробелов")
                if local in {
                    "scripts", "event-listeners", "event-listener", "execute-macro",
                    "tracked-changes", "forms", "form", "binary-data",
                    "object", "object-ole", "dde-links", "dde-link",
                }:
                    raise ValueError(f"ODT содержит неподдерживаемую активную структуру: {name}")
                href = element.get(f"{{{XLINK_NS}}}href")
                if href:
                    value = href.strip()
                    parsed = urlsplit(value)
                    if (
                        parsed.scheme or parsed.netloc or value.startswith(("/", "\\"))
                        or re.match(r"^[A-Za-z]:", value)
                    ):
                        if not (qname.namespace == TEXT_NS and qname.localname == "a"):
                            raise ValueError(f"ODT содержит внешние ссылки: {name}")


def _validate_identifiers(root, engine: Anonymizer, checked: set[str]) -> None:
    # Names form a cross-part reference graph. Changing only a definition or a
    # consumer silently breaks formatting; reject sensitive names before writing.
    # Match by local name so table/draw/list styles and extension consumers are
    # checked too, not just style:style and text:p.
    for element in root.iter():
        for key, value in element.attrib.items():
            local = etree.QName(key).localname
            if not (local == "name" or local.endswith(("-name", "-names"))):
                continue
            if value in checked:
                continue
            result = engine.anonymize(value)
            if result.text != value or warnings_require_review(result.warnings):
                # Never echo the sensitive identifier in errors/UI/logs.
                raise ValueError("ODT содержит чувствительный идентификатор стиля или ссылки")
            checked.add(value)


def _sanitize_external_text_links(root) -> bool:
    changed = False
    href_key = f"{{{XLINK_NS}}}href"
    for element in root.iter(f"{{{TEXT_NS}}}a"):
        href = element.get(href_key)
        if not href:
            continue
        value = href.strip()
        parsed = urlsplit(value)
        if (
            parsed.scheme or parsed.netloc or value.startswith(("/", "\\"))
            or re.match(r"^[A-Za-z]:", value)
        ):
            element.set(href_key, "#")
            changed = True
    return changed


def _remove_annotations(root) -> bool:
    changed = False
    annotation_tags = {
        f"{{{OFFICE_NS}}}annotation",
        f"{{{OFFICE_NS}}}annotation-end",
        f"{{{TEXT_NS}}}bookmark",
        f"{{{TEXT_NS}}}bookmark-start",
        f"{{{TEXT_NS}}}bookmark-end",
        f"{{{TEXT_NS}}}reference-mark",
        f"{{{TEXT_NS}}}reference-mark-start",
        f"{{{TEXT_NS}}}reference-mark-end",
    }
    for element in list(root.iter()):
        if element.tag not in annotation_tags:
            continue
        parent = element.getparent()
        if parent is None:
            continue
        if element.tail:
            previous = element.getprevious()
            if previous is None:
                parent.text = (parent.text or "") + element.tail
            else:
                previous.tail = (previous.tail or "") + element.tail
        parent.remove(element)
        changed = True
    return changed


@dataclass
class _TextSlot:
    element: object
    tail: bool = False
    structural_text: str | None = None

    @property
    def text(self) -> str | None:
        if self.structural_text is not None:
            return self.structural_text
        return self.element.tail if self.tail else self.element.text

    @text.setter
    def text(self, value: str | None) -> None:
        if self.structural_text is not None:
            if value == self.structural_text:
                return
            self.element.tag = f"{{{TEXT_NS}}}span"
            self.element.attrib.clear()
            self.element.text = value or None
            self.structural_text = None
            return
        if self.tail:
            self.element.tail = value
        else:
            self.element.text = value


def _text_slots(block) -> list[_TextSlot]:
    slots: list[_TextSlot] = []

    def visit(element) -> None:
        qname = etree.QName(element)
        if qname.namespace == OFFICE_NS and qname.localname in {"annotation", "annotation-end"}:
            return
        structural = None
        if qname.namespace == TEXT_NS:
            if qname.localname == "s":
                structural = " " * _structural_space_count(element)
            elif qname.localname == "tab":
                structural = "\t"
            elif qname.localname == "line-break":
                structural = "\n"
        if structural is not None:
            slots.append(_TextSlot(element, structural_text=structural))
        elif element.text:
            slots.append(_TextSlot(element))
        for child in element:
            visit(child)
            if child.tail:
                slots.append(_TextSlot(child, tail=True))

    visit(block)
    return slots


def _replace_slots(slots: list[_TextSlot], new_text: str) -> None:
    if not slots:
        return
    old = "".join(slot.text or "" for slot in slots)
    if old == new_text:
        return
    offsets: list[tuple[int, int, _TextSlot]] = []
    position = 0
    for slot in slots:
        value = slot.text or ""
        offsets.append((position, position + len(value), slot))
        position += len(value)
    operations = [
        operation
        for operation in difflib.SequenceMatcher(None, old, new_text, autojunk=False).get_opcodes()
        if operation[0] != "equal"
    ]
    for _, a1, a2, b1, b2 in reversed(operations):
        replacement = new_text[b1:b2]
        if a1 == a2:
            target = next((slot for start, end, slot in offsets if start <= a1 <= end), slots[-1])
            start = next(start for start, _, slot in offsets if slot is target)
            local = a1 - start
            value = target.text or ""
            target.text = value[:local] + replacement + value[local:]
            continue
        touched = [(start, end, slot) for start, end, slot in offsets if start < a2 and end > a1]
        if not touched:
            raise RuntimeError("Ошибка замены текста ODT")
        first_start, _, first = touched[0]
        last_start, _, last = touched[-1]
        first_value, last_value = first.text or "", last.text or ""
        prefix = first_value[: max(0, a1 - first_start)]
        suffix = last_value[max(0, a2 - last_start) :]
        if first is last:
            first.text = prefix + replacement + suffix
        else:
            first.text = prefix + replacement
            for _, _, slot in touched[1:-1]:
                slot.text = ""
            last.text = suffix


def _rewrite_package(source: Path, target: Path, updates: dict[str, bytes]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target.stem}-", suffix=target.suffix, dir=target.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with ZipFile(source) as package, ZipFile(temporary, "w") as output:
            for info in package.infolist():
                output.writestr(info, updates.get(info.filename, package.read(info.filename)))
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _content_blocks(root) -> list[object]:
    return list(
        root.xpath(
            ".//text:p[not(ancestor::office:annotation)] | "
            ".//text:h[not(ancestor::office:annotation)]",
            namespaces=_NS,
        )
    )


def extract_odt_text(path: str | Path) -> str:
    path = Path(path)
    _preflight_odt_package(path)
    with ZipFile(path) as package:
        root = etree.fromstring(package.read("content.xml"), parser=_parser())
    return "\n".join(
        "".join(slot.text or "" for slot in _text_slots(block))
        for block in _content_blocks(root)
    )


def _sanitized_meta(payload: bytes | None) -> bytes:
    # Rebuild rather than blank text: names, attributes and namespaces can leak too.
    root = etree.Element(f"{{{OFFICE_NS}}}document-meta", nsmap={"office": OFFICE_NS})
    root.set(f"{{{OFFICE_NS}}}version", "1.3")
    etree.SubElement(root, f"{{{OFFICE_NS}}}meta")
    return etree.tostring(root, encoding="UTF-8", xml_declaration=True)


def read_odt_artifact_stamp(path: str | Path) -> str | None:
    path = Path(path)
    _preflight_odt_package(path)
    with ZipFile(path) as package:
        if "meta.xml" not in package.namelist():
            return None
        root = etree.fromstring(package.read("meta.xml"), parser=_parser())
    nodes = root.xpath(
        ".//meta:user-defined[@meta:name=$name]", namespaces=_NS, name=_ARTIFACT_FIELD
    )
    if len(nodes) > 1:
        raise ValueError("ODT содержит повторяющиеся служебные идентификаторы")
    return nodes[0].text if nodes else None


def write_odt_artifact_stamp(path: str | Path, value: str) -> None:
    path = Path(path)
    _preflight_odt_package(path)
    with ZipFile(path) as package:
        payload = package.read("meta.xml") if "meta.xml" in package.namelist() else None
    if payload:
        root = etree.fromstring(payload, parser=_parser())
    else:
        root = etree.Element(f"{{{OFFICE_NS}}}document-meta", nsmap={"office": OFFICE_NS, "meta": META_NS})
        root.set(f"{{{OFFICE_NS}}}version", "1.3")
    metadata = root.find(f"{{{OFFICE_NS}}}meta")
    if metadata is None:
        metadata = etree.SubElement(root, f"{{{OFFICE_NS}}}meta")
    existing = metadata.xpath(
        "./meta:user-defined[@meta:name=$name]", namespaces=_NS, name=_ARTIFACT_FIELD
    )
    if len(existing) > 1:
        raise ValueError("ODT содержит повторяющиеся служебные идентификаторы")
    for existing_node in existing:
        metadata.remove(existing_node)
    node = etree.SubElement(metadata, f"{{{META_NS}}}user-defined")
    node.set(f"{{{META_NS}}}name", _ARTIFACT_FIELD)
    node.set(f"{{{META_NS}}}value-type", "string")
    node.text = value
    updated = etree.tostring(root, encoding="UTF-8", xml_declaration=True)
    _rewrite_package(path, path, {"meta.xml": updated})


def clear_odt_artifact_stamp(path: str | Path) -> None:
    path = Path(path)
    _preflight_odt_package(path)
    with ZipFile(path) as package:
        root = etree.fromstring(package.read("meta.xml"), parser=_parser())
    metadata = root.find(f"{{{OFFICE_NS}}}meta")
    if metadata is None:
        return
    existing = metadata.xpath(
        "./meta:user-defined[@meta:name=$name]", namespaces=_NS, name=_ARTIFACT_FIELD
    )
    if len(existing) > 1:
        raise ValueError("ODT содержит повторяющиеся служебные идентификаторы")
    if not existing:
        return
    metadata.remove(existing[0])
    _rewrite_package(
        path,
        path,
        {"meta.xml": etree.tostring(root, encoding="UTF-8", xml_declaration=True)},
    )


def _exact_archive(source_bytes: bytes, anonymized_bytes: bytes) -> dict:
    return {
        "schema": 1,
        "kind": "odt-exact",
        "exact_source_b64": base64.b64encode(source_bytes).decode("ascii"),
        "exact_source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "exact_anonymized_sha256": hashlib.sha256(anonymized_bytes).hexdigest(),
    }


def _restore_exact(
    source: Path, output: Path, mapping: dict[str, str], package_archive: dict | None
) -> bool:
    if not isinstance(package_archive, dict) or package_archive.get("kind") != "odt-exact":
        return False
    if hashlib.sha256(source.read_bytes()).hexdigest() != package_archive.get("exact_anonymized_sha256"):
        return False
    try:
        original = base64.b64decode(package_archive["exact_source_b64"], validate=True)
    except Exception as exc:
        raise ValueError("Повреждён точный снимок исходного ODT") from exc
    if hashlib.sha256(original).hexdigest() != package_archive.get("exact_source_sha256"):
        raise ValueError("Повреждён точный снимок исходного ODT")
    try:
        with ZipFile(BytesIO(original)) as package:
            original_text = "\n".join(
                "".join(slot.text or "" for slot in _text_slots(block))
                for name in ("content.xml", "styles.xml")
                for block in _content_blocks(
                    etree.fromstring(package.read(name), parser=_parser())
                )
            )
    except Exception as exc:
        raise ValueError("Повреждён точный снимок исходного ODT") from exc
    if any(value not in original_text for value in mapping.values()):
        raise ValueError("Точный снимок ODT не соответствует таблице восстановления")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{output.stem}-", suffix=output.suffix, dir=output.parent
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(original)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, output)
    finally:
        Path(temporary_name).unlink(missing_ok=True)
    return True


class OdtProcessor:
    def __init__(self, engine: Anonymizer | None = None):
        self.engine = engine or Anonymizer()

    def anonymize(self, source: str | Path, output: str | Path) -> DocumentResult:
        source, output = Path(source), Path(output)
        _preflight_odt_package(source)
        source_bytes = source.read_bytes()
        with ZipFile(source) as package:
            payloads = {
                name: package.read(name) for name in ("content.xml", "styles.xml", "meta.xml")
            }
        roots = {
            name: etree.fromstring(payloads[name], parser=_parser())
            for name in ("content.xml", "styles.xml")
        }
        changed_parts = {
            name
            for name, root in roots.items()
            if _sanitize_external_text_links(root) | _remove_annotations(root)
        }
        checked_identifiers: set[str] = set()
        for root in roots.values():
            _validate_identifiers(root, self.engine, checked_identifiers)
        records: list[tuple[str, object, list[_TextSlot], str]] = []
        for name, root in roots.items():
            for block in _content_blocks(root):
                group = _text_slots(block)
                records.append((name, root, group, "".join(slot.text or "" for slot in group)))
        texts = [text for _, _, _, text in records]
        separator = "\ufdd0"
        if any(separator in text for text in texts):
            raise RuntimeError("Ошибка разбиения ODT: коллизия разделителя")
        result = self.engine.anonymize(separator.join(texts))
        replacements = result.text.split(separator) if texts else []
        if len(replacements) != len(texts):
            raise RuntimeError("Ошибка разбиения ODT: неверное число фрагментов")
        for (name, _, group, original), replacement in zip(records, replacements):
            if replacement != original:
                _replace_slots(group, replacement)
                changed_parts.add(name)
        updates = {"meta.xml": _sanitized_meta(payloads["meta.xml"])}
        with ZipFile(source) as package:
            if "settings.xml" in package.namelist():
                # Application/view settings are not document formatting.
                settings = etree.Element(
                    f"{{{OFFICE_NS}}}document-settings", nsmap={"office": OFFICE_NS}
                )
                settings.set(f"{{{OFFICE_NS}}}version", "1.3")
                etree.SubElement(settings, f"{{{OFFICE_NS}}}settings")
                updates["settings.xml"] = etree.tostring(
                    settings, encoding="UTF-8", xml_declaration=True
                )
        for name in changed_parts:
            updates[name] = etree.tostring(
                roots[name], encoding="UTF-8", xml_declaration=True
            )
        _rewrite_package(source, output, updates)
        if source.read_bytes() != source_bytes:
            raise RuntimeError("Исходный файл был изменён")
        warnings = list(result.warnings)
        archive = (
            _exact_archive(source_bytes, output.read_bytes())
            if (not any(part.get("secret") for part in result.parts)
                and _source_archive_is_reversible(source_bytes, self.engine))
            else None
        )
        return DocumentResult(
            result.mapping,
            result.candidates,
            warnings,
            not warnings_require_review(warnings),
            result.total,
            result.hint_count,
            archive,
        )

    def restore(
        self,
        source: str | Path,
        output: str | Path,
        mapping: dict[str, str],
        *,
        package_archive: dict | None = None,
    ) -> list[str]:
        source, output = Path(source), Path(output)
        _preflight_odt_package(source)
        if _restore_exact(source, output, mapping, package_archive):
            return []
        with ZipFile(source) as package:
            roots = {
                name: etree.fromstring(package.read(name), parser=_parser())
                for name in ("content.xml", "styles.xml")
            }
        unknown: set[str] = set()
        changed_parts: set[str] = set()
        for name, root in roots.items():
            for block in _content_blocks(root):
                slots = _text_slots(block)
                text = "".join(slot.text or "" for slot in slots)
                unknown.update(_unknown_markers(text, mapping))
                restored = _restore_text(text, mapping)
                if restored != text:
                    _replace_slots(slots, restored)
                    changed_parts.add(name)
        _rewrite_package(
            source,
            output,
            {
                name: etree.tostring(roots[name], encoding="UTF-8", xml_declaration=True)
                for name in changed_parts
            },
        )
        clear_odt_artifact_stamp(output)
        return sorted(unknown)
