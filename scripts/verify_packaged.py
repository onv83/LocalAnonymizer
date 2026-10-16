from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path


class VerificationError(RuntimeError):
    """The packaged application did not prove a required release invariant."""


def _require_true(payload: dict, key: str, scope: str) -> None:
    if payload.get(key) is not True:
        raise VerificationError(f"{scope}.{key} must be true")


def validate_smoke(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise VerificationError("smoke payload must be an object")
    _require_true(payload, "ok", "smoke")
    engine = payload.get("engine")
    if not isinstance(engine, dict):
        raise VerificationError("smoke.engine must be an object")
    for key in ("ok", "vm_node_ok", "abbreviation_ok", "graphics_roundtrip_ok"):
        _require_true(engine, key, "smoke.engine")


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


def verify_executable(executable: str | Path) -> dict[str, dict]:
    path = Path(executable).resolve()
    if not path.is_file():
        raise VerificationError(f"packaged executable not found: {path}")
    checks: tuple[tuple[str, Callable[[dict], None]], ...] = (
        ("--smoke", validate_smoke),
        ("--pair-smoke", validate_pair_smoke),
        ("--platform-smoke", validate_platform_smoke),
    )
    results: dict[str, dict] = {}
    for flag, validate in checks:
        payload = _run_json_check(path, flag)
        validate(payload)
        results[flag.removeprefix("--")] = payload
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail-closed verification of a packaged LocalAnonymizer executable"
    )
    parser.add_argument("executable")
    args = parser.parse_args(argv)
    try:
        results = verify_executable(args.executable)
    except VerificationError as exc:
        print(f"Packaged verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "checks": sorted(results)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
