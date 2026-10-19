from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROVENANCE_MODULE = Path("src/local_anonymizer/_build_provenance.py")
_DIGEST_RE = re.compile(r"[0-9a-f]{64}")
_REVISION_RE = re.compile(r"[0-9a-f]{40,64}")


class VerificationError(RuntimeError):
    """The packaged application did not prove a required release invariant."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _require_true(payload: dict, key: str, scope: str) -> None:
    if payload.get(key) is not True:
        raise VerificationError(f"{scope}.{key} must be true")


def _require_digest(payload: dict, key: str, scope: str) -> None:
    value = payload.get(key)
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise VerificationError(f"{scope}.{key} must be a SHA-256 digest")


def _require_revision(payload: dict, key: str, scope: str) -> None:
    value = payload.get(key)
    if not isinstance(value, str) or _REVISION_RE.fullmatch(value) is None:
        raise VerificationError(f"{scope}.{key} must be a Git revision")


def validate_smoke(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise VerificationError("smoke payload must be an object")
    _require_true(payload, "ok", "smoke")
    engine = payload.get("engine")
    if not isinstance(engine, dict):
        raise VerificationError("smoke.engine must be an object")
    for key in (
        "ok",
        "vm_node_ok",
        "abbreviation_ok",
        "abbreviation_unicode_ok",
        "domain_toc_ok",
        "port_ok",
        "address_inventory_ok",
        "address_postal_variants_ok",
        "address_contextual_variants_ok",
        "compound_policy_abbreviation_ok",
        "mixed_separator_compound_abbreviation_ok",
        "inventory_style_abbreviation_ok",
        "intra_boundary_semantic_precedence_ok",
        "hyphenated_abbreviation_hint_precedence_ok",
        "prefixed_lowercase_compound_abbreviation_ok",
        "dotted_version_compound_abbreviation_ok",
        "contextual_location_table_ok",
        "server_inventory_name_ok",
        "split_server_inventory_name_ok",
        "semantic_server_capacity_node_ok",
        "underscored_dns_fqdn_ok",
        "domain_inventory_subject_ok",
        "domain_inventory_row_ok",
        "device_inventory_identifier_ok",
        "service_account_ok",
        "split_service_account_ok",
        "abbreviation_single_two_letter_ok",
        "graphics_roundtrip_ok",
    ):
        _require_true(engine, key, "smoke.engine")
    _require_digest(engine, "source_snapshot_sha256", "smoke.engine")
    _require_revision(engine, "git_revision", "smoke.engine")
    _require_digest(engine, "git_diff_sha256", "smoke.engine")


def validate_pair_smoke(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise VerificationError("pair-smoke payload must be an object")
    for key in (
        "ok",
        "pair_found_after_library_delete",
        "recovery_contains_sensitive_mapping",
        "restored_exactly",
    ):
        _require_true(payload, key, "pair-smoke")


def validate_platform_smoke(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise VerificationError("platform-smoke payload must be an object")
    for key in ("ok", "secure_storage", "clipboard"):
        _require_true(payload, key, "platform-smoke")


def _run_json_check(executable: Path, flag: str, timeout: int = 180) -> dict:
    try:
        completed = subprocess.run(
            [str(executable), flag],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise VerificationError(f"{flag} could not run: {type(exc).__name__}") from exc
    if completed.returncode != 0:
        raise VerificationError(f"{flag} exited with code {completed.returncode}")
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise VerificationError(f"{flag} returned no JSON")
    try:
        payload = json.loads(lines[-1])
    except (json.JSONDecodeError, TypeError) as exc:
        raise VerificationError(f"{flag} returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise VerificationError(f"{flag} payload must be an object")
    return payload


def _run_executable_checks(executable: Path) -> dict[str, dict]:
    if not executable.is_file():
        raise VerificationError(f"packaged executable not found: {executable}")
    checks: tuple[tuple[str, Callable[[dict], None]], ...] = (
        ("--smoke", validate_smoke),
        ("--pair-smoke", validate_pair_smoke),
        ("--platform-smoke", validate_platform_smoke),
    )
    results: dict[str, dict] = {}
    for flag, validate in checks:
        payload = _run_json_check(executable, flag)
        validate(payload)
        results[flag.removeprefix("--")] = payload
    return results


def _runtime_source_files(source_root: Path) -> list[Path]:
    fixed = (
        source_root / "launcher.py",
        source_root / "LocalAnonymizer.spec",
        source_root / "pyproject.toml",
        source_root / "uv.lock",
    )
    package_root = source_root / "src" / "local_anonymizer"
    candidates = [path for path in fixed if path.is_file()]
    if package_root.is_dir():
        candidates.extend(path for path in package_root.rglob("*.py") if path.is_file())
        assets = package_root / "assets"
        if assets.is_dir():
            candidates.extend(path for path in assets.rglob("*") if path.is_file())
    excluded = (source_root / PROVENANCE_MODULE).resolve()
    files = sorted({path.resolve() for path in candidates if path.resolve() != excluded})
    if not files:
        raise VerificationError("runtime source snapshot contains no files")
    return files


def source_snapshot_sha256(source_root: str | Path = ROOT) -> str:
    root = Path(source_root).resolve()
    digest = hashlib.sha256()
    for path in _runtime_source_files(root):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def git_revision(source_root: str | Path = ROOT) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=Path(source_root), capture_output=True,
            check=True, text=True, encoding="utf-8", errors="strict",
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise VerificationError("Git revision could not be determined") from exc
    revision = completed.stdout.strip().lower()
    if _REVISION_RE.fullmatch(revision) is None:
        raise VerificationError("Git revision has an invalid format")
    return revision


def git_diff_sha256(source_root: str | Path = ROOT) -> str:
    try:
        completed = subprocess.run(
            ["git", "diff", "--binary", "HEAD"], cwd=Path(source_root),
            capture_output=True, check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise VerificationError("Git worktree diff could not be hashed") from exc
    return _sha256_bytes(completed.stdout)


def _source_assets(source_root: Path) -> list[Path]:
    assets_root = source_root / "src" / "local_anonymizer" / "assets"
    if not assets_root.is_dir():
        raise VerificationError("source asset directory is missing")
    assets = sorted(path for path in assets_root.rglob("*") if path.is_file())
    if not assets:
        raise VerificationError("source asset directory is empty")
    return assets


def _find_bundled_asset(executable: Path, relative_asset: Path) -> Path:
    suffix = ("local_anonymizer", "assets", *relative_asset.parts)
    roots = [executable.parent]
    if executable.parent.name == "MacOS":
        roots.append(executable.parent.parent)
    matches: set[Path] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for candidate in root.rglob(relative_asset.name):
            if candidate.is_file() and tuple(candidate.parts[-len(suffix):]) == suffix:
                matches.add(candidate.resolve())
    if len(matches) != 1:
        raise VerificationError(
            f"packaged asset {relative_asset.as_posix()} must resolve exactly once; found {len(matches)}"
        )
    return next(iter(matches))


def _asset_manifest(executable: Path, source_root: Path) -> dict[str, dict[str, str]]:
    assets_root = source_root / "src" / "local_anonymizer" / "assets"
    records: dict[str, dict[str, str]] = {}
    for source in _source_assets(source_root):
        relative = source.relative_to(assets_root)
        bundled = _find_bundled_asset(executable, relative)
        source_hash = _sha256_file(source)
        bundled_hash = _sha256_file(bundled)
        if bundled_hash != source_hash:
            raise VerificationError(f"packaged asset differs from source: {relative.as_posix()}")
        records[relative.as_posix()] = {
            "sha256": source_hash,
            "package_path": os.path.relpath(bundled, executable.parent).replace("\\", "/"),
        }
    return records


def _package_root(executable: Path) -> Path:
    parent = executable.parent
    if parent.name == "MacOS" and parent.parent.name == "Contents":
        return parent.parent.parent
    return parent


def _normalized_path(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def _package_file_manifest(
    executable: Path,
    *,
    excluded_paths: Iterable[str | Path] = (),
) -> dict[str, dict[str, str | int]]:
    package_root = _package_root(executable)
    excluded = {_normalized_path(Path(path)) for path in excluded_paths}
    records: dict[str, dict[str, str | int]] = {}
    for path in sorted(package_root.rglob("*")):
        if _normalized_path(path) in excluded:
            continue
        relative = path.relative_to(package_root).as_posix()
        if path.is_symlink():
            resolved = path.resolve()
            try:
                resolved.relative_to(package_root.resolve())
            except ValueError as exc:
                raise VerificationError(
                    f"packaged symlink escapes package root: {relative}"
                ) from exc
            records[relative] = {
                "symlink": os.readlink(path).replace("\\", "/"),
            }
        elif path.is_file():
            records[relative] = {
                "sha256": _sha256_file(path),
                "size": path.stat().st_size,
            }
    if not records:
        raise VerificationError("package file inventory is empty")
    return records


def _validate_engine_provenance(
    engine: dict,
    source_hash: str,
    revision: str,
    diff_hash: str,
) -> None:
    if engine.get("source_snapshot_sha256") != source_hash:
        raise VerificationError("executable self-reported source snapshot does not match current source")
    if engine.get("git_revision") != revision:
        raise VerificationError("executable self-reported Git revision does not match current source")
    if engine.get("git_diff_sha256") != diff_hash:
        raise VerificationError("executable self-reported Git diff hash does not match current source")


def build_package_manifest(
    executable: str | Path,
    engine: dict,
    *,
    source_root: str | Path = ROOT,
    git_revision: str | None = None,
    git_diff_sha256: str | None = None,
) -> dict:
    path = Path(executable).resolve()
    root = Path(source_root).resolve()
    if not path.is_file():
        raise VerificationError(f"packaged executable not found: {path}")
    source_hash = source_snapshot_sha256(root)
    revision = git_revision or globals()["git_revision"](root)
    diff_hash = git_diff_sha256 or globals()["git_diff_sha256"](root)
    _validate_engine_provenance(engine, source_hash, revision, diff_hash)
    return {
        "schema_version": 2,
        "source_snapshot_sha256": source_hash,
        "git_revision": revision,
        "git_diff_sha256": diff_hash,
        "executable_sha256": _sha256_file(path),
        "assets": _asset_manifest(path, root),
        "files": _package_file_manifest(path),
    }


def validate_package_manifest(
    executable: str | Path,
    manifest: dict,
    engine: dict,
    *,
    source_root: str | Path = ROOT,
    git_revision: str | None = None,
    git_diff_sha256: str | None = None,
    manifest_path: str | Path | None = None,
) -> None:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 2:
        raise VerificationError("package manifest schema_version must be 2")
    path = Path(executable).resolve()
    root = Path(source_root).resolve()
    if not path.is_file():
        raise VerificationError(f"packaged executable not found: {path}")
    source_hash = source_snapshot_sha256(root)
    revision = git_revision or globals()["git_revision"](root)
    diff_hash = git_diff_sha256 or globals()["git_diff_sha256"](root)
    if manifest.get("source_snapshot_sha256") != source_hash:
        raise VerificationError("package manifest source snapshot does not match current source")
    if manifest.get("git_revision") != revision:
        raise VerificationError("package manifest Git revision does not match current source")
    if manifest.get("git_diff_sha256") != diff_hash:
        raise VerificationError("package manifest Git diff hash does not match current source")
    if manifest.get("executable_sha256") != _sha256_file(path):
        raise VerificationError("package manifest executable SHA-256 does not match")
    _validate_engine_provenance(engine, source_hash, revision, diff_hash)
    expected_assets = _asset_manifest(path, root)
    if manifest.get("assets") != expected_assets:
        raise VerificationError("package manifest asset hashes do not match source and package")
    excluded = (manifest_path,) if manifest_path is not None else ()
    if manifest.get("files") != _package_file_manifest(path, excluded_paths=excluded):
        raise VerificationError("package file inventory does not match")


def _read_manifest(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerificationError("package manifest could not be read") from exc
    if not isinstance(payload, dict):
        raise VerificationError("package manifest must be an object")
    return payload


def _write_manifest(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def verify_executable(
    executable: str | Path,
    manifest: str | Path,
    *,
    source_root: str | Path = ROOT,
) -> dict[str, dict]:
    path = Path(executable).resolve()
    manifest_path = Path(manifest).resolve()
    results = _run_executable_checks(path)
    validate_package_manifest(
        path,
        _read_manifest(manifest_path),
        results["smoke"]["engine"],
        source_root=source_root,
        manifest_path=manifest_path,
    )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed verification of a packaged LocalAnonymizer executable"
    )
    parser.add_argument("executable")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--manifest")
    mode.add_argument("--write-manifest")
    args = parser.parse_args(argv)
    executable = Path(args.executable).resolve()
    try:
        results = _run_executable_checks(executable)
        engine = results["smoke"]["engine"]
        if args.write_manifest:
            manifest_path = Path(args.write_manifest).resolve()
            manifest = build_package_manifest(executable, engine)
            _write_manifest(manifest_path, manifest)
        else:
            manifest_path = Path(args.manifest).resolve()
            manifest = _read_manifest(manifest_path)
        validate_package_manifest(
            executable,
            manifest,
            engine,
            manifest_path=manifest_path,
        )
    except VerificationError as exc:
        print(f"Packaged verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "ok": True,
        "checks": sorted(results),
        "manifest": str(manifest_path),
        "source_snapshot_sha256": manifest["source_snapshot_sha256"],
        "executable_sha256": manifest["executable_sha256"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
