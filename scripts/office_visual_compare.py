from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from local_anonymizer.visual_regression import compare_office_documents


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Сравнить компоновку DOCX/XLSX через PDF, созданные Word/Excel."
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--max-line-delta", type=int, default=0)
    parser.add_argument("--max-bbox-delta", type=float, default=2.0)
    parser.add_argument("--max-raster-delta", type=float, default=0.08)
    args = parser.parse_args()
    try:
        report = compare_office_documents(
            args.source,
            args.candidate,
            max_line_delta=args.max_line_delta,
            max_bbox_delta=args.max_bbox_delta,
            max_raster_delta=args.max_raster_delta,
        )
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error": type(exc).__name__, "message": str(exc)},
                ensure_ascii=False,
            )
        )
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
