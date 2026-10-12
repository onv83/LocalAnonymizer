from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


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
