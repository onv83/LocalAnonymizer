from __future__ import annotations

import os
import sys
import time
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Protocol


class DataProtectionUnavailable(RuntimeError):
    """Raised when the operating system cannot protect sensitive data."""


class DataProtector(Protocol):
    def protect(self, data: bytes, purpose: str) -> bytes: ...

    def unprotect(self, envelope: bytes) -> bytes: ...


class ClipboardReader(Protocol):
    available: bool

    def read_text(self) -> str: ...


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

    def unprotect(self, envelope: bytes) -> bytes:
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

    def unprotect(self, envelope: bytes) -> bytes:
        self._raise()


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


class UnavailableClipboardReader:
    available = False

    def read_text(self) -> str:
        return ""


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
    return UnavailableDataProtector(platform_name)


def default_clipboard_reader(platform_name: str | None = None) -> ClipboardReader:
    platform_name = platform_name or sys.platform
    if platform_name == "win32":
        return WindowsClipboardReader()
    return UnavailableClipboardReader()


def restrict_private_directory(path: Path, platform_name: str | None = None) -> None:
    platform_name = platform_name or sys.platform
    if platform_name != "win32":
        path.chmod(0o700)


def restrict_private_file(path: Path, platform_name: str | None = None) -> None:
    platform_name = platform_name or sys.platform
    if platform_name != "win32":
        path.chmod(0o600)
