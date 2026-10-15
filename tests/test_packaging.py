import os
import shutil
import subprocess
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def _run_posix_build(
    tmp_path: Path,
    kernel: str,
    artifact: str | None,
    *,
    executable: bool = True,
) -> subprocess.CompletedProcess[str]:
    script = tmp_path / "build.sh"
    shutil.copy2(ROOT / "build.sh", script)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "uname").write_text(
        "#!/usr/bin/env sh\nprintf '%s\\n' \"$FAKE_UNAME\"\n",
        encoding="utf-8",
        newline="\n",
    )
    pyinstaller = tmp_path / ".venv" / "bin" / "pyinstaller"
    pyinstaller.parent.mkdir(parents=True)
    pyinstaller.write_text(
        "#!/usr/bin/env sh\n"
        "set -eu\n"
        "if [ -n \"${FAKE_ARTIFACT:-}\" ]; then\n"
        "  mkdir -p \"$(dirname \"$FAKE_ARTIFACT\")\"\n"
        "  if [ \"${FAKE_EXECUTABLE:-1}\" = 1 ]; then\n"
        "    printf '%s\\n' '#!/usr/bin/env sh' > \"$FAKE_ARTIFACT\"\n"
        "    chmod +x \"$FAKE_ARTIFACT\"\n"
        "  else\n"
        "    : > \"$FAKE_ARTIFACT\"\n"
        "  fi\n"
        "fi\n",
        encoding="utf-8",
        newline="\n",
    )
    os.chmod(bin_dir / "uname", 0o755)
    os.chmod(pyinstaller, 0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "FAKE_UNAME": kernel,
            "FAKE_ARTIFACT": artifact or "",
            "FAKE_EXECUTABLE": "1" if executable else "0",
        }
    )
    return subprocess.run(
        ["sh", str(script)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_gui_and_windows_dependencies_are_platform_scoped():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    dependencies = project["dependencies"]

    assert "pywin32>=311; sys_platform == 'win32'" in dependencies
    assert any(dependency.startswith("lxml") and ";" not in dependency for dependency in dependencies)
    assert any(
        dependency.startswith("pywebview") and "sys_platform == 'win32'" in dependency
        for dependency in dependencies
    )
    assert any(
        dependency.startswith("pywebview") and "sys_platform == 'darwin'" in dependency
        for dependency in dependencies
    )
    assert any(
        dependency.startswith("pywebview[gtk]") and "sys_platform == 'linux'" in dependency
        for dependency in dependencies
    )
    assert not any(
        dependency.startswith("pywebview") and ";" not in dependency
        for dependency in dependencies
    )
    assert "Windows" not in project["description"]


def test_non_windows_secure_storage_dependencies_are_platform_scoped():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    dependencies = project["dependencies"]

    for package in ("cryptography", "keyring"):
        assert any(
            dependency.startswith(package) and "sys_platform == 'linux'" in dependency
            for dependency in dependencies
        )
        assert any(
            dependency.startswith(package) and "sys_platform == 'darwin'" in dependency
            for dependency in dependencies
        )
        assert not any(
            dependency.startswith(package) and ";" not in dependency
            for dependency in dependencies
        )
    assert any(
        dependency.startswith("secretstorage") and "sys_platform == 'linux'" in dependency
        for dependency in dependencies
    )


def test_platform_build_wrappers_share_the_pyinstaller_spec():
    windows = (ROOT / "build.bat").read_text(encoding="utf-8")
    posix = (ROOT / "build.sh").read_text(encoding="utf-8")

    assert "LocalAnonymizer.spec" in windows
    assert "LocalAnonymizer.spec" in posix
    for duplicated_setting in ("--onedir", "--windowed", "--add-data", "--collect-all"):
        assert duplicated_setting not in windows
        assert duplicated_setting not in posix


def test_posix_scripts_are_forced_to_lf_in_git():
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.sh text eol=lf" in attributes
    for name in ("build.sh", "verify-native.sh"):
        script = ROOT / name
        assert script.read_bytes().startswith(b"#!/usr/bin/env sh\n")
        assert bytes((13, 10)) not in script.read_bytes()
        assert os.access(script, os.X_OK)


def test_posix_build_reports_verified_linux_artifact(tmp_path):
    artifact = "dist/LocalAnonymizer/LocalAnonymizer"
    result = _run_posix_build(tmp_path, "Linux", artifact)

    assert result.returncode == 0, result.stderr
    assert artifact in result.stdout


def test_posix_build_reports_verified_macos_artifact(tmp_path):
    artifact = "dist/LocalAnonymizer.app/Contents/MacOS/LocalAnonymizer"
    result = _run_posix_build(tmp_path, "Darwin", artifact)

    assert result.returncode == 0, result.stderr
    assert artifact in result.stdout


def test_posix_build_rejects_unsupported_kernel_before_build(tmp_path):
    result = _run_posix_build(tmp_path, "FreeBSD", None)

    assert result.returncode != 0
    assert "Unsupported platform: FreeBSD" in result.stderr


def test_posix_build_fails_when_expected_artifact_is_missing(tmp_path):
    result = _run_posix_build(tmp_path, "Linux", None)

    assert result.returncode != 0
    assert "Build artifact is missing" in result.stderr


def test_posix_build_fails_when_artifact_is_not_executable(tmp_path):
    result = _run_posix_build(
        tmp_path,
        "Darwin",
        "dist/LocalAnonymizer.app/Contents/MacOS/LocalAnonymizer",
        executable=False,
    )

    assert result.returncode != 0
    assert "Build artifact is not executable" in result.stderr


def test_macos_spec_produces_native_app_bundle_without_changing_windows_onedir():
    spec = (ROOT / "LocalAnonymizer.spec").read_text(encoding="utf-8")

    assert "import sys" in spec
    assert "if sys.platform == 'darwin':" in spec
    assert "BUNDLE(" in spec
    assert "name='LocalAnonymizer.app'" in spec
    assert "bundle_identifier='io.github.onv83.localanonymizer'" in spec
    assert "COLLECT(" in spec


def test_posix_native_verifier_checks_all_packaged_smoke_modes():
    verifier = (ROOT / "verify-native.sh").read_text(encoding="utf-8")

    assert "dist/LocalAnonymizer.app/Contents/MacOS/LocalAnonymizer" in verifier
    assert "dist/LocalAnonymizer/LocalAnonymizer" in verifier
    assert '"$executable" --smoke' in verifier
    assert '"$executable" --pair-smoke' in verifier
    assert '"$executable" --platform-smoke' in verifier


def test_native_spec_collects_runtime_loaded_secure_storage_backends():
    spec = (ROOT / "LocalAnonymizer.spec").read_text(encoding="utf-8")

    assert "collect_all('docx')" in spec
    assert "if sys.platform in {'darwin', 'linux'}:" in spec
    assert "for package in ('keyring', 'cryptography'):" in spec
    assert "collect_all(package)" in spec
    assert "if sys.platform == 'linux':" in spec
    assert "collect_all('secretstorage')" in spec


def test_native_ci_builds_and_smokes_linux_and_macos_packages():
    workflow = (ROOT / ".github" / "workflows" / "native.yml").read_text(encoding="utf-8")
    verifier = (ROOT / "verify-native.sh").read_text(encoding="utf-8")

    assert "ubuntu-24.04" in workflow
    assert "macos-14" in workflow
    assert "uv sync --extra dev" in workflow
    assert "Run macOS tests" in workflow
    assert "Run Linux tests with Secret Service" in workflow
    assert "security delete-generic-password -s LocalAnonymizer" in workflow
    assert "uv run pytest" in workflow
    assert "./build.sh" in workflow
    assert "./verify-native.sh" in workflow
    assert "--smoke" in verifier
    assert "--pair-smoke" in verifier
    assert "--platform-smoke" in verifier
