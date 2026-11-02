from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "local_anonymizer" / "assets"


def test_current_interfaces_do_not_offer_in_place_value_restoration() -> None:
    """The obsolete text-only restore control must not return in the current UI."""
    for name in ("index-v1.8.20.html", "index-en-v1.8.20.html"):
        content = (ASSETS / name).read_text(encoding="utf-8")
        assert 'id="restore"' not in content


def test_current_interfaces_disclose_normal_secret_recovery() -> None:
    russian = (ASSETS / "index-v1.8.20.html").read_text(encoding="utf-8")
    english = (ASSETS / "index-en-v1.8.20.html").read_text(encoding="utf-8")
    assert "включая значения, помеченные как секреты" in russian
    assert "восстанавливает их обычным механизмом" in russian
    assert "including values marked as secrets" in english
    assert "ordinary recovery mechanism" in english


def test_current_bridge_does_not_expose_text_only_restore() -> None:
    """Document-pair restoration remains separate from the removed text control."""
    content = (ROOT / "src" / "local_anonymizer" / "app.py").read_text(encoding="utf-8")
    assert "def restore_text(" not in content
