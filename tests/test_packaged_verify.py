from pathlib import Path

import pytest

from scripts.verify_packaged import (
    VerificationError,
    validate_pair_smoke,
    validate_platform_smoke,
    validate_smoke,
)


def test_packaged_smoke_rejects_a_stale_executable_without_port_gate():
    stale_payload = {
        "ok": True,
        "engine": {
            "ok": True,
            "vm_node_ok": True,
            "abbreviation_ok": True,
            "abbreviation_unicode_ok": True,
            "domain_toc_ok": True,
            "graphics_roundtrip_ok": True,
        },
    }

    with pytest.raises(VerificationError, match="port_ok"):
        validate_smoke(stale_payload)


def test_packaged_smoke_accepts_all_required_fail_closed_results():
    validate_smoke({
        "ok": True,
        "engine": {
            "ok": True,
            "vm_node_ok": True,
            "abbreviation_ok": True,
            "abbreviation_unicode_ok": True,
            "domain_toc_ok": True,
            "port_ok": True,
            "graphics_roundtrip_ok": True,
        },
    })
    validate_pair_smoke({
        "ok": True,
        "pair_found_after_library_delete": True,
        "recovery_contains_sensitive_mapping": True,
        "restored_exactly": True,
    })
    validate_platform_smoke({
        "ok": True,
        "secure_storage": True,
        "clipboard": True,
    })


def test_native_build_wrappers_run_the_external_packaged_verifier():
    windows = Path("build.bat").read_text(encoding="utf-8")
    assert "scripts\\verify_packaged.py" in windows
    assert "--workpath" in windows and "build\\pyinstaller-current" in windows
    assert '--distpath "build\\pyinstaller-output"' in windows
    assert windows.count("scripts\\verify_packaged.py") == 2
    assert "scripts/verify_packaged.py" in Path("verify-native.sh").read_text(encoding="utf-8")
