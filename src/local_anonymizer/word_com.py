from __future__ import annotations

import os
import tempfile
from pathlib import Path


def convert_doc_to_docx(source: str | Path, output: str | Path, *, dispatch=None) -> Path:
    source, output = Path(source).resolve(), Path(output).resolve()
    if source.suffix.lower() != ".doc":
        raise ValueError("Ожидается файл .doc")
    if output.suffix.lower() != ".docx" or source == output:
        raise ValueError("Выход должен быть новым файлом .docx")
    try:
        import pythoncom
    except Exception as exc:
        raise RuntimeError("Microsoft Word automation недоступен") from exc
    if dispatch is None:
        try:
            from win32com.client import DispatchEx
            dispatch = DispatchEx
        except Exception as exc:
            raise RuntimeError("Microsoft Word automation недоступен") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{output.stem}-", suffix=".docx", dir=output.parent); os.close(fd)
    Path(temp_name).unlink(missing_ok=True)
    word = document = None
    com_initialized = False
    try:
        pythoncom.CoInitialize()
        com_initialized = True
        word = dispatch("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        word.AutomationSecurity = 3  # msoAutomationSecurityForceDisable
        try:
            word.Options.UpdateLinksAtOpen = False
        except Exception:
            pass
        document = word.Documents.Open(str(source), ReadOnly=True, AddToRecentFiles=False,
                                       ConfirmConversions=False, Revert=False)
        try:
            document.UpdateStylesOnOpen = False
        except Exception:
            pass
        document.SaveAs2(str(Path(temp_name)), FileFormat=16)  # wdFormatDocumentDefault (.docx)
        # Word keeps the SaveAs target locked until the document is closed.
        document.Close(SaveChanges=False)
        document = None
        os.replace(temp_name, output)
        return output
    except Exception as exc:
        raise RuntimeError("Не удалось безопасно преобразовать .doc через Microsoft Word") from exc
    finally:
        if document is not None:
            try: document.Close(SaveChanges=False)
            except Exception: pass
        if word is not None:
            try: word.Quit()
            except Exception: pass
        if com_initialized:
            try: pythoncom.CoUninitialize()
            except Exception: pass
        Path(temp_name).unlink(missing_ok=True)
