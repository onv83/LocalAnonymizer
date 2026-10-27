from __future__ import annotations

import base64
import getpass
import hashlib
import os
import secrets
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Callable, Protocol


class DataProtectionUnavailable(RuntimeError):
    """Raised when the operating system cannot protect sensitive data."""


class DataProtector(Protocol):
    def protect(self, data: bytes, purpose: str) -> bytes: ...

    def unprotect(self, envelope: bytes, purpose: str) -> bytes: ...


class ClipboardReader(Protocol):
    available: bool

    def read_text(self) -> str: ...

    def write_text(self, text: str) -> None: ...


class WindowsDpapiProtector:
    """Preserve the existing per-user Windows DPAPI envelope format."""

    @staticmethod
    def _win32crypt():
        try:
            import win32crypt
        except ImportError as exc:
            raise DataProtectionUnavailable("Windows DPAPI недоступен") from exc
        return win32crypt

    def protect(self, data: bytes, purpose: str) -> bytes:
        return self._win32crypt().CryptProtectData(data, purpose, None, None, None, 0)

    def unprotect(self, envelope: bytes, purpose: str) -> bytes:
        return self._win32crypt().CryptUnprotectData(envelope, None, None, None, 0)[1]


class UnavailableDataProtector:
    def __init__(self, platform_name: str):
        self.platform_name = platform_name

    def _raise(self) -> None:
        raise DataProtectionUnavailable(
            f"Защищённое хранилище пока не настроено для платформы {self.platform_name}"
        )

    def protect(self, data: bytes, purpose: str) -> bytes:
        self._raise()

    def unprotect(self, envelope: bytes, purpose: str) -> bytes:
        self._raise()


class KeyringAesGcmProtector:
    """Encrypt application data with a key held by Secret Service or Keychain."""

    _MAGIC = b"LAK1"
    _SERVICE = "LocalAnonymizer"

    def __init__(
        self,
        platform_name: str,
        *,
        backend=None,
        account: str | None = None,
        aesgcm_cls=None,
        random_bytes: Callable[[int], bytes] = secrets.token_bytes,
    ):
        self.platform_name = platform_name
        if backend is None:
            try:
                import keyring
            except ImportError as exc:
                raise DataProtectionUnavailable("Системный keyring недоступен") from exc
            backend = keyring.get_keyring()
        module = type(backend).__module__
        trusted_prefix = {
            "darwin": "keyring.backends.macOS",
            "linux": "keyring.backends.SecretService",
        }.get(platform_name)
        if trusted_prefix is None or not module.startswith(trusted_prefix):
            raise DataProtectionUnavailable(
                f"Не найден безопасный системный keyring для платформы {platform_name}"
            )
        if getattr(backend, "priority", 0) <= 0:
            raise DataProtectionUnavailable("Безопасный системный keyring недоступен")
        self._backend = backend
        self._account = account or getpass.getuser()
        if aesgcm_cls is None:
            try:
                from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            except ImportError as exc:
                raise DataProtectionUnavailable("Криптографический backend AES-GCM недоступен") from exc
            aesgcm_cls = AESGCM
        self._aesgcm_cls = aesgcm_cls
        self._random_bytes = random_bytes

    @contextmanager
    def _creation_lock(self):
        # The credential identity, not the configurable data directory, defines
        # the lock. Atomic mkdir works across processes and keeps keys in keyring.
        identity = f"{self._SERVICE}\0{self._account}".encode("utf-8")
        path = Path.home() / (".local-anonymizer-keyring-" + hashlib.sha256(identity).hexdigest() + ".lock")
        deadline = time.monotonic() + 5.0
        while True:
            try:
                path.mkdir(mode=0o700)
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise DataProtectionUnavailable("Не удалось получить блокировку системного keyring")
                time.sleep(0.05)
            except OSError as exc:
                raise DataProtectionUnavailable("Не удалось создать блокировку системного keyring") from exc
        try:
            yield
        finally:
            # Never steal a stale lock: a paused owner may still be creating its
            # key. A crash before creation requires manual recovery of this empty
            # directory after all application processes have been stopped.
            path.rmdir()

    def _cipher(self, *, create: bool):
        try:
            encoded = self._backend.get_password(self._SERVICE, self._account)
            if encoded is None and create:
                with self._creation_lock():
                    encoded = self._backend.get_password(self._SERVICE, self._account)
                    if encoded is None:
                        key = self._random_bytes(32)
                        if len(key) != 32:
                            raise DataProtectionUnavailable("Некорректный источник криптографической случайности")
                        generated = base64.urlsafe_b64encode(key).decode("ascii")
                        self._backend.set_password(self._SERVICE, self._account, generated)
                        encoded = self._backend.get_password(self._SERVICE, self._account)
            if encoded is None:
                raise DataProtectionUnavailable("Ключ шифрования не найден в системном keyring")
            key = base64.b64decode(encoded.encode("ascii"), altchars=b"-_", validate=True)
        except DataProtectionUnavailable:
            raise
        except Exception as exc:
            raise DataProtectionUnavailable("Не удалось получить ключ из системного keyring") from exc
        if len(key) != 32:
            raise DataProtectionUnavailable("Системный keyring содержит некорректный ключ")
        return self._aesgcm_cls(key)

    def protect(self, data: bytes, purpose: str) -> bytes:
        purpose_bytes = purpose.encode("utf-8")
        if not purpose_bytes or len(purpose_bytes) > 65535:
            raise ValueError("Некорректное назначение защищаемых данных")
        header = self._MAGIC + len(purpose_bytes).to_bytes(2, "big") + purpose_bytes
        nonce = self._random_bytes(12)
        if len(nonce) != 12:
            raise DataProtectionUnavailable("Некорректный источник криптографической случайности")
        return header + nonce + self._cipher(create=True).encrypt(nonce, data, header)

    def unprotect(self, envelope: bytes, purpose: str) -> bytes:
        if len(envelope) < 6 or not envelope.startswith(self._MAGIC):
            raise DataProtectionUnavailable("Защищённые данные повреждены")
        purpose_size = int.from_bytes(envelope[4:6], "big")
        header_size = 6 + purpose_size
        if purpose_size == 0 or len(envelope) <= header_size + 12:
            raise DataProtectionUnavailable("Защищённые данные повреждены")
        header = envelope[:header_size]
        expected_purpose = purpose.encode("utf-8")
        if envelope[6:header_size] != expected_purpose:
            raise DataProtectionUnavailable("Назначение защищённых данных не совпадает")
        nonce = envelope[header_size : header_size + 12]
        ciphertext = envelope[header_size + 12 :]
        try:
            return self._cipher(create=False).decrypt(nonce, ciphertext, header)
        except DataProtectionUnavailable:
            raise
        except Exception as exc:
            raise DataProtectionUnavailable("Не удалось расшифровать: данные повреждены") from exc


class WindowsClipboardReader:
    available = True

    @staticmethod
    def _win32clipboard():
        try:
            import win32clipboard
        except ImportError as exc:
            raise RuntimeError("Буфер обмена Windows недоступен") from exc
        return win32clipboard

    def read_text(self) -> str:
        clipboard = self._win32clipboard()
        for attempt in range(5):
            try:
                clipboard.OpenClipboard()
                break
            except OSError:
                if attempt == 4:
                    raise RuntimeError("Буфер обмена временно недоступен") from None
                time.sleep(0.04)
        try:
            if not clipboard.IsClipboardFormatAvailable(clipboard.CF_UNICODETEXT):
                return ""
            value = clipboard.GetClipboardData(clipboard.CF_UNICODETEXT)
            return value if isinstance(value, str) else ""
        finally:
            clipboard.CloseClipboard()

    def write_text(self, text: str) -> None:
        clipboard = self._win32clipboard()
        for attempt in range(5):
            try:
                clipboard.OpenClipboard()
                break
            except OSError:
                if attempt == 4:
                    raise RuntimeError("Буфер обмена временно недоступен") from None
                time.sleep(0.04)
        try:
            clipboard.EmptyClipboard()
            clipboard.SetClipboardData(clipboard.CF_UNICODETEXT, text)
        finally:
            clipboard.CloseClipboard()


class UnavailableClipboardReader:
    available = False

    def read_text(self) -> str:
        return ""

    def write_text(self, text: str) -> None:
        raise RuntimeError("Системный буфер обмена недоступен")


class CommandClipboardReader:
    """Read the native clipboard through fixed, shell-free OS commands."""

    def __init__(
        self,
        platform_name: str,
        *,
        environment: Mapping[str, str] | None = None,
        which: Callable[[str], str | None] = shutil.which,
        runner=subprocess.run,
    ):
        environment = os.environ if environment is None else environment
        read_command: list[str] | None = None
        write_command: list[str] | None = None
        if platform_name == "darwin":
            read_executable = which("pbpaste")
            write_executable = which("pbcopy")
            read_command = [read_executable] if read_executable else None
            write_command = [write_executable] if write_executable else None
        elif platform_name.startswith("linux"):
            if environment.get("WAYLAND_DISPLAY"):
                read_executable = which("wl-paste")
                write_executable = which("wl-copy")
                if read_executable and write_executable:
                    read_command = [read_executable, "--no-newline"]
                    write_command = [write_executable]
            if read_command is None:
                executable = which("xclip")
                if executable:
                    read_command = [executable, "-selection", "clipboard", "-o"]
                    write_command = [executable, "-selection", "clipboard", "-i"]
            if read_command is None:
                executable = which("xsel")
                if executable:
                    read_command = [executable, "--clipboard", "--output"]
                    write_command = [executable, "--clipboard", "--input"]
        self._read_command = read_command
        self._write_command = write_command
        self._runner = runner
        self.available = read_command is not None and write_command is not None

    def read_text(self) -> str:
        if self._read_command is None:
            return ""
        try:
            result = self._runner(
                self._read_command,
                shell=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="strict",
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
            raise RuntimeError("Буфер обмена временно недоступен") from exc
        if result.returncode != 0:
            raise RuntimeError("Буфер обмена временно недоступен")
        if len(result.stdout.encode("utf-8")) > 10 * 1024 * 1024:
            raise RuntimeError("Содержимое буфера обмена слишком велико")
        return result.stdout

    def write_text(self, text: str) -> None:
        if self._write_command is None:
            raise RuntimeError("Системный буфер обмена недоступен")
        if len(text.encode("utf-8")) > 10 * 1024 * 1024:
            raise RuntimeError("Содержимое буфера обмена слишком велико")
        try:
            result = self._runner(
                self._write_command,
                shell=False,
                input=text,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="strict",
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
            raise RuntimeError("Буфер обмена временно недоступен") from exc
        if result.returncode != 0:
            raise RuntimeError("Буфер обмена временно недоступен")


def default_data_dir(
    platform_name: str | None = None,
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    platform_name = platform_name or sys.platform
    environment = os.environ if environment is None else environment
    home = Path.home() if home is None else Path(home)

    if platform_name == "win32":
        local_app_data = environment.get("LOCALAPPDATA")
        if not local_app_data:
            raise RuntimeError("Переменная LOCALAPPDATA не определена")
        return Path(local_app_data) / "LocalAnonymizer"
    if platform_name == "darwin":
        return home / "Library" / "Application Support" / "LocalAnonymizer"
    if platform_name.startswith("linux"):
        data_home = environment.get("XDG_DATA_HOME")
        candidate = Path(data_home) if data_home else None
        base = (
            candidate
            if data_home and PurePosixPath(data_home).is_absolute()
            else home / ".local" / "share"
        )
        return base / "local-anonymizer"
    raise RuntimeError(f"Неподдерживаемая платформа: {platform_name}")


def default_data_protector(platform_name: str | None = None) -> DataProtector:
    platform_name = platform_name or sys.platform
    if platform_name == "win32":
        return WindowsDpapiProtector()
    if platform_name == "darwin" or platform_name.startswith("linux"):
        return KeyringAesGcmProtector("linux" if platform_name.startswith("linux") else "darwin")
    return UnavailableDataProtector(platform_name)


def default_clipboard_reader(
    platform_name: str | None = None,
    *,
    environment: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> ClipboardReader:
    platform_name = platform_name or sys.platform
    if platform_name == "win32":
        return WindowsClipboardReader()
    if platform_name == "darwin" or platform_name.startswith("linux"):
        reader = CommandClipboardReader(
            platform_name,
            environment=environment,
            which=which,
        )
        if reader.available:
            return reader
    return UnavailableClipboardReader()


def restrict_private_directory(path: Path, platform_name: str | None = None) -> None:
    platform_name = platform_name or sys.platform
    if platform_name != "win32":
        path.chmod(0o700)


def restrict_private_file(path: Path, platform_name: str | None = None) -> None:
    platform_name = platform_name or sys.platform
    if platform_name != "win32":
        path.chmod(0o600)
