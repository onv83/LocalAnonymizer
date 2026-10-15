from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from local_anonymizer.word_com import convert_doc_to_docx
import local_anonymizer.word_com as word_com


pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Word COM hardening is Windows-only",
)


class FakeDocument:
    def __init__(self, fail=False): self.fail=fail; self.closed=False
    def SaveAs2(self, path, FileFormat):
        if self.fail: raise RuntimeError("save")
        Path(path).write_bytes(b"docx")
    def Close(self, SaveChanges=False): self.closed=True


class FakeWord:
    def __init__(self, document):
        self.document=document; self.quit=False; self.DisplayAlerts=99; self.AutomationSecurity=0
        self.Options=SimpleNamespace(UpdateLinksAtOpen=True)
        self.Documents=SimpleNamespace(Open=self.open)
    def open(self, path, **kwargs):
        self.open_kwargs=kwargs; return self.document
    def Quit(self): self.quit=True


def test_doc_conversion_locks_down_word_and_closes_on_success(tmp_path):
    source = tmp_path/"a.doc"; source.write_bytes(b"legacy")
    doc = FakeDocument(); word = FakeWord(doc)
    out = convert_doc_to_docx(source, tmp_path/"a.docx", dispatch=lambda _: word)
    assert out.exists() and doc.closed and word.quit
    assert word.DisplayAlerts == 0 and word.AutomationSecurity == 3
    assert word.Options.UpdateLinksAtOpen is False
    assert word.open_kwargs["ReadOnly"] is True and word.open_kwargs["AddToRecentFiles"] is False
    assert "UpdateLinks" not in word.open_kwargs


def test_doc_conversion_always_closes_on_error(tmp_path):
    source = tmp_path/"a.doc"; source.write_bytes(b"legacy")
    doc = FakeDocument(True); word = FakeWord(doc)
    with pytest.raises(RuntimeError): convert_doc_to_docx(source, tmp_path/"a.docx", dispatch=lambda _: word)
    assert doc.closed and word.quit


def test_doc_conversion_initializes_com_for_pywebview_worker_thread(tmp_path, monkeypatch):
    calls = []
    pythoncom = SimpleNamespace(
        CoInitialize=lambda: calls.append("initialize"),
        CoUninitialize=lambda: calls.append("uninitialize"),
    )
    monkeypatch.setitem(sys.modules, "pythoncom", pythoncom)
    source = tmp_path / "worker.doc"
    source.write_bytes(b"legacy")
    doc = FakeDocument()
    word = FakeWord(doc)

    convert_doc_to_docx(source, tmp_path / "worker.docx", dispatch=lambda _: word)

    assert calls == ["initialize", "uninitialize"]
    assert doc.closed and word.quit


def test_doc_conversion_closes_saved_document_before_replacing_temp_file(tmp_path, monkeypatch):
    source = tmp_path / "locked.doc"
    source.write_bytes(b"legacy")
    doc = FakeDocument()
    word = FakeWord(doc)
    real_replace = word_com.os.replace

    def replace_only_after_word_releases_file(source_path, destination_path):
        if not doc.closed:
            raise PermissionError("Word still holds the converted file")
        real_replace(source_path, destination_path)

    monkeypatch.setattr(word_com.os, "replace", replace_only_after_word_releases_file)

    output = convert_doc_to_docx(source, tmp_path / "locked.docx", dispatch=lambda _: word)

    assert output.read_bytes() == b"docx"
    assert doc.closed and word.quit
