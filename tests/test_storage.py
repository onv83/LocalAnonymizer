import json
import sqlite3
import sys
import threading
from pathlib import Path

import pytest

from local_anonymizer.storage import MappingError, Storage


def test_storage_can_be_used_from_pywebview_bridge_thread(tmp_path):
    """AppApi is constructed on the UI thread but called by a bridge worker."""
    store = Storage(tmp_path)
    errors = []
    results = []

    def bridge_call():
        try:
            results.append(store.list_documents())
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=bridge_call)
    worker.start()
    worker.join()

    assert errors == []
    assert results == [[]]


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI envelope is Windows-only")
def test_dpapi_envelope_is_bound_and_plaintext_never_enters_database(tmp_path):
    store = Storage(tmp_path)
    doc_id = store.import_document(tmp_path / "outside.docx", copy_source=False)
    mapping = {"[ФИО-1]": "СЕКРЕТНЫЙ_ИВАНОВ"}
    store.save_mapping(doc_id, "op-1", mapping)
    assert store.load_mapping(doc_id, "op-1") == mapping
    raw = (tmp_path / "library.db").read_bytes()
    assert "СЕКРЕТНЫЙ_ИВАНОВ".encode("utf-8") not in raw
    with pytest.raises(MappingError):
        store.load_mapping(doc_id, "wrong-op")
    row = store.connection.execute("select envelope from mappings where document_id=?", (doc_id,)).fetchone()
    corrupted = bytearray(row[0]); corrupted[len(corrupted)//2] ^= 1
    store.connection.execute("update mappings set envelope=? where document_id=?", (bytes(corrupted), doc_id)); store.connection.commit()
    with pytest.raises(MappingError):
        store.load_mapping(doc_id, "op-1")


def test_safe_delete_removes_owned_files_but_never_source_or_escape(tmp_path):
    source = tmp_path.parent / "outside.docx"
    source.write_bytes(b"original")
    store = Storage(tmp_path / "app")
    doc_id = store.import_document(source)
    owned = Path(store.get_document(doc_id)["owned_source"])
    assert owned.exists()
    store.connection.execute("update documents set output_path=? where id=?", (str(source), doc_id)); store.connection.commit()
    store.delete_document(doc_id)
    assert source.read_bytes() == b"original"
    assert not owned.exists()


def test_profiles_validate_and_roundtrip_without_executable_content(tmp_path):
    store = Storage(tmp_path)
    store.save_profile("Общий", {"Вымпел": "СИСТЕМА"}, ["Казань"], paranoid=False)
    profile = store.load_profile("Общий")
    assert profile["dictionary"]["Вымпел"] == "СИСТЕМА"
    exported = store.export_profile("Общий")
    imported = store.import_profile(exported.replace('"Общий"', '"Новый"'))
    assert imported == "Новый"
    with pytest.raises(ValueError):
        store.import_profile('{"version":1,"name":"x","dictionary":{"a":"BAD ]"},"whitelist":[]}')


def test_profiles_preserve_new_uncertain_mode_and_accept_legacy_paranoid_only(tmp_path):
    store = Storage(tmp_path)
    store.save_profile("Старый", {}, [], paranoid=True)
    legacy = store.load_profile("Старый")
    assert legacy["paranoid"] is True
    assert "uncertain_mode" not in legacy

    store.save_profile("Новый", {}, [], paranoid=False, uncertain_mode="off")
    current = store.load_profile("Новый")
    assert current["paranoid"] is False
    assert current["uncertain_mode"] == "off"
    exported = store.export_profile("Новый")
    assert store.import_profile(exported.replace('"Новый"', '"Копия"')) == "Копия"
    assert store.load_profile("Копия")["uncertain_mode"] == "off"

    store.save_profile("Нормализованный", {}, [], paranoid=True, uncertain_mode="review")
    normalized = store.load_profile("Нормализованный")
    assert normalized["uncertain_mode"] == "review"
    assert normalized["paranoid"] is False

    with pytest.raises(ValueError):
        store.save_profile("Ошибка", {}, [], uncertain_mode="unexpected")
    with pytest.raises(ValueError):
        store._validate_profile({
            "version": 1, "name": "Ошибка", "dictionary": {}, "whitelist": [],
            "uncertain_mode": {"unexpected": True},
        })
