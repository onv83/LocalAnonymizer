import ast
from pathlib import Path
from zipfile import ZipFile

from docx import Document

from local_anonymizer.documents import DocxProcessor
from scripts.release_verify import build_acceptance_source


def test_release_acceptance_document_contains_visible_graphic_and_round_trips_exactly(tmp_path):
    source = tmp_path / "acceptance-source.docx"
    anonymized = tmp_path / "acceptance-anonymized.docx"
    restored = tmp_path / "acceptance-restored.docx"

    image_bytes = build_acceptance_source(
        source,
        Path("acceptance_sample.txt"),
        Path("docs/images/acceptance-diagram.png"),
    )

    source_document = Document(source)
    assert len(source_document.inline_shapes) == 1
    with ZipFile(source) as package:
        embedded_images = [
            package.read(name)
            for name in package.namelist()
            if name.startswith("word/media/")
        ]
    assert embedded_images == [image_bytes]

    result = DocxProcessor().anonymize(source, anonymized)
    with ZipFile(anonymized) as package:
        assert not any(name.startswith("word/media/") for name in package.namelist())
        assert "[СХЕМА-1]".encode("utf-8") in package.read("word/document.xml")

    DocxProcessor().restore(
        anonymized,
        restored,
        result.mapping,
        package_archive=result.package_archive,
    )

    assert restored.read_bytes() == source.read_bytes()
    with ZipFile(restored) as package:
        restored_images = [
            package.read(name)
            for name in package.namelist()
            if name.startswith("word/media/")
        ]
    assert restored_images == [image_bytes]


def test_release_verifier_uses_explicit_checks_that_survive_python_optimization():
    verifier = Path("scripts/release_verify.py")
    tree = ast.parse(verifier.read_text(encoding="utf-8"))

    assert not [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Assert)]
