import os
import subprocess
import sys
from pathlib import Path

import pytest

from local_anonymizer.platform_services import (
    CommandClipboardReader,
    DataProtectionUnavailable,
    KeyringAesGcmProtector,
    WindowsDpapiProtector,
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

    def unprotect(self, envelope: bytes, purpose: str) -> bytes:
        if not envelope.startswith(b"TEST\0"):
            raise ValueError("invalid test envelope")
        _, stored_purpose, payload = envelope.split(b"\0", 2)
        if stored_purpose.decode("utf-8") != purpose:
            raise ValueError("wrong purpose")
        return payload[::-1]


class UnavailableTestProtector:
    def protect(self, data: bytes, purpose: str) -> bytes:
        raise DataProtectionUnavailable("secure storage unavailable")

    def unprotect(self, envelope: bytes, purpose: str) -> bytes:
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
        def __init__(self):
            self.written = []

        def read_text(self) -> str:
            return "Текст из адаптера"

        def write_text(self, text: str) -> None:
            self.written.append(text)

    storage = Storage(tmp_path / "app", protector=ReversibleTestProtector())
    clipboard = FakeClipboardReader()
    api = AppApi(
        service=AnonymizerService(storage=storage),
        clipboard_reader=clipboard,
    )

    assert api.read_clipboard_text() == {"text": "Текст из адаптера"}
    assert api.write_clipboard_text("Обезличенный текст") == {"ok": True}
    assert clipboard.written == ["Обезличенный текст"]


def test_non_windows_clipboard_factory_is_safe_and_explicit():
    reader = default_clipboard_reader("linux", environment={}, which=lambda command: None)

    assert reader.read_text() == ""
    assert reader.available is False


def test_keyring_aes_gcm_protector_roundtrips_and_detects_tampering():
    import hmac

    class FakeAesGcm:
        def __init__(self, key):
            self.key = key

        def encrypt(self, nonce, data, aad):
            body = bytes(value ^ self.key[index % len(self.key)] for index, value in enumerate(data))
            return body + hmac.digest(self.key, nonce + aad + body, "sha256")

        def decrypt(self, nonce, data, aad):
            body, tag = data[:-32], data[-32:]
            expected = hmac.digest(self.key, nonce + aad + body, "sha256")
            if not hmac.compare_digest(tag, expected):
                raise ValueError("invalid tag")
            return bytes(value ^ self.key[index % len(self.key)] for index, value in enumerate(body))

    class FakeSecretServiceKeyring:
        priority = 5

        def __init__(self):
            self.values = {}

        def get_password(self, service, account):
            return self.values.get((service, account))

        def set_password(self, service, account, value):
            self.values[(service, account)] = value

    FakeSecretServiceKeyring.__module__ = "keyring.backends.SecretService"
    backend = FakeSecretServiceKeyring()
    protector = KeyringAesGcmProtector(
        "linux",
        backend=backend,
        account="alice",
        aesgcm_cls=FakeAesGcm,
        random_bytes=lambda size: bytes(range(size)),
    )

    envelope = protector.protect(b"sensitive mapping", "mapping:test")

    assert b"sensitive mapping" not in envelope
    assert protector.unprotect(envelope, "mapping:test") == b"sensitive mapping"
    with pytest.raises(DataProtectionUnavailable, match="(?i)назначени|расшифровать"):
        protector.unprotect(envelope, "mapping:other")
    with pytest.raises(DataProtectionUnavailable, match="повреждены|расшифровать"):
        protector.unprotect(envelope[:-1] + bytes([envelope[-1] ^ 1]), "mapping:test")

    backend.values.clear()
    with pytest.raises(DataProtectionUnavailable, match="(?i)ключ.*не найден"):
        protector.unprotect(envelope, "mapping:test")
    assert backend.values == {}


def test_keyring_protector_rejects_plaintext_or_unknown_backends():
    class PlaintextBackend:
        priority = 1

        def get_password(self, service, account):
            return None

        def set_password(self, service, account, value):
            raise AssertionError("must reject before storing a key")

    PlaintextBackend.__module__ = "keyring.backends.fail"

    with pytest.raises(DataProtectionUnavailable, match="безопасный.*keyring"):
        KeyringAesGcmProtector("linux", backend=PlaintextBackend(), account="alice")


def test_command_clipboard_reader_uses_native_command_without_shell():
    calls = []

    class Result:
        returncode = 0
        stdout = "Буфер обмена"
        stderr = ""

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return Result()

    reader = CommandClipboardReader(
        "linux",
        environment={"WAYLAND_DISPLAY": "wayland-0"},
        which=lambda command: f"/usr/bin/{command}" if command in {"wl-paste", "wl-copy"} else None,
        runner=runner,
    )

    assert reader.available is True
    assert reader.read_text() == "Буфер обмена"
    reader.write_text("Обезличенный текст")
    assert calls[0][0] == ["/usr/bin/wl-paste", "--no-newline"]
    assert calls[0][1]["shell"] is False
    assert calls[1][0] == ["/usr/bin/wl-copy"]
    assert calls[1][1]["input"] == "Обезличенный текст"


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
