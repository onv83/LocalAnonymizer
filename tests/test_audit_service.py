"""Regression coverage for service export/restore data-safety audit."""
from pathlib import Path
import threading

import pytest

from local_anonymizer.engine import AnonymizationResult
from local_anonymizer.service import AnonymizerService, export_mapping_csv


class Engine:
    def __init__(self, value="FIRST"):
        self.value = value

    def anonymize(self, text):
        return AnonymizationResult(text="[ФИО-1]", mapping={"[ФИО-1]": self.value}, total=1)


@pytest.fixture
def document(tmp_path):
    service = AnonymizerService(tmp_path / "app")
    source = tmp_path / "source.txt"
    source.write_text("FIRST", encoding="utf-8")
    doc_id = service.import_file(source)
    report = service.anonymize(doc_id, Engine())
    return service, doc_id, report


@pytest.mark.parametrize("operation", ["restore", "pair", "archive", "mapping"])
def test_adjacent_user_files_are_never_used_as_scratch(document, tmp_path, operation):
    service, doc_id, report = document
    destination = tmp_path / "exports" / "restored.txt"
    destination.parent.mkdir()
    if operation == "restore":
        neighbor = destination.with_name(".restored.validated.txt")
    elif operation == "pair":
        neighbor = destination.with_name("." + service._recovery_name(destination) + ".tmp")
    else:
        neighbor = destination.with_name("." + destination.name + ".tmp")
    neighbor.write_bytes(b"IRREPLACEABLE USER DATA")
    if operation == "restore":
        service.restore(doc_id, report["output_path"], destination)
    elif operation == "pair":
        service.export_pair(doc_id, destination)
    elif operation == "archive":
        service.export_all_ready(destination)
    else:
        export_mapping_csv({"[ФИО-1]": "FIRST"}, destination)
    assert neighbor.exists(), "user-owned neighbor was deleted"
    assert neighbor.read_bytes() == b"IRREPLACEABLE USER DATA"
    assert not any(p.is_dir() for p in destination.parent.iterdir())


def test_pair_export_keeps_one_operation_during_concurrent_reanonymization(document, tmp_path, monkeypatch):
    service, doc_id, first = document
    selected = threading.Event()
    release = threading.Event()
    changed = threading.Event()
    errors = []
    original = service._recovery_payload

    def paused_payload(row, name):
        payload = original(row, name)
        selected.set()
        assert release.wait(5)
        return payload

    monkeypatch.setattr(service, "_recovery_payload", paused_payload)
    destination = tmp_path / "export.txt"

    def export():
        try:
            service.export_pair(doc_id, destination)
        except Exception as exc:
            errors.append(exc)

    def change():
        try:
            service.anonymize(doc_id, Engine("SECOND"))
        except Exception as exc:
            errors.append(exc)
        finally:
            changed.set()

    exporter = threading.Thread(target=export)
    writer = threading.Thread(target=change)
    exporter.start()
    assert selected.wait(5)
    writer.start()
    raced = changed.wait(0.3)
    release.set()
    exporter.join(5)
    writer.join(5)
    assert not exporter.is_alive() and not writer.is_alive()
    assert not errors
    assert not raced, "reanonymization invalidated the operation being exported"
    fresh = AnonymizerService(tmp_path / "fresh-install")
    restored = tmp_path / "restored.txt"
    fresh.restore_from_pair(destination, restored)
    assert restored.read_text(encoding="utf-8") == "FIRST"


@pytest.mark.parametrize("operation", ["pair", "anonymized", "restore", "mapping", "archive"])
def test_operation_selection_waits_for_document_lock(document, tmp_path, monkeypatch, operation):
    service, doc_id, report = document
    selected = threading.Event()
    started = threading.Event()
    errors = []
    original = service.storage.get_document

    def read(document_id):
        selected.set()
        return original(document_id)

    monkeypatch.setattr(service.storage, "get_document", read)
    target = tmp_path / "out.txt"
    actions = {
        "pair": lambda: service.export_pair(doc_id, target),
        "anonymized": lambda: service.export_anonymized(doc_id, target),
        "restore": lambda: service.restore(doc_id, report["output_path"], target),
        "mapping": lambda: service.export_mapping(doc_id, target),
        "archive": lambda: service.export_all_ready(target),
    }

    def run():
        started.set()
        try:
            actions[operation]()
        except Exception as exc:
            errors.append(exc)

    with service._document_lock(doc_id):
        thread = threading.Thread(target=run)
        thread.start()
        assert started.wait(5)
        premature = selected.wait(0.2)
    thread.join(5)
    assert not thread.is_alive()
    assert not errors
    assert not premature, "operation selected a row outside its document lock"
    assert selected.is_set(), "operation must re-fetch current row under its lock"


@pytest.mark.parametrize("operation", ["restore", "anonymized", "pair"])
@pytest.mark.parametrize("existing", [False, True])
def test_failed_processing_never_publishes_partial_output(document, tmp_path, monkeypatch, operation, existing):
    service, doc_id, report = document
    folder = tmp_path / "exports"
    folder.mkdir()
    target = folder / "out.txt"
    if existing:
        target.write_bytes(b"PREVIOUS USER OUTPUT")

    def partial(source, destination, *args, **kwargs):
        Path(destination).write_bytes(b"PARTIAL SECRET")
        raise OSError("injected failure")

    if operation == "restore":
        monkeypatch.setattr("local_anonymizer.service.restore_text_file", partial)
        action = lambda: service.restore(doc_id, report["output_path"], target)
    else:
        monkeypatch.setattr("local_anonymizer.service.shutil.copy2", partial)
        action = lambda: (service.export_pair if operation == "pair" else service.export_anonymized)(doc_id, target)
    before_temp = set(service.storage.temp_dir.iterdir())
    with pytest.raises(OSError, match="injected failure"):
        action()
    assert list(folder.iterdir()) == ([target] if existing else [])
    if existing:
        assert target.read_bytes() == b"PREVIOUS USER OUTPUT"
    assert set(service.storage.temp_dir.iterdir()) == before_temp


@pytest.mark.parametrize("existing", [False, True])
def test_pair_publication_failure_preserves_previous_pair(document, tmp_path, monkeypatch, existing):
    import os
    service, doc_id, report = document
    folder = tmp_path / "exports"
    folder.mkdir()
    target = folder / "out.txt"
    recovery = target.with_name(service._recovery_name(target))
    if existing:
        service.export_pair(doc_id, target)
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    service.anonymize(doc_id, Engine("SECOND"))
    replace = os.replace

    def fail_recovery(source, destination):
        if Path(destination) == recovery:
            raise OSError("publication fault")
        return replace(source, destination)

    monkeypatch.setattr("local_anonymizer.service.os.replace", fail_recovery)
    with pytest.raises(OSError, match="publication fault"):
        service.export_pair(doc_id, target)
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before


@pytest.mark.parametrize("separate_instance", [False, True])
@pytest.mark.parametrize("fail_first", [False, True])
@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("shared_companion_only", [False, True])
def test_overlapping_pair_publications_are_serialized(
        document, tmp_path, monkeypatch, separate_instance, fail_first,
        existing, shared_companion_only):
    import os
    service, first_id, _ = document
    second_service = AnonymizerService(tmp_path / "other-app") if separate_instance else service
    source = tmp_path / "second.txt"
    source.write_text("SECOND", encoding="utf-8")
    second_id = second_service.import_file(source)
    second_service.anonymize(second_id, Engine("SECOND"))
    folder = tmp_path / "exports"
    folder.mkdir()
    first_target = folder / "out.txt"
    second_target = folder / ("out.anonymized.txt" if shared_companion_only else "out.txt")
    recovery = first_target.with_name(service._recovery_name(first_target))
    if existing:
        service.export_pair(first_id, first_target)
    previous = first_target.read_bytes() if existing else None
    paused = threading.Event()
    release = threading.Event()
    started = threading.Event()
    finished = threading.Event()
    errors = {}
    replace = os.replace

    def pause_publication(source, target):
        if Path(target) == recovery and threading.current_thread().name == "first-export":
            paused.set()
            if not release.wait(10):
                raise TimeoutError("test did not release publication barrier")
            if fail_first:
                raise OSError("publication fault")
        return replace(source, target)

    def run(label, svc, doc_id, target):
        if label == "second":
            started.set()
        try:
            svc.export_pair(doc_id, target)
        except Exception as exc:
            errors[label] = exc
        finally:
            svc.storage.connection.close()
            if label == "second":
                finished.set()

    monkeypatch.setattr("local_anonymizer.service.os.replace", pause_publication)
    first = threading.Thread(target=run, args=("first", service, first_id, first_target), name="first-export")
    second = threading.Thread(target=run, args=("second", second_service, second_id, second_target))
    first.start()
    try:
        assert paused.wait(5)
        second.start()
        assert started.wait(5)
        raced = finished.wait(0.3)
    finally:
        # Never wait for the blocked exporter before opening the barrier.
        release.set()
        first.join(10)
        if second.ident is not None:
            second.join(10)
    assert not first.is_alive() and not second.is_alive()
    assert not raced, "overlapping destination publication bypassed serialization"
    assert "second" not in errors
    if fail_first:
        assert isinstance(errors.get("first"), OSError)
        assert str(errors["first"]) == "publication fault"
        if shared_companion_only:
            assert (first_target.read_bytes() if first_target.exists() else None) == previous
    else:
        assert not errors
    fresh = AnonymizerService(tmp_path / "fresh")
    restored = tmp_path / "restored.txt"
    fresh.restore_from_pair(second_target, restored)
    assert restored.read_text(encoding="utf-8") == "SECOND"
    assert not any(p.is_dir() for p in folder.iterdir())


@pytest.mark.parametrize("lock_kind", ["file", "directory"])
@pytest.mark.parametrize("locked_output", ["anonymized", "recovery"])
def test_pair_lock_collision_fails_closed_without_touching_owner(
        document, tmp_path, monkeypatch, lock_kind, locked_output):
    import hashlib
    import os
    import subprocess
    import sys
    service, doc_id, _ = document
    folder = tmp_path / "exports"
    folder.mkdir()
    target = folder / "out.txt"
    recovery = target.with_name(service._recovery_name(target))
    target.write_bytes(b"PREVIOUS DOCUMENT")
    recovery.write_bytes(b"PREVIOUS COMPANION")
    selected = target if locked_output == "anonymized" else recovery
    identity = os.path.normcase(str(selected.resolve()))
    digest = hashlib.sha256(os.fsencode(identity)).hexdigest()
    lock = Path(identity).parent / (".local-anonymizer-lock-" + digest)
    # A separate process owns this reservation. Stale and active reservations
    # must both fail closed, and user-owned files must never be unlinked.
    script = (
        "import pathlib,sys; p=pathlib.Path(sys.argv[1]); "
        "p.mkdir() if sys.argv[2]=='directory' else p.write_bytes(b'OWNER')"
    )
    subprocess.run([sys.executable, "-c", script, str(lock), lock_kind], check=True, timeout=10)
    before = set(folder.iterdir())
    monkeypatch.setattr("local_anonymizer.service._DESTINATION_LOCK_TIMEOUT", 0.1)
    with pytest.raises(TimeoutError, match="Destination publication is busy"):
        service.export_pair(doc_id, target)
    assert set(folder.iterdir()) == before, "partial lock acquisition leaked a directory"
    assert target.read_bytes() == b"PREVIOUS DOCUMENT"
    assert recovery.read_bytes() == b"PREVIOUS COMPANION"
    if lock_kind == "file":
        assert lock.read_bytes() == b"OWNER"
    else:
        assert lock.is_dir() and not list(lock.iterdir())
