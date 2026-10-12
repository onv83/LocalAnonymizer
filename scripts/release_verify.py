from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from zipfile import ZipFile

from docx import Document

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from local_anonymizer.service import AnonymizerService


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    root = ROOT / "artifacts" / "smoke"
    shutil.rmtree(root, ignore_errors=True); root.mkdir(parents=True)
    source = root / "acceptance-source.docx"
    doc = Document(); doc.add_paragraph((ROOT / "acceptance_sample.txt").read_text(encoding="utf-8")); doc.save(source)
    before = sha256(source)
    service = AnonymizerService(root / "appdata")
    document_id = service.import_file(source)
    report = service.anonymize(document_id)
    anonymized = Path(report["output_path"])
    text = "\n".join(p.text for p in Document(anonymized).paragraphs)
    required = ["[ФИО-1]", "[ОРГАНИЗАЦИЯ-1]", "[ПОЧТА-1]", "[ТЕЛЕФОН-1]", "[ТЕЛЕФОН-2]", "[IP-1]", "[IP-2]", "[уязвимость]", "(удалено)"]
    public = ["1.7.5.16", "SLA 99,9%", "НДС 20%", "порт 8080"]
    assert all(x in text for x in required) and all(x in text for x in public)
    with ZipFile(anonymized) as archive:
        rels = b"".join(archive.read(n) for n in archive.namelist() if n.endswith(".rels"))
        assert b'TargetMode="External"' not in rels
    edited = root / "acceptance-edited.docx"
    edit = Document(anonymized); edit.add_paragraph("Редактура [ФИО-1] [ФИО-999]"); edit.save(edited)
    restored_report = service.restore(document_id, edited)
    restored = Path(restored_report["output_path"])
    assert "Иванов Сергей Петрович" in "\n".join(p.text for p in Document(restored).paragraphs)
    assert restored_report["unknown_markers"] == ["[ФИО-999]"] and sha256(source) == before

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
          "external_relationships": 0, "python_docx_open": True, "word_com_opened": opened}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
