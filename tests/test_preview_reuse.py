"""The engine must run once per document action; previews reuse that result.

The UI applies settings to a file with one action that triggers, in order:
anonymize_document -> anonymize_text (text preview) ->
start_anonymized_document_preview (formatted preview). These tests pin the
single engine pass and prove the reused preview output is byte-identical to a
freshly computed one.
"""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from docx import Document

from local_anonymizer.app import AppApi
from local_anonymizer.engine import Anonymizer


OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
META = "urn:oasis:names:tc:opendocument:xmlns:meta:1.0"
MANIFEST = "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
STYLE = "urn:oasis:names:tc:opendocument:xmlns:style:1.0"


def _count_engine_passes(monkeypatch) -> list:
    """Count every Anonymizer.anonymize pass, whatever pipeline invokes it."""
    counter = {"passes": 0}
    original = Anonymizer.anonymize

    def counting(self, source):
        counter["passes"] += 1
        return original(self, source)

    monkeypatch.setattr(Anonymizer, "anonymize", counting)
    return counter


def _synthetic_docx(path: Path) -> None:
    document = Document()
    document.add_paragraph("Иванов Сергей Петрович, test@example.ru")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "АС «Паутина»"
    table.cell(0, 1).text = "+7 495 123-45-67"
    table.cell(1, 0).text = "login admin_db; пароль: Secret123!"
    table.cell(1, 1).text = "ИНН 7707083893"
    for index in range(3):
        document.add_paragraph(
            f"Контакт {index}: petrov{index}@example.ru, 192.168.1.{10 + index}"
        )
    document.save(path)


def _write_odt(path: Path) -> None:
    content = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="{OFFICE}" xmlns:text="{TEXT}" office:version="1.3">
  <office:body><office:text>
    <text:p text:style-name="Body">Иванов Сергей Петрович, test@example.ru</text:p>
  </office:text></office:body>
</office:document-content>'''.encode()
    styles = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="{OFFICE}" xmlns:text="{TEXT}" xmlns:style="{STYLE}" office:version="1.3">
  <office:styles/>
</office:document-styles>'''.encode()
    meta = f'''<?xml version="1.0" encoding="UTF-8"?>
<office:document-meta xmlns:office="{OFFICE}" xmlns:meta="{META}" office:version="1.3">
  <office:meta><meta:generator>LocalAnonymizer tests</meta:generator></office:meta>
</office:document-meta>'''.encode()
    manifest = f'''<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="{MANIFEST}" manifest:version="1.3">
  <manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>
  <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
  <manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>
  <manifest:file-entry manifest:full-path="meta.xml" manifest:media-type="text/xml"/>
</manifest:manifest>'''.encode()
    with ZipFile(path, "w") as package:
        package.writestr("mimetype", "application/vnd.oasis.opendocument.text",
                         compress_type=ZIP_STORED)
        package.writestr("content.xml", content, compress_type=ZIP_DEFLATED)
        package.writestr("styles.xml", styles, compress_type=ZIP_DEFLATED)
        package.writestr("meta.xml", meta, compress_type=ZIP_DEFLATED)
        package.writestr("META-INF/manifest.xml", manifest, compress_type=ZIP_DEFLATED)


def _read_preview_chunks(api: AppApi, manifest: dict, field: str) -> str:
    value = ""
    offset = 0
    while offset < manifest[f"{field}_length"]:
        chunk = api.read_document_preview_chunk(manifest["token"], field, offset)
        value += chunk["chunk"]
        offset = chunk["next_offset"]
    api.finish_document_preview(manifest["token"])
    return value


def test_docx_document_action_runs_engine_once(tmp_path, monkeypatch):
    source = tmp_path / "report.docx"
    _synthetic_docx(source)
    api = AppApi(root=tmp_path / "app")
    document_id = api.import_paths([str(source)])["ids"][0]

    # The UI loads the preview text, then the debounced anonymize_text runs
    # before the button is clicked.
    manifest = api.start_document_preview(document_id)
    preview_text = _read_preview_chunks(api, manifest, "text")

    counter = _count_engine_passes(monkeypatch)
    api.anonymize_text(preview_text)
    assert counter["passes"] == 1
    counter["passes"] = 0

    # One document action: apply settings, refresh the text preview, refresh
    # the formatted preview. Exactly one engine pass in total.
    report = api.anonymize_document(document_id)
    bridge = api.anonymize_text(preview_text)
    rich_manifest = api.start_anonymized_document_preview(document_id)
    rich_html = _read_preview_chunks(api, rich_manifest, "rich_html")

    assert counter["passes"] == 1
    assert set(report) == {"replacement_count", "legend_total", "candidate_count",
                           "candidates", "warnings", "ready", "status", "mapping"}
    assert report["replacement_count"] > 0
    assert "[ФИО-1]" in bridge["text"] and "Иванов" not in bridge["text"]
    assert "[ФИО-1]" in rich_html and "Иванов" not in rich_html
    assert rich_manifest["replacement_count"] == report["replacement_count"]


def test_docx_cached_anonymized_preview_matches_fresh_engine_pass(tmp_path):
    source = tmp_path / "report.docx"
    _synthetic_docx(source)
    api = AppApi(root=tmp_path / "app")
    document_id = api.import_paths([str(source)])["ids"][0]
    api.anonymize_document(document_id)
    cached = api.preview_anonymized_document(document_id)

    fresh = AppApi(root=tmp_path / "app-fresh")
    fresh_id = fresh.import_paths([str(source)])["ids"][0]
    uncached = fresh.preview_anonymized_document(fresh_id)

    assert cached == uncached
    assert "[ФИО-1]" in cached["rich_html"]
    assert "Иванов" not in cached["rich_html"]
    assert cached["replacement_count"] == uncached["replacement_count"]


def test_odt_cached_anonymized_preview_matches_fresh_engine_pass(tmp_path):
    source = tmp_path / "note.odt"
    _write_odt(source)
    api = AppApi(root=tmp_path / "app")
    document_id = api.import_paths([str(source)])["ids"][0]
    api.anonymize_document(document_id)
    cached = api.preview_anonymized_document(document_id)

    fresh = AppApi(root=tmp_path / "app-fresh")
    fresh_id = fresh.import_paths([str(source)])["ids"][0]
    uncached = fresh.preview_anonymized_document(fresh_id)

    assert cached == uncached
    assert "[ФИО-1]" in cached["rich_html"]
    assert "Иванов" not in cached["rich_html"]


def test_text_document_bridge_reuses_the_document_pass(tmp_path, monkeypatch):
    source = tmp_path / "note.txt"
    source.write_text(
        "Иванов Сергей Петрович, test@example.ru\nАС «Паутина», ИНН 7707083893",
        encoding="utf-8",
    )
    api = AppApi(root=tmp_path / "app")
    document_id = api.import_paths([str(source)])["ids"][0]

    # The UI preview loads exactly the file text through the chunk bridge.
    manifest = api.start_document_preview(document_id)
    preview_text = _read_preview_chunks(api, manifest, "text")

    counter = _count_engine_passes(monkeypatch)
    api.anonymize_document(document_id)
    assert counter["passes"] == 1

    # The bridge call after the action reuses the pass above instead of
    # re-running the engine over the same file text.
    first = api.anonymize_text(preview_text)
    second = api.anonymize_text(preview_text)
    assert counter["passes"] == 1
    assert first == second and first is second
    assert set(first) == {"text", "mapping", "candidates", "parts", "legend",
                          "counts", "total", "legend_total", "hintCount", "warnings"}
    assert "[ФИО-1]" in first["text"] and "Иванов" not in first["text"]
    assert first["parts"] and first["legend"]


def test_anonymize_text_repeats_return_the_same_result_object(tmp_path):
    api = AppApi(root=tmp_path / "app")
    text = "Иванов Сергей Петрович, test@example.ru"
    first = api.anonymize_text(text)
    second = api.anonymize_text(text)
    assert second is first
    changed = api.anonymize_text(text, disabled=["ПОЧТА"])
    assert changed is not first
    assert "[ПОЧТА-1]" in first["text"]
    assert "test@example.ru" in changed["text"]


def test_anonymized_preview_recomputes_when_settings_differ(tmp_path):
    source = tmp_path / "report.docx"
    _synthetic_docx(source)
    api = AppApi(root=tmp_path / "app")
    document_id = api.import_paths([str(source)])["ids"][0]
    api.anonymize_document(document_id)
    cached = api.preview_anonymized_document(document_id)

    whitelisted = api.preview_anonymized_document(document_id, whitelist="Иванов")
    assert "[ФИО-1]" in cached["rich_html"]
    assert "Иванов" in whitelisted["rich_html"]

    fresh = AppApi(root=tmp_path / "app-fresh")
    fresh_id = fresh.import_paths([str(source)])["ids"][0]
    assert whitelisted == fresh.preview_anonymized_document(fresh_id, whitelist="Иванов")


def test_service_exposes_the_computed_engine_result(tmp_path):
    source = tmp_path / "report.docx"
    _synthetic_docx(source)
    api = AppApi(root=tmp_path / "app")
    document_id = api.import_paths([str(source)])["ids"][0]
    api.anonymize_document(document_id)

    run = api.service.last_anonymized_run(document_id)
    assert run is not None
    engine_result = run["engine_result"]
    assert engine_result is not None
    assert engine_result.text and engine_result.mapping
    assert isinstance(engine_result.parts, list) and engine_result.parts
    assert isinstance(engine_result.legend, list) and engine_result.legend
    assert Path(run["output"]).is_file()
    assert run["report"]["replacement_count"] > 0
