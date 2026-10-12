import os
import subprocess
import sys
from pathlib import Path

import pytest

from local_anonymizer.platform_services import (
    DataProtectionUnavailable,
    default_clipboard_reader,
    default_data_dir,
    restrict_private_directory,
    restrict_private_file,
)
from local_anonymizer.storage import Storage


class ReversibleTestProtector:
    """Test-only protector proving Storage does not depend on DPAPI."""

    def protect(self, data: bytes, purpose: str) -> bytes:
        return b"TEST\0" + purpose.encode("utf-8") + b"\0" + data[::-1]

    def unprotect(self, envelope: bytes) -> bytes:
        if not envelope.startswith(b"TEST\0"):
            raise ValueError("invalid test envelope")
        return envelope.split(b"\0", 2)[2][::-1]


class UnavailableTestProtector:
    def protect(self, data: bytes, purpose: str) -> bytes:
        raise DataProtectionUnavailable("secure storage unavailable")

    def unprotect(self, envelope: bytes) -> bytes:
        raise DataProtectionUnavailable("secure storage unavailable")


def test_non_windows_modules_import_without_pywin32(tmp_path):
    code = """
import builtins
import os
import sys
sys.platform = 'linux'
os.environ.pop('LOCALAPPDATA', None)
real_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'win32crypt', 'win32com', 'pythoncom', 'win32clipboard'}:
        raise ImportError(f'blocked Windows module: {name}')
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded
import local_anonymizer.storage
import local_anonymizer.service
import local_anonymizer.app
"""
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    source_root = Path(__file__).resolve().parents[1] / "src"
    env["PYTHONPATH"] = os.pathsep.join(
        value for value in (str(source_root), env.get("PYTHONPATH", "")) if value
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("platform_name", "environment", "home", "expected"),
    [
        ("win32", {"LOCALAPPDATA": "C:/Users/Test/AppData/Local"}, "/home/test", Path("C:/Users/Test/AppData/Local/LocalAnonymizer")),
        ("linux", {"XDG_DATA_HOME": "/data"}, "/home/test", Path("/data/local-anonymizer")),
        ("linux", {"XDG_DATA_HOME": "relative"}, "/home/test", Path("/home/test/.local/share/local-anonymizer")),
        ("linux", {}, "/home/test", Path("/home/test/.local/share/local-anonymizer")),
        ("darwin", {}, "/Users/test", Path("/Users/test/Library/Application Support/LocalAnonymizer")),
    ],
)
def test_default_data_dir_is_platform_native(platform_name, environment, home, expected):
    assert default_data_dir(platform_name, environment, Path(home)) == expected


def test_explicit_storage_root_and_protector_work_without_platform_defaults(tmp_path):
    store = Storage(tmp_path, protector=ReversibleTestProtector())
    document_id = store.import_document(tmp_path / "outside.docx", copy_source=False)
    mapping = {"[ФИО-1]": "Иванов Иван"}
    store.save_mapping(document_id, "op-1", mapping)
    assert store.load_mapping(document_id, "op-1") == mapping
    assert "Иванов Иван".encode("utf-8") not in (tmp_path / "library.db").read_bytes()


def test_storage_fails_closed_when_secure_protection_is_unavailable(tmp_path):
    store = Storage(tmp_path, protector=UnavailableTestProtector())
    document_id = store.import_document(tmp_path / "outside.docx", copy_source=False)

    with pytest.raises(DataProtectionUnavailable, match="secure storage unavailable"):
        store.save_mapping(document_id, "op-1", {"[ФИО-1]": "Иванов Иван"})

    assert store.connection.execute("select count(*) from mappings").fetchone()[0] == 0
    assert "Иванов Иван".encode("utf-8") not in (tmp_path / "library.db").read_bytes()


def test_service_uses_injected_legacy_document_converter(tmp_path):
    from local_anonymizer.service import AnonymizerService

    calls = []

    class FalseyConverter:
        def __bool__(self) -> bool:
            return False

        def __call__(self, source: Path, destination: Path) -> Path:
            calls.append((source, destination))
            destination.write_bytes(b"converted docx")
            return destination

    source = tmp_path / "legacy.doc"
    source.write_bytes(b"legacy doc")
    storage = Storage(tmp_path / "app", protector=ReversibleTestProtector())
    service = AnonymizerService(
        storage=storage,
        legacy_document_converter=FalseyConverter(),
    )

    document_id = service.import_file(source)
    row = storage.get_document(document_id)

    assert len(calls) == 1
    assert calls[0][0].suffix == ".doc"
    assert calls[0][1].suffix == ".docx"
    assert Path(row["owned_source"]).read_bytes() == b"converted docx"
    assert row["status"] == "Преобразован из DOC"
    assert not calls[0][0].exists()


def test_app_api_uses_injected_clipboard_reader(tmp_path):
    from local_anonymizer.app import AppApi
    from local_anonymizer.service import AnonymizerService

    class FakeClipboardReader:
        def read_text(self) -> str:
            return "Текст из адаптера"

    storage = Storage(tmp_path / "app", protector=ReversibleTestProtector())
    api = AppApi(
        service=AnonymizerService(storage=storage),
        clipboard_reader=FakeClipboardReader(),
    )

    assert api.read_clipboard_text() == {"text": "Текст из адаптера"}


def test_non_windows_clipboard_factory_is_safe_and_explicit():
    reader = default_clipboard_reader("linux")

    assert reader.read_text() == ""
    assert reader.available is False


def test_posix_permission_helpers_enforce_private_modes(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(Path, "chmod", lambda path, mode: calls.append((path, mode)))
    directory = tmp_path / "private-dir"
    file_path = tmp_path / "private-file"

    restrict_private_directory(directory, "linux")
    restrict_private_file(file_path, "darwin")
    restrict_private_file(file_path, "win32")

    assert calls == [(directory, 0o700), (file_path, 0o600)]


def test_storage_applies_private_permissions_to_owned_material(monkeypatch, tmp_path):
    import local_anonymizer.storage as storage_module

    directories = []
    files = []
    monkeypatch.setattr(
        storage_module,
        "restrict_private_directory",
        lambda path: directories.append(Path(path)),
    )
    monkeypatch.setattr(
        storage_module,
        "restrict_private_file",
        lambda path: files.append(Path(path)),
    )
    root = tmp_path / "app"
    store = Storage(root, protector=ReversibleTestProtector())
    source = tmp_path / "source.txt"
    source.write_text("sensitive", encoding="utf-8")

    document_id = store.import_document(source)
    row = store.get_document(document_id)
    output = Path(row["owned_source"]).with_name("output.txt")
    output.write_text("anonymized", encoding="utf-8")
    store.set_output(document_id, output, "op-1", "Готов")

    assert {root, root / "documents", root / "temp", root / "documents" / document_id} <= set(directories)
    assert {root / "library.db", Path(row["owned_source"]), output} <= set(files)


def test_pair_smoke_matches_portable_recovery_contract():
    from local_anonymizer.app import pair_smoke_check

    report = pair_smoke_check()

    assert report["ok"] is True
    assert report["restored_exactly"] is True
    assert report["recovery_contains_sensitive_mapping"] is True
