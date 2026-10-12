from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path
from typing import Any


def _bbox_delta(left: list[float], right: list[float]) -> float:
    if len(left) != 4 or len(right) != 4:
        return math.inf
    return max(abs(float(a) - float(b)) for a, b in zip(left, right))


def compare_layout_signatures(
    source: dict[str, Any],
    candidate: dict[str, Any],
    *,
    max_line_delta: int = 0,
    max_bbox_delta: float = 2.0,
    max_raster_delta: float = 0.08,
) -> dict[str, Any]:
    """Compare page geometry and a coarse raster signature, not document text."""
    source_pages = list(source.get("pages") or [])
    candidate_pages = list(candidate.get("pages") or [])
    issues: list[dict[str, Any]] = []
    page_reports: list[dict[str, Any]] = []
    if len(source_pages) != len(candidate_pages):
        issues.append(
            {
                "kind": "page-count",
                "source": len(source_pages),
                "candidate": len(candidate_pages),
            }
        )

    for index, (left, right) in enumerate(zip(source_pages, candidate_pages), start=1):
        page_issues: list[dict[str, Any]] = []
        size_delta = max(
            abs(float(left.get("width", 0)) - float(right.get("width", 0))),
            abs(float(left.get("height", 0)) - float(right.get("height", 0))),
        )
        if size_delta > max_bbox_delta:
            page_issues.append({"kind": "page-size", "delta": size_delta})

        line_delta = abs(int(left.get("text_lines", 0)) - int(right.get("text_lines", 0)))
        if line_delta > max_line_delta:
            page_issues.append({"kind": "text-lines", "delta": line_delta})

        left_text = list(left.get("text_bboxes") or [])
        right_text = list(right.get("text_bboxes") or [])
        if len(left_text) != len(right_text):
            text_bbox_delta = math.inf
            page_issues.append(
                {"kind": "text-bboxes", "source": len(left_text), "candidate": len(right_text)}
            )
        else:
            text_bbox_delta = max(
                (_bbox_delta(a, b) for a, b in zip(left_text, right_text)),
                default=0.0,
            )
            if text_bbox_delta > max_bbox_delta:
                page_issues.append({"kind": "text-bbox", "delta": text_bbox_delta})

        for kind in ("images", "drawings"):
            left_items = list(left.get(kind) or [])
            right_items = list(right.get(kind) or [])
            if len(left_items) != len(right_items):
                page_issues.append(
                    {"kind": kind, "source": len(left_items), "candidate": len(right_items)}
                )
                continue
            largest = max(
                (_bbox_delta(a.get("bbox", []), b.get("bbox", [])) for a, b in zip(left_items, right_items)),
                default=0.0,
            )
            if largest > max_bbox_delta:
                page_issues.append({"kind": f"{kind}-bbox", "delta": largest})

        left_raster = [float(value) for value in left.get("raster") or []]
        right_raster = [float(value) for value in right.get("raster") or []]
        if len(left_raster) != len(right_raster):
            raster_delta = math.inf
        elif not left_raster:
            raster_delta = 0.0
        else:
            raster_delta = sum(abs(a - b) for a, b in zip(left_raster, right_raster)) / len(left_raster)
        if raster_delta > max_raster_delta:
            page_issues.append({"kind": "render-delta", "delta": raster_delta})

        for item in page_issues:
            issues.append({"page": index, **item})
        page_reports.append(
            {
                "page": index,
                "line_delta": line_delta,
                "text_bbox_delta": text_bbox_delta,
                "size_delta": size_delta,
                "raster_delta": raster_delta,
                "ok": not page_issues,
            }
        )

    return {
        "ok": not issues,
        "source_pages": len(source_pages),
        "candidate_pages": len(candidate_pages),
        "pages": page_reports,
        "issues": issues,
    }


def _coarse_raster(page, *, grid: int = 24) -> list[float]:
    import pymupdf as fitz

    pixmap = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5), colorspace=fitz.csGRAY, alpha=False)
    width, height = pixmap.width, pixmap.height
    samples = pixmap.samples
    values: list[float] = []
    for gy in range(grid):
        y0, y1 = gy * height // grid, (gy + 1) * height // grid
        for gx in range(grid):
            x0, x1 = gx * width // grid, (gx + 1) * width // grid
            total = count = 0
            for y in range(y0, y1):
                row = y * width
                for x in range(x0, x1):
                    total += 255 - samples[row + x]
                    count += 1
            values.append(round(total / (255 * count), 6) if count else 0.0)
    return values


def pdf_layout_signature(path: str | Path) -> dict[str, Any]:
    import pymupdf as fitz

    pages: list[dict[str, Any]] = []
    with fitz.open(str(Path(path))) as document:
        for page in document:
            blocks = page.get_text("dict").get("blocks", [])
            text_lines = sum(len(block.get("lines", [])) for block in blocks if block.get("type") == 0)
            text_bboxes = [
                [round(float(value), 3) for value in line.get("bbox", ())]
                for block in blocks
                if block.get("type") == 0
                for line in block.get("lines", [])
            ]
            images = [
                {"bbox": [round(float(value), 3) for value in block.get("bbox", ())]}
                for block in blocks
                if block.get("type") == 1
            ]
            drawings = [
                {"bbox": [round(float(value), 3) for value in drawing["rect"]]}
                for drawing in page.get_drawings()
                if drawing.get("rect") is not None
            ]
            pages.append(
                {
                    "width": round(float(page.rect.width), 3),
                    "height": round(float(page.rect.height), 3),
                    "text_lines": text_lines,
                    "text_bboxes": text_bboxes,
                    "images": images,
                    "drawings": drawings,
                    "raster": _coarse_raster(page),
                }
            )
    return {"pages": pages}


def export_office_pdf(source: str | Path, destination: str | Path) -> None:
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    suffix = source.suffix.lower()
    if suffix not in {".docx", ".xlsx"}:
        raise ValueError("Визуальное сравнение поддерживает только DOCX и XLSX")

    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    application = document = None
    try:
        if suffix == ".docx":
            application = win32com.client.DispatchEx("Word.Application")
            application.Visible = False
            application.DisplayAlerts = 0
            application.AutomationSecurity = 3
            application.Options.UpdateLinksAtOpen = False
            document = application.Documents.Open(
                str(source), ConfirmConversions=False, ReadOnly=True,
                AddToRecentFiles=False, Visible=False, OpenAndRepair=False,
                NoEncodingDialog=True,
            )
            document.ExportAsFixedFormat(
                str(destination), 17, OpenAfterExport=False, OptimizeFor=0,
                Range=0, Item=0, IncludeDocProps=False, KeepIRM=False,
                CreateBookmarks=0, DocStructureTags=True,
                BitmapMissingFonts=True, UseISO19005_1=False,
            )
        else:
            application = win32com.client.DispatchEx("Excel.Application")
            application.Visible = False
            application.DisplayAlerts = False
            application.AutomationSecurity = 3
            document = application.Workbooks.Open(
                str(source), UpdateLinks=0, ReadOnly=True,
                IgnoreReadOnlyRecommended=True, AddToMru=False,
            )
            document.ExportAsFixedFormat(
                0, str(destination), Quality=0, IncludeDocProperties=False,
                IgnorePrintAreas=False, OpenAfterPublish=False,
            )
    finally:
        primary_exception_active = sys.exc_info()[0] is not None
        cleanup_error = None
        if document is not None:
            try:
                document.Close(False)
            except Exception as exc:
                cleanup_error = exc
        if application is not None:
            try:
                application.Quit()
            except Exception as exc:
                if cleanup_error is None:
                    cleanup_error = exc
        try:
            pythoncom.CoUninitialize()
        except Exception as exc:
            if cleanup_error is None:
                cleanup_error = exc
        if cleanup_error is not None and not primary_exception_active:
            raise cleanup_error


def compare_office_documents(
    source: str | Path,
    candidate: str | Path,
    *,
    max_line_delta: int = 0,
    max_bbox_delta: float = 2.0,
    max_raster_delta: float = 0.08,
) -> dict[str, Any]:
    source = Path(source)
    candidate = Path(candidate)
    if source.suffix.lower() != candidate.suffix.lower():
        raise ValueError("Форматы исходного и проверяемого документов должны совпадать")
    with tempfile.TemporaryDirectory(prefix="local-anonymizer-visual-") as directory:
        root = Path(directory)
        source_pdf = root / "source.pdf"
        candidate_pdf = root / "candidate.pdf"
        export_office_pdf(source, source_pdf)
        export_office_pdf(candidate, candidate_pdf)
        return compare_layout_signatures(
            pdf_layout_signature(source_pdf),
            pdf_layout_signature(candidate_pdf),
            max_line_delta=max_line_delta,
            max_bbox_delta=max_bbox_delta,
            max_raster_delta=max_raster_delta,
        )
