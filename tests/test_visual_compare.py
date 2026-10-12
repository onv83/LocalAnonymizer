import sys
import types

import pytest

from local_anonymizer.visual_regression import compare_layout_signatures, export_office_pdf


def _signature(
    *,
    lines=10,
    images=1,
    raster=(0.1, 0.2, 0.3),
    text_bboxes=((40.0, 100.0, 240.0, 112.0),),
):
    return {
        "pages": [
            {
                "width": 595.0,
                "height": 842.0,
                "text_lines": lines,
                "text_bboxes": [list(bbox) for bbox in text_bboxes],
                "images": [{"bbox": [20.0, 30.0, 120.0, 130.0]}] * images,
                "drawings": [{"bbox": [10.0, 200.0, 580.0, 400.0]}],
                "raster": list(raster),
            }
        ]
    }


def test_visual_compare_accepts_matching_layout_with_small_render_noise():
    report = compare_layout_signatures(
        _signature(),
        _signature(raster=(0.101, 0.198, 0.302)),
        max_raster_delta=0.01,
    )

    assert report["ok"] is True
    assert report["issues"] == []


@pytest.mark.parametrize(
    ("candidate", "issue"),
    [
        ({"pages": []}, "page-count"),
        (_signature(lines=12), "text-lines"),
        (_signature(images=0), "images"),
        (_signature(raster=(0.9, 0.9, 0.9)), "render-delta"),
    ],
)
def test_visual_compare_rejects_layout_regressions(candidate, issue):
    report = compare_layout_signatures(
        _signature(), candidate, max_line_delta=0, max_raster_delta=0.05
    )

    assert report["ok"] is False
    assert any(item["kind"] == issue for item in report["issues"])


def test_visual_compare_rejects_material_text_displacement():
    report = compare_layout_signatures(
        _signature(text_bboxes=((40.0, 100.0, 240.0, 112.0),)),
        _signature(text_bboxes=((40.0, 160.0, 240.0, 172.0),)),
    )

    assert report["ok"] is False
    assert any(item["kind"] == "text-bbox" for item in report["issues"])


def test_word_pdf_export_disables_macros_and_link_updates(tmp_path, monkeypatch):
    source = tmp_path / "source.docx"
    source.write_bytes(b"fixture")
    destination = tmp_path / "source.pdf"
    calls = {}

    class FakeDocument:
        def ExportAsFixedFormat(self, *args, **kwargs):
            calls["export"] = (args, kwargs)

        def Close(self, save):
            calls["close"] = save

    class FakeDocuments:
        def Open(self, path, **kwargs):
            calls["open"] = (path, kwargs)
            return FakeDocument()

    class FakeWord:
        def __init__(self):
            self.Documents = FakeDocuments()
            self.Options = types.SimpleNamespace(UpdateLinksAtOpen=True)
            self.AutomationSecurity = None
            self.DisplayAlerts = None
            self.Visible = None

        def Quit(self):
            calls["quit"] = True

    word = FakeWord()
    pythoncom = types.SimpleNamespace(
        CoInitialize=lambda: calls.setdefault("coinitialize", True),
        CoUninitialize=lambda: calls.setdefault("couninitialize", True),
    )
    client = types.SimpleNamespace(DispatchEx=lambda name: word)
    monkeypatch.setitem(sys.modules, "pythoncom", pythoncom)
    monkeypatch.setitem(sys.modules, "win32com", types.SimpleNamespace(client=client))
    monkeypatch.setitem(sys.modules, "win32com.client", client)

    export_office_pdf(source, destination)

    assert word.AutomationSecurity == 3
    assert word.Options.UpdateLinksAtOpen is False
    assert calls["open"][1]["ReadOnly"] is True
    assert calls["open"][1]["AddToRecentFiles"] is False
    assert calls["open"][1]["OpenAndRepair"] is False
    assert calls["close"] is False
    assert calls["quit"] is True
    assert calls["couninitialize"] is True


def test_office_cleanup_runs_all_stages_when_close_raises(tmp_path, monkeypatch):
    source = tmp_path / "source.docx"
    source.write_bytes(b"fixture")
    calls = []

    class FakeDocument:
        def ExportAsFixedFormat(self, *args, **kwargs):
            calls.append("export")

        def Close(self, save):
            calls.append("close")
            raise RuntimeError("close failed")

    class FakeDocuments:
        def Open(self, path, **kwargs):
            return FakeDocument()

    class FakeWord:
        def __init__(self):
            self.Documents = FakeDocuments()
            self.Options = types.SimpleNamespace(UpdateLinksAtOpen=True)

        def Quit(self):
            calls.append("quit")

    pythoncom = types.SimpleNamespace(
        CoInitialize=lambda: calls.append("initialize"),
        CoUninitialize=lambda: calls.append("uninitialize"),
    )
    client = types.SimpleNamespace(DispatchEx=lambda name: FakeWord())
    monkeypatch.setitem(sys.modules, "pythoncom", pythoncom)
    monkeypatch.setitem(sys.modules, "win32com", types.SimpleNamespace(client=client))
    monkeypatch.setitem(sys.modules, "win32com.client", client)

    with pytest.raises(RuntimeError, match="close failed"):
        export_office_pdf(source, tmp_path / "source.pdf")

    assert calls[-3:] == ["close", "quit", "uninitialize"]


def test_office_cleanup_preserves_primary_export_error(tmp_path, monkeypatch):
    source = tmp_path / "source.docx"
    source.write_bytes(b"fixture")
    calls = []

    class FakeDocument:
        def ExportAsFixedFormat(self, *args, **kwargs):
            raise ValueError("export failed")

        def Close(self, save):
            calls.append("close")
            raise RuntimeError("close failed")

    class FakeDocuments:
        def Open(self, path, **kwargs):
            return FakeDocument()

    class FakeWord:
        def __init__(self):
            self.Documents = FakeDocuments()
            self.Options = types.SimpleNamespace(UpdateLinksAtOpen=True)

        def Quit(self):
            calls.append("quit")

    pythoncom = types.SimpleNamespace(
        CoInitialize=lambda: None,
        CoUninitialize=lambda: calls.append("uninitialize"),
    )
    client = types.SimpleNamespace(DispatchEx=lambda name: FakeWord())
    monkeypatch.setitem(sys.modules, "pythoncom", pythoncom)
    monkeypatch.setitem(sys.modules, "win32com", types.SimpleNamespace(client=client))
    monkeypatch.setitem(sys.modules, "win32com.client", client)

    with pytest.raises(ValueError, match="export failed"):
        export_office_pdf(source, tmp_path / "source.pdf")

    assert calls == ["close", "quit", "uninitialize"]
