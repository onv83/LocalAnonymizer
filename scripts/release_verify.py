from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from local_anonymizer.service import AnonymizerService


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ReleaseVerificationError(RuntimeError):
    """Raised when a release invariant is not satisfied."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseVerificationError(message)


def build_acceptance_source(source: Path, sample_path: Path, image_path: Path) -> bytes:
    """Build the synthetic DOCX used by release verification and screenshots."""
    image_bytes = image_path.read_bytes()
    document = Document()
    document.add_heading("Синтетический приёмочный документ", level=1)
    document.add_paragraph(
        "Рисунок ниже содержит только вымышленные тестовые обозначения. "
        "При обезличивании он должен замениться маркером категории «СХЕМА», "
        "а при локальном восстановлении вернуться без изменений."
    )
    image_paragraph = document.add_paragraph()
    image_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    image_paragraph.add_run().add_picture(str(image_path), width=Inches(6.4))
    document.add_paragraph(sample_path.read_text(encoding="utf-8"))
    document.save(source)
    return image_bytes


def main() -> int:
    root = ROOT / "artifacts" / "smoke"
    shutil.rmtree(root, ignore_errors=True); root.mkdir(parents=True)
    source = root / "acceptance-source.docx"
    image_bytes = build_acceptance_source(
        source,
        ROOT / "acceptance_sample.txt",
        ROOT / "docs" / "images" / "acceptance-diagram.png",
    )
    before = sha256(source)
    service = AnonymizerService(root / "appdata")
    document_id = service.import_file(source)
    report = service.anonymize(document_id)
    anonymized = Path(report["output_path"])
    text = "\n".join(p.text for p in Document(anonymized).paragraphs)
    required = ["[СХЕМА-1]", "[ФИО-1]", "[ОРГАНИЗАЦИЯ-1]", "[ПОЧТА-1]", "[ТЕЛЕФОН-1]", "[ТЕЛЕФОН-2]", "[IP-1]", "[IP-2]", "[уязвимость]", "(удалено)"]
    public = ["1.7.5.16", "порт 8080"]
    abbreviations = ["SLA", "НДС"]
    require(
        all(x in text for x in required) and all(x in text for x in public),
        "Anonymized acceptance document is missing required markers or public values",
    )
    require(
        "[СОКРАЩЕНИЯ-" in text and all(x not in text for x in abbreviations),
        "Abbreviation redaction did not satisfy the acceptance contract",
    )
    with ZipFile(anonymized) as archive:
        require(
            not any(name.startswith("word/media/") for name in archive.namelist()),
            "Anonymized DOCX still contains embedded media",
        )
        rels = b"".join(archive.read(n) for n in archive.namelist() if n.endswith(".rels"))
        require(
            b'TargetMode="External"' not in rels,
            "Anonymized DOCX contains an external relationship",
        )

    exact_restored_report = service.restore(
        document_id,
        anonymized,
        destination=root / "acceptance-restored-exact.docx",
    )
    exact_restored = Path(exact_restored_report["output_path"])
    require(
        exact_restored.read_bytes() == source.read_bytes(),
        "Unedited anonymized DOCX did not restore byte-for-byte to its source",
    )

    edited = root / "acceptance-edited.docx"
    edit = Document(anonymized); edit.add_paragraph("Редактура [ФИО-1] [ФИО-999]"); edit.save(edited)
    restored_report = service.restore(document_id, edited)
    restored = Path(restored_report["output_path"])
    restored_document = Document(restored)
    require(
        "Иванов Сергей Петрович" in "\n".join(p.text for p in restored_document.paragraphs),
        "Known text marker did not restore",
    )
    require(
        len(restored_document.inline_shapes) == 1,
        "Edited DOCX did not restore exactly one embedded graphic",
    )
    with ZipFile(restored) as archive:
        restored_images = [
            archive.read(name)
            for name in archive.namelist()
            if name.startswith("word/media/")
        ]
    require(
        restored_images == [image_bytes],
        "Restored graphic bytes differ from the source graphic",
    )
    require(
        restored_report["unknown_markers"] == ["[ФИО-999]"],
        "Unknown marker reporting differs from the acceptance contract",
    )
    require(sha256(source) == before, "Release verification modified its source DOCX")

    # Real installed Word COM opens emitted files read-only with no link updates.
    import win32com.client
    word = win32com.client.DispatchEx("Word.Application"); word.Visible = False; word.DisplayAlerts = 0; word.AutomationSecurity = 3
    opened = []
    try:
        for path in (anonymized, restored):
            word.Options.UpdateLinksAtOpen = False
            d = word.Documents.Open(str(path), ReadOnly=True, AddToRecentFiles=False)
            opened.append(path.name); d.Close(False)
    finally:
        word.Quit()
    print(json.dumps({"ok": True, "source": str(source), "source_sha256": before,
          "anonymized": str(anonymized), "restored": str(restored),
          "replacement_count": report["replacement_count"], "candidate_count": report["candidate_count"],
          "public_values_preserved": public, "unknown_markers": restored_report["unknown_markers"],
          "graphic_removed": True, "graphic_restored_exactly": True,
          "document_restored_byte_exactly": True,
          "external_relationships": 0, "python_docx_open": True, "word_com_opened": opened}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
