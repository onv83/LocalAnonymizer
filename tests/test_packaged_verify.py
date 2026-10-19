import hashlib
import json
from pathlib import Path

import pytest

from scripts.build_provenance import write_provenance_module
from scripts.verify_packaged import (
    VerificationError,
    build_package_manifest,
    source_snapshot_sha256,
    validate_package_manifest,
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
            "abbreviation_single_two_letter_ok": True,
            "domain_toc_ok": True,
            "port_ok": True,
            "address_inventory_ok": True,
            "address_postal_variants_ok": True,
            "address_contextual_variants_ok": True,
            "compound_policy_abbreviation_ok": True,
            "hyphenated_abbreviation_hint_precedence_ok": True,
            "prefixed_lowercase_compound_abbreviation_ok": True,
            "dotted_version_compound_abbreviation_ok": True,
            "contextual_location_table_ok": True,
            "server_inventory_name_ok": True,
            "split_server_inventory_name_ok": True,
            "semantic_server_capacity_node_ok": True,
            "underscored_dns_fqdn_ok": True,
            "domain_inventory_row_ok": True,
            "device_inventory_identifier_ok": True,
            "service_account_ok": True,
            "split_service_account_ok": True,
            "graphics_roundtrip_ok": True,
            "domain_inventory_subject_ok": True,
            "source_snapshot_sha256": "a" * 64,
            "git_revision": "b" * 40,
            "git_diff_sha256": "c" * 64,
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


@pytest.mark.parametrize("missing", (
    "compound_policy_abbreviation_ok", "hyphenated_abbreviation_hint_precedence_ok",
    "prefixed_lowercase_compound_abbreviation_ok",
    "dotted_version_compound_abbreviation_ok",
    "contextual_location_table_ok",
    "split_server_inventory_name_ok", "semantic_server_capacity_node_ok",
    "underscored_dns_fqdn_ok",
    "domain_inventory_subject_ok", "domain_inventory_row_ok",
    "device_inventory_identifier_ok", "service_account_ok", "split_service_account_ok",
))
def test_packaged_smoke_rejects_build_without_new_detector_proofs(missing):
    required = (
        "ok", "vm_node_ok", "abbreviation_ok", "abbreviation_unicode_ok",
        "abbreviation_single_two_letter_ok", "domain_toc_ok", "port_ok",
        "address_inventory_ok", "address_postal_variants_ok",
        "address_contextual_variants_ok", "compound_policy_abbreviation_ok",
        "hyphenated_abbreviation_hint_precedence_ok",
        "prefixed_lowercase_compound_abbreviation_ok",
        "dotted_version_compound_abbreviation_ok",
        "contextual_location_table_ok", "server_inventory_name_ok",
        "split_server_inventory_name_ok", "semantic_server_capacity_node_ok",
        "underscored_dns_fqdn_ok", "service_account_ok",
        "split_service_account_ok",
        "graphics_roundtrip_ok", "domain_inventory_subject_ok", "domain_inventory_row_ok",
        "device_inventory_identifier_ok",
    )
    engine = {key: True for key in required if key != missing}
    engine.update({
        "source_snapshot_sha256": "a" * 64,
        "git_revision": "b" * 40,
        "git_diff_sha256": "c" * 64,
    })

    with pytest.raises(VerificationError, match=missing):
        validate_smoke({"ok": True, "engine": engine})


def test_packaged_smoke_rejects_stale_build_without_address_inventory_proof():
    payload = {
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
    }

    with pytest.raises(VerificationError, match="address_inventory_ok"):
        validate_smoke(payload)


def test_packaged_smoke_rejects_stale_build_without_complete_postal_address_proof():
    payload = {
        "ok": True,
        "engine": {
            "ok": True,
            "vm_node_ok": True,
            "abbreviation_ok": True,
            "abbreviation_unicode_ok": True,
            "domain_toc_ok": True,
            "port_ok": True,
            "address_inventory_ok": True,
            "graphics_roundtrip_ok": True,
            "source_snapshot_sha256": "a" * 64,
            "git_revision": "b" * 40,
            "git_diff_sha256": "c" * 64,
        },
    }

    with pytest.raises(VerificationError, match="address_postal_variants_ok"):
        validate_smoke(payload)


def test_packaged_smoke_rejects_stale_build_without_contextual_address_proof():
    payload = {
        "ok": True,
        "engine": {
            "ok": True,
            "vm_node_ok": True,
            "abbreviation_ok": True,
            "abbreviation_unicode_ok": True,
            "domain_toc_ok": True,
            "port_ok": True,
            "address_inventory_ok": True,
            "address_postal_variants_ok": True,
            "server_inventory_name_ok": True,
            "abbreviation_single_two_letter_ok": True,
            "graphics_roundtrip_ok": True,
            "source_snapshot_sha256": "a" * 64,
            "git_revision": "b" * 40,
            "git_diff_sha256": "c" * 64,
        },
    }

    with pytest.raises(VerificationError, match="address_contextual_variants_ok"):
        validate_smoke(payload)


def test_packaged_smoke_rejects_stale_build_without_server_inventory_name_proof():
    payload = {
        "ok": True,
        "engine": {
            "ok": True,
            "vm_node_ok": True,
            "abbreviation_ok": True,
            "abbreviation_unicode_ok": True,
            "domain_toc_ok": True,
            "port_ok": True,
            "address_inventory_ok": True,
            "address_postal_variants_ok": True,
            "address_contextual_variants_ok": True,
            "compound_policy_abbreviation_ok": True,
            "hyphenated_abbreviation_hint_precedence_ok": True,
            "prefixed_lowercase_compound_abbreviation_ok": True,
            "dotted_version_compound_abbreviation_ok": True,
            "contextual_location_table_ok": True,
            "graphics_roundtrip_ok": True,
            "source_snapshot_sha256": "a" * 64,
            "git_revision": "b" * 40,
            "git_diff_sha256": "c" * 64,
        },
    }

    with pytest.raises(VerificationError, match="server_inventory_name_ok"):
        validate_smoke(payload)


def test_packaged_smoke_rejects_stale_frequency_only_build_without_single_token_proof():
    payload = {
        "ok": True,
        "engine": {
            "ok": True,
            "vm_node_ok": True,
            "abbreviation_ok": True,
            "abbreviation_unicode_ok": True,
            "domain_toc_ok": True,
            "port_ok": True,
            "address_inventory_ok": True,
            "address_postal_variants_ok": True,
            "address_contextual_variants_ok": True,
            "compound_policy_abbreviation_ok": True,
            "hyphenated_abbreviation_hint_precedence_ok": True,
            "prefixed_lowercase_compound_abbreviation_ok": True,
            "dotted_version_compound_abbreviation_ok": True,
            "contextual_location_table_ok": True,
            "server_inventory_name_ok": True,
            "split_server_inventory_name_ok": True,
            "semantic_server_capacity_node_ok": True,
            "underscored_dns_fqdn_ok": True,
            "domain_inventory_subject_ok": True,
            "domain_inventory_row_ok": True,
            "device_inventory_identifier_ok": True,
            "service_account_ok": True,
            "split_service_account_ok": True,
            "graphics_roundtrip_ok": True,
            "source_snapshot_sha256": "a" * 64,
            "git_revision": "b" * 40,
            "git_diff_sha256": "c" * 64,
        },
    }

    with pytest.raises(VerificationError, match="abbreviation_single_two_letter_ok"):
        validate_smoke(payload)


def _fake_package(tmp_path: Path):
    root = tmp_path / "source"
    assets = root / "src" / "local_anonymizer" / "assets"
    assets.mkdir(parents=True)
    (root / "launcher.py").write_text("print('launch')\n", encoding="utf-8")
    (root / "LocalAnonymizer.spec").write_text("# spec\n", encoding="utf-8")
    (root / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (root / "src" / "local_anonymizer" / "engine.py").write_text("VALUE = 1\n", encoding="utf-8")
    (assets / "app-v1.8.18.js").write_text("const version = 1;\n", encoding="utf-8")
    package = tmp_path / "package"
    executable = package / "LocalAnonymizer.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"fresh executable")
    internal = package / "_internal"
    internal.mkdir(parents=True)
    (internal / "runtime.bin").write_bytes(b"fresh runtime")
    bundled = internal / "local_anonymizer" / "assets"
    bundled.mkdir(parents=True)
    (bundled / "app-v1.8.18.js").write_bytes((assets / "app-v1.8.18.js").read_bytes())
    return root, executable


def test_package_manifest_binds_executable_runtime_source_and_assets(tmp_path):
    root, executable = _fake_package(tmp_path)
    revision = "1" * 40
    diff_hash = "2" * 64
    engine = {
        "source_snapshot_sha256": source_snapshot_sha256(root),
        "git_revision": revision,
        "git_diff_sha256": diff_hash,
    }
    manifest = build_package_manifest(
        executable,
        engine,
        source_root=root,
        git_revision=revision,
        git_diff_sha256=diff_hash,
    )

    validate_package_manifest(
        executable,
        manifest,
        engine,
        source_root=root,
        git_revision=revision,
        git_diff_sha256=diff_hash,
    )

    executable.write_bytes(b"stale executable")
    with pytest.raises(VerificationError, match="executable SHA-256"):
        validate_package_manifest(
            executable, manifest, engine, source_root=root,
            git_revision=revision, git_diff_sha256=diff_hash,
        )


def test_package_manifest_binds_every_bundled_runtime_file(tmp_path):
    root, executable = _fake_package(tmp_path)
    revision = "7" * 40
    diff_hash = "8" * 64
    engine = {
        "source_snapshot_sha256": source_snapshot_sha256(root),
        "git_revision": revision,
        "git_diff_sha256": diff_hash,
    }
    manifest = build_package_manifest(
        executable,
        engine,
        source_root=root,
        git_revision=revision,
        git_diff_sha256=diff_hash,
    )

    runtime = executable.parent / "_internal" / "runtime.bin"
    assert manifest["files"]["_internal/runtime.bin"] == {
        "sha256": _sha256_for_test(runtime),
        "size": len(b"fresh runtime"),
    }

    runtime.write_bytes(b"tampered runtime")
    with pytest.raises(VerificationError, match="package file inventory"):
        validate_package_manifest(
            executable, manifest, engine, source_root=root,
            git_revision=revision, git_diff_sha256=diff_hash,
        )


def test_package_manifest_rejects_unmanifested_added_runtime_file(tmp_path):
    root, executable = _fake_package(tmp_path)
    revision = "9" * 40
    diff_hash = "a" * 64
    engine = {
        "source_snapshot_sha256": source_snapshot_sha256(root),
        "git_revision": revision,
        "git_diff_sha256": diff_hash,
    }
    manifest = build_package_manifest(
        executable,
        engine,
        source_root=root,
        git_revision=revision,
        git_diff_sha256=diff_hash,
    )

    (executable.parent / "_internal" / "injected.bin").write_bytes(b"unmanifested")
    with pytest.raises(VerificationError, match="package file inventory"):
        validate_package_manifest(
            executable, manifest, engine, source_root=root,
            git_revision=revision, git_diff_sha256=diff_hash,
        )


def test_package_manifest_can_be_verified_from_inside_the_package(tmp_path):
    root, executable = _fake_package(tmp_path)
    revision = "b" * 40
    diff_hash = "c" * 64
    engine = {
        "source_snapshot_sha256": source_snapshot_sha256(root),
        "git_revision": revision,
        "git_diff_sha256": diff_hash,
    }
    manifest = build_package_manifest(
        executable,
        engine,
        source_root=root,
        git_revision=revision,
        git_diff_sha256=diff_hash,
    )
    manifest_path = executable.parent / "LocalAnonymizer.manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    validate_package_manifest(
        executable,
        manifest,
        engine,
        source_root=root,
        git_revision=revision,
        git_diff_sha256=diff_hash,
        manifest_path=manifest_path,
    )


def _sha256_for_test(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_package_manifest_rejects_stale_source_asset_and_self_report(tmp_path):
    root, executable = _fake_package(tmp_path)
    revision = "3" * 40
    diff_hash = "4" * 64
    engine = {
        "source_snapshot_sha256": "0" * 64,
        "git_revision": revision,
        "git_diff_sha256": diff_hash,
    }
    with pytest.raises(VerificationError, match="self-reported source snapshot"):
        build_package_manifest(
            executable, engine, source_root=root,
            git_revision=revision, git_diff_sha256=diff_hash,
        )

    engine["source_snapshot_sha256"] = source_snapshot_sha256(root)
    manifest = build_package_manifest(
        executable, engine, source_root=root,
        git_revision=revision, git_diff_sha256=diff_hash,
    )
    (root / "src" / "local_anonymizer" / "assets" / "app-v1.8.18.js").write_text(
        "const version = 2;\n", encoding="utf-8"
    )
    with pytest.raises(VerificationError, match="source snapshot"):
        validate_package_manifest(
            executable, manifest, engine, source_root=root,
            git_revision=revision, git_diff_sha256=diff_hash,
        )


def test_build_provenance_module_embeds_the_exact_source_and_git_snapshot(tmp_path):
    root, _executable = _fake_package(tmp_path)
    destination = root / "src" / "local_anonymizer" / "_build_provenance.py"
    revision = "5" * 40
    diff_hash = "6" * 64

    payload = write_provenance_module(
        destination,
        source_root=root,
        git_revision=revision,
        git_diff_sha256=diff_hash,
    )

    source = destination.read_text(encoding="utf-8")
    assert payload == {
        "source_snapshot_sha256": source_snapshot_sha256(root),
        "git_revision": revision,
        "git_diff_sha256": diff_hash,
    }
    assert f'SOURCE_SNAPSHOT_SHA256 = "{payload["source_snapshot_sha256"]}"' in source
    assert f'GIT_REVISION = "{revision}"' in source
    assert f'GIT_DIFF_SHA256 = "{diff_hash}"' in source


def test_native_build_wrappers_run_the_external_packaged_verifier():
    windows = Path("build.bat").read_text(encoding="utf-8")
    assert "scripts\\verify_packaged.py" in windows
    assert "scripts\\build_provenance.py" in windows
    assert "--write-manifest" in windows
    assert "--manifest" in windows
    assert "--workpath" in windows and "build\\pyinstaller-current" in windows
    assert '--distpath "build\\pyinstaller-output"' in windows
    assert windows.count("scripts\\verify_packaged.py") == 2
    native = Path("verify-native.sh").read_text(encoding="utf-8")
    assert "scripts/verify_packaged.py" in native
    assert "--write-manifest" in native
