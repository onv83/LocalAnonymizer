"""Synthetic keyring tests: never access a real credential store."""
import base64
import hashlib
import hmac
import multiprocessing
from pathlib import Path

import pytest

from local_anonymizer.platform_services import DataProtectionUnavailable, KeyringAesGcmProtector
import local_anonymizer.platform_services as platform_services


def test_lock_open_error_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    state = {"writes": []}

    def denied(*args, **kwargs):
        raise PermissionError("synthetic denied")

    monkeypatch.setattr(Path, "mkdir", denied)
    with pytest.raises(DataProtectionUnavailable, match="блокиров"):
        make_protector(MemoryBackend(state)).protect(b"synthetic", "audit")
    assert state == {"writes": []}



class TestCipher:
    __test__ = False

    def __init__(self, key):
        self.key = key

    def encrypt(self, nonce, data, aad):
        return data + hmac.digest(self.key, nonce + aad + data, "sha256")

    def decrypt(self, nonce, data, aad):
        body, tag = data[:-32], data[-32:]
        if not hmac.compare_digest(tag, hmac.digest(self.key, nonce + aad + body, "sha256")):
            raise ValueError("different key")
        return body


class MemoryBackend:
    priority = 5

    def __init__(self, state, barrier=None):
        self.state = state
        self.barrier = barrier
        self.first = True

    def get_password(self, service, account):
        value = self.state.get("key")
        if self.first and self.barrier is not None:
            self.first = False
            self.barrier.wait(10)
        return value

    def set_password(self, service, account, value):
        self.state["writes"].append(value)
        self.state["key"] = value


MemoryBackend.__module__ = "keyring.backends.SecretService"


def make_protector(backend):
    return KeyringAesGcmProtector(
        "linux", backend=backend, account="synthetic-audit", aesgcm_cls=TestCipher
    )


def race_worker(home, state, barrier, results):
    # Scoped to the child, never modify the real home or environment.
    Path.home = classmethod(lambda cls: Path(home))
    try:
        protector = make_protector(MemoryBackend(state, barrier))
        results.put((True, protector.protect(b"synthetic", "audit")))
    except Exception as exc:
        results.put((False, repr(exc)))


def test_first_use_two_processes_share_one_key(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    ctx = multiprocessing.get_context("spawn")
    with ctx.Manager() as manager:
        state = manager.dict(writes=manager.list())
        barrier = ctx.Barrier(2)
        results = ctx.Queue()
        workers = [ctx.Process(target=race_worker, args=(str(tmp_path), state, barrier, results)) for _ in range(2)]
        try:
            for worker in workers:
                worker.start()
            answers = [results.get(timeout=20) for _ in workers]
            for worker in workers:
                worker.join(10)
                assert worker.exitcode == 0
            assert all(ok for ok, _ in answers), answers
            assert len(state["writes"]) == 1, "first-use callers overwrote the key"
            reader = make_protector(MemoryBackend(state))
            assert [reader.unprotect(value, "audit") for _, value in answers] == [b"synthetic"] * 2
            # Lock artifacts must never contain raw or encoded key material.
            key = state["key"]
            for path in tmp_path.rglob("*"):
                if path.is_file():
                    assert key.encode() not in path.read_bytes()
                    assert base64.urlsafe_b64decode(key) not in path.read_bytes()
        finally:
            for worker in workers:
                if worker.is_alive():
                    worker.terminate()
                    worker.join(5)
            results.close()


def lock_path(home):
    digest = hashlib.sha256(b"LocalAnonymizer\0synthetic-audit").hexdigest()
    return home / f".local-anonymizer-keyring-{digest}.lock"


def test_abandoned_lock_times_out_without_stealing(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    path = lock_path(tmp_path)
    path.mkdir()
    clock = iter([0, 6])
    monkeypatch.setattr(platform_services.time, "monotonic", lambda: next(clock))
    state = {"writes": []}
    with pytest.raises(DataProtectionUnavailable, match="блокиров"):
        make_protector(MemoryBackend(state)).protect(b"synthetic", "audit")
    assert state == {"writes": []}
    assert path.is_dir()


def test_existing_key_and_decryption_do_not_need_creation_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    lock_path(tmp_path).mkdir()
    state = {"writes": [], "key": base64.b64encode(b"x" * 32).decode()}
    protector = make_protector(MemoryBackend(state))
    envelope = protector.protect(b"synthetic", "audit")
    assert protector.unprotect(envelope, "audit") == b"synthetic"
    del state["key"]
    with pytest.raises(DataProtectionUnavailable, match="не найден"):
        protector.unprotect(envelope, "audit")
    assert state == {"writes": []}


def test_creation_lock_private_and_released_on_backend_error(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    modes = []
    original = Path.mkdir

    def tracked(path, mode=0o777, **kwargs):
        modes.append(mode)
        return original(path, mode=mode, **kwargs)

    monkeypatch.setattr(Path, "mkdir", tracked)
    backend = MemoryBackend({"writes": []})

    def denied(*args):
        assert lock_path(tmp_path).is_dir()
        raise RuntimeError("synthetic keyring locked")

    monkeypatch.setattr(backend, "set_password", denied)
    with pytest.raises(DataProtectionUnavailable):
        make_protector(backend).protect(b"synthetic", "audit")
    assert modes == [0o700]
    assert not lock_path(tmp_path).exists()


def test_invalid_generated_key_never_reaches_keyring(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    state = {"writes": []}
    protector = make_protector(MemoryBackend(state))
    protector._random_bytes = lambda size: b"x" * (31 if size == 32 else size)
    with pytest.raises(DataProtectionUnavailable):
        protector.protect(b"synthetic", "audit")
    assert state == {"writes": []}
    assert not lock_path(tmp_path).exists()
