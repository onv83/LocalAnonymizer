"""Regressions for B61/B62: bridge preview isolation and settings races."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import time
from pathlib import Path

import pytest

from local_anonymizer.app import AppApi


def test_concurrent_settings_updates_preserve_all_keys(api, monkeypatch):
    other = AppApi(root=api.service.storage.root)
    original = AppApi._read_ui_settings
    def slow_read(self):
        result = original(self)
        time.sleep(0.02)
        return result
    monkeypatch.setattr(AppApi, "_read_ui_settings", slow_read)
    barrier = threading.Barrier(12)
    def update(i):
        barrier.wait(timeout=5)
        (api if i % 2 else other)._write_ui_settings(**{f"key{i}": i})
    try:
        with ThreadPoolExecutor(max_workers=12) as pool:
            list(pool.map(update, range(12)))
        assert original(api) == {f"key{i}": i for i in range(12)}
        assert json.loads((api.service.storage.root / "ui-settings.json").read_text()) == original(api)
    finally:
        other.service.storage.connection.close()


def test_settings_use_unique_atomic_temp_and_clean_up_on_failure(api, monkeypatch):
    api.set_theme("dark")
    root = api.service.storage.root
    sentinel = root / "ui-settings.tmp"
    sentinel.write_text("unrelated")
    original = Path.replace
    seen = []
    def replace(source, target):
        if Path(target).name == "ui-settings.json":
            seen.append(source)
            assert source != sentinel
            assert source.parent == root
            assert json.loads(source.read_text())["language"] == "en"
            if len(seen) == 2:
                raise OSError("simulated replace failure")
        return original(source, target)
    monkeypatch.setattr(Path, "replace", replace)
    api.set_language("en")
    with pytest.raises(OSError, match="simulated"):
        api.set_language("en")
    assert len(set(seen)) == 2
    assert all(not path.exists() for path in seen)
    assert sentinel.read_text() == "unrelated"
    assert api.get_theme() == "dark"
    assert api.get_language() == "en"


@pytest.fixture
def api(tmp_path, monkeypatch):
    instance = AppApi(root=tmp_path / "app")
    monkeypatch.setattr(instance.service, "preview_document", lambda doc, **kw: {
        "text": "source:" + doc, "rich_html": "<p>source:" + doc + "</p>"
    })
    monkeypatch.setattr(instance, "preview_anonymized_document", lambda doc, *a, **kw: {
        "rich_html": "<p>anonymous:" + doc + "</p>"
    })
    yield instance
    instance.service.storage.connection.close()


def test_preview_cache_evicts_oldest_at_capacity(api, monkeypatch):
    monkeypatch.setattr(AppApi, "_PREVIEW_CACHE_LIMIT", 2, raising=False)
    tokens = [api.start_document_preview(str(i))["token"] for i in range(3)]
    try:
        with pytest.raises(ValueError, match="устарел"):
            api.read_document_preview_chunk(tokens[0], "text", 0)
        for i in (1, 2):
            assert api.read_document_preview_chunk(tokens[i], "text", 0)["chunk"] == f"source:{i}"
        assert len(api._ui_previews) == 2
    finally:
        for token in tokens:
            api.finish_document_preview(token)


def test_overlapping_preview_kinds_keep_independent_tokens(api):
    source = api.start_document_preview("first")["token"]
    formatted = api.start_formatted_document_preview("second")["token"]
    anonymous = api.start_anonymized_document_preview("third")["token"]
    try:
        assert api.read_document_preview_chunk(source, "text", 0)["chunk"] == "source:first"
        assert api.read_document_preview_chunk(formatted, "rich_html", 0)["chunk"] == "<p>source:second</p>"
        api.finish_document_preview(formatted)
        with pytest.raises(ValueError, match="устарел"):
            api.read_document_preview_chunk(formatted, "rich_html", 0)
        assert api.read_document_preview_chunk(anonymous, "rich_html", 0)["chunk"] == "<p>anonymous:third</p>"
        assert api.read_document_preview_chunk(source, "text", 0)["chunk"] == "source:first"
    finally:
        for token in (source, formatted, anonymous):
            api.finish_document_preview(token)


def test_abandoned_preview_is_erased_without_more_requests(api, monkeypatch):
    monkeypatch.setattr(AppApi, "_PREVIEW_TTL_SECONDS", 0.05, raising=False)
    token = api.start_document_preview("sensitive")["token"]
    deadline = time.monotonic() + 2
    while api._ui_previews and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not api._ui_previews
    with pytest.raises(ValueError, match="устарел"):
        api.read_document_preview_chunk(token, "text", 0)
