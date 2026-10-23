from __future__ import annotations

import json
import shutil
import sqlite3
import threading
import uuid
from pathlib import Path

from .engine import normalize_label
from .platform_services import (
    DataProtectionUnavailable,
    DataProtector,
    default_data_dir,
    default_data_protector,
    restrict_private_directory,
    restrict_private_file,
)


class MappingError(RuntimeError):
    pass


class Storage:
    def __init__(self, root: str | Path | None = None, *, protector: DataProtector | None = None):
        self.root = Path(root if root is not None else default_data_dir()).resolve()
        self.protector = protector if protector is not None else default_data_protector()
        self.documents_dir = self.root / "documents"
        self.temp_dir = self.root / "temp"
        self.root.mkdir(parents=True, exist_ok=True)
        restrict_private_directory(self.root)
        for directory in (self.documents_dir, self.temp_dir):
            directory.mkdir(exist_ok=True)
            restrict_private_directory(directory)
        self._database_path = self.root / "library.db"
        self._connections = threading.local()
        connection = self.connection
        restrict_private_file(self._database_path)
        connection.execute("pragma journal_mode=DELETE")
        connection.execute("pragma secure_delete=ON")
        connection.executescript("""
          create table if not exists documents(
            id text primary key, display_name text not null, source_path text not null,
            owned_source text, output_path text, operation_id text, status text not null,
            created_at text not null default current_timestamp);
          create table if not exists mappings(
            document_id text primary key references documents(id) on delete cascade,
            operation_id text not null, envelope blob not null);
          create table if not exists profiles(
            name text primary key, envelope blob not null);
        """)
        connection.commit()

    @property
    def connection(self) -> sqlite3.Connection:
        """Return a separate SQLite connection for each pywebview thread."""
        connection = getattr(self._connections, "connection", None)
        if connection is None:
            connection = sqlite3.connect(self._database_path, timeout=30)
            connection.row_factory = sqlite3.Row
            connection.execute("pragma secure_delete=ON")
            self._connections.connection = connection
        return connection

    def _protect(self, data: bytes, description: str) -> bytes:
        return self.protector.protect(data, description)

    def _unprotect(self, data: bytes, purpose: str) -> bytes:
        return self.protector.unprotect(data, purpose)

    def import_document(self, source: str | Path, *, copy_source: bool = True) -> str:
        source = Path(source).resolve()
        doc_id = str(uuid.uuid4())
        owned: str | None = None
        folder: Path | None = None
        if copy_source:
            if not source.is_file():
                raise FileNotFoundError(source)
            folder = self.documents_dir / doc_id
        try:
            if folder is not None:
                folder.mkdir()
                restrict_private_directory(folder)
                target = folder / ("original" + source.suffix.lower())
                shutil.copy2(source, target)
                restrict_private_file(target)
                owned = str(target)
            self.connection.execute("insert into documents(id,display_name,source_path,owned_source,status) values(?,?,?,?,?)",
                                    (doc_id, source.name, str(source), owned, "Импортирован"))
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            if folder is not None:
                shutil.rmtree(folder, ignore_errors=True)
            raise
        return doc_id

    def discard_import(self, document_id: str) -> None:
        """Rollback a post-copy import stage and erase all owned plaintext."""
        folder = self._owned(self.documents_dir / document_id)
        try:
            self.connection.execute("delete from mappings where document_id=?", (document_id,))
            self.connection.execute("delete from documents where id=?", (document_id,))
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        finally:
            if folder.is_dir():
                shutil.rmtree(folder, ignore_errors=True)

    def get_document(self, document_id: str) -> dict:
        row = self.connection.execute("select * from documents where id=?", (document_id,)).fetchone()
        if not row:
            raise KeyError(document_id)
        return dict(row)

    def list_documents(self) -> list[dict]:
        return [dict(row) for row in self.connection.execute("select * from documents order by created_at desc")]

    def set_output(self, document_id: str, path: str | Path, operation_id: str, status: str) -> None:
        path = self._owned(path)
        if not path.is_file():
            raise FileNotFoundError(path)
        restrict_private_file(path)
        self.connection.execute("update documents set output_path=?,operation_id=?,status=? where id=?",
                                (str(path), operation_id, status, document_id))
        self.connection.commit()

    def save_mapping(self, document_id: str, operation_id: str, mapping: dict[str, str],
                     package_archive: dict | None = None) -> None:
        if not self.connection.execute("select 1 from documents where id=?", (document_id,)).fetchone():
            raise KeyError(document_id)
        payload = {"schema": 2 if package_archive is not None else 1,
                   "document_id": document_id, "operation_id": operation_id,
                   "marker_manifest": sorted(mapping), "mapping": mapping}
        if package_archive is not None:
            payload["package_archive"] = package_archive
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        envelope = self._protect(raw, f"LocalAnonymizer:{document_id}:{operation_id}")
        self.connection.execute("insert or replace into mappings(document_id,operation_id,envelope) values(?,?,?)",
                                (document_id, operation_id, envelope))
        self.connection.commit()

    def commit_operation(self, document_id: str, operation_id: str, mapping: dict[str, str],
                         output_path: str | Path, status: str,
                         package_archive: dict | None = None) -> None:
        """Atomically switch output, encrypted mapping, operation and status."""
        output = self._owned(output_path)
        if not output.is_file():
            raise FileNotFoundError(output)
        restrict_private_file(output)
        payload = {"schema": 2 if package_archive is not None else 1,
                   "document_id": document_id, "operation_id": operation_id,
                   "marker_manifest": sorted(mapping), "mapping": mapping}
        if package_archive is not None:
            payload["package_archive"] = package_archive
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        envelope = self._protect(raw, f"LocalAnonymizer:{document_id}:{operation_id}")
        connection = self.connection
        try:
            connection.execute("begin immediate")
            if not connection.execute("select 1 from documents where id=?", (document_id,)).fetchone():
                raise KeyError(document_id)
            connection.execute("insert or replace into mappings(document_id,operation_id,envelope) values(?,?,?)",
                               (document_id, operation_id, envelope))
            connection.execute("update documents set output_path=?,operation_id=?,status=? where id=?",
                               (str(output), operation_id, status, document_id))
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def load_mapping(self, document_id: str, operation_id: str) -> dict[str, str]:
        mapping, _ = self.load_restore_bundle(document_id, operation_id)
        return mapping

    def load_restore_envelope(self, document_id: str, operation_id: str) -> bytes:
        row = self.connection.execute(
            "select operation_id,envelope from mappings where document_id=?", (document_id,)
        ).fetchone()
        if not row or row["operation_id"] != operation_id:
            raise MappingError("Карта замен не соответствует документу или операции")
        return bytes(row["envelope"])

    def decode_restore_envelope(self, envelope: bytes, document_id: str,
                                operation_id: str) -> tuple[dict[str, str], dict | None]:
        purpose = f"LocalAnonymizer:{document_id}:{operation_id}"
        try:
            payload = json.loads(self._unprotect(envelope, purpose).decode("utf-8"))
        except DataProtectionUnavailable:
            raise
        except Exception as exc:
            raise MappingError("Защищённая карта восстановления повреждена") from exc
        return self.decode_restore_payload(payload, document_id, operation_id)

    @staticmethod
    def decode_restore_payload(payload: object, document_id: str,
                               operation_id: str) -> tuple[dict[str, str], dict | None]:
        """Validate a decrypted or portable restore bundle."""
        if not isinstance(payload, dict):
            raise MappingError("Файл восстановления повреждён")
        if (payload.get("schema") not in {1, 2}
                or payload.get("document_id") != document_id
                or payload.get("operation_id") != operation_id):
            raise MappingError("Файл восстановления не соответствует обезличенному документу")
        mapping = payload.get("mapping")
        if not isinstance(mapping, dict) or payload.get("marker_manifest") != sorted(mapping):
            raise MappingError("Повреждён манифест маркеров")
        package_archive = payload.get("package_archive") if payload.get("schema") == 2 else None
        if package_archive is not None and not isinstance(package_archive, dict):
            raise MappingError("Повреждён защищённый архив документа")
        return {str(k): str(v) for k, v in mapping.items()}, package_archive

    def load_restore_bundle(self, document_id: str, operation_id: str) -> tuple[dict[str, str], dict | None]:
        envelope = self.load_restore_envelope(document_id, operation_id)
        return self.decode_restore_envelope(envelope, document_id, operation_id)

    def _owned(self, path: str | Path) -> Path:
        candidate = Path(path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Операция разрешена только внутри каталога приложения") from exc
        if candidate == self.root:
            raise ValueError("Нельзя удалить корневой каталог приложения")
        return candidate

    def delete_document(self, document_id: str) -> None:
        row = self.get_document(document_id)
        paths = {row.get("owned_source"), row.get("output_path")}
        for value in paths:
            if not value:
                continue
            try:
                path = self._owned(value)
            except ValueError:
                continue
            if path.is_file() and not path.is_symlink():
                path.unlink()
        folder = self.documents_dir / document_id
        if folder.exists() and self._owned(folder) == folder.resolve():
            shutil.rmtree(folder)
        self.connection.execute("delete from mappings where document_id=?", (document_id,))
        self.connection.execute("delete from documents where id=?", (document_id,))
        self.connection.commit()

    def save_profile(self, name: str, dictionary: dict[str, str], whitelist: list[str], *,
                     paranoid: bool = False, uncertain_mode: str | None = None) -> None:
        profile = {"version": 1, "name": name, "dictionary": dictionary,
                   "whitelist": whitelist, "paranoid": bool(paranoid)}
        if uncertain_mode is not None:
            profile["uncertain_mode"] = uncertain_mode
        payload = self._validate_profile(profile)
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.connection.execute("insert or replace into profiles(name,envelope) values(?,?)",
                                (name, self._protect(raw, f"LocalAnonymizer:profile:{name}")))
        self.connection.commit()

    def load_profile(self, name: str) -> dict:
        row = self.connection.execute("select envelope from profiles where name=?", (name,)).fetchone()
        if not row:
            raise KeyError(name)
        purpose = f"LocalAnonymizer:profile:{name}"
        return self._validate_profile(
            json.loads(self._unprotect(bytes(row[0]), purpose).decode("utf-8"))
        )

    def export_profile(self, name: str) -> str:
        return json.dumps(self.load_profile(name), ensure_ascii=False, indent=2)

    def import_profile(self, text: str) -> str:
        payload = self._validate_profile(json.loads(text))
        self.save_profile(
            payload["name"], payload["dictionary"], payload["whitelist"],
            paranoid=payload["paranoid"], uncertain_mode=payload.get("uncertain_mode"),
        )
        return payload["name"]

    @staticmethod
    def _validate_profile(payload: object) -> dict:
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ValueError("Неподдерживаемая версия профиля")
        name, dictionary, whitelist = payload.get("name"), payload.get("dictionary"), payload.get("whitelist")
        if not isinstance(name, str) or not 1 <= len(name) <= 80 or not isinstance(dictionary, dict) or not isinstance(whitelist, list):
            raise ValueError("Некорректный профиль")
        clean: dict[str, str] = {}
        for phrase, label in dictionary.items():
            if not isinstance(phrase, str) or not phrase.strip() or not isinstance(label, str):
                raise ValueError("Некорректное правило словаря")
            try:
                clean[phrase] = normalize_label(label)
            except ValueError as exc:
                raise ValueError("Некорректное правило словаря") from exc
        if any(not isinstance(x, str) or len(x) > 500 for x in whitelist):
            raise ValueError("Некорректный белый список")
        result = {"version": 1, "name": name, "dictionary": clean, "whitelist": whitelist,
                  "paranoid": bool(payload.get("paranoid", False))}
        if "uncertain_mode" in payload:
            uncertain_mode = payload["uncertain_mode"]
            if not isinstance(uncertain_mode, str) or uncertain_mode not in {"off", "review", "auto"}:
                raise ValueError("Некорректный режим обработки спорных фрагментов")
            result["uncertain_mode"] = uncertain_mode
            result["paranoid"] = uncertain_mode == "auto"
        return result
