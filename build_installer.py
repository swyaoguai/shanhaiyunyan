#!/usr/bin/env python3
"""
Windows installer build script.

Builds a normal installable app layout with PyInstaller --onedir, writes an
Inno Setup script, and compiles Setup.exe when ISCC is available.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from build_portable import (
    APP_VERSION,
    BUILD_DIR,
    DISPLAY_NAME,
    DIST_DIR,
    RELEASE_DATA_DIR,
    ROOT_DIR,
    SOURCE_ONNX_MODEL_DIR,
    SOURCE_SKILLS_DIR,
    _default_skills_config,
    _default_timeout_settings,
    _default_trends_config,
    calculate_file_hash,
    check_requirements,
    prepare_release_data,
    pyinstaller_optional_exclude_args,
    pyinstaller_skill_dependency_args,
)


APP_DIR = DIST_DIR / f"{DISPLAY_NAME}_v{APP_VERSION}_App"
PYINSTALLER_OUT_DIR = DIST_DIR / DISPLAY_NAME
INSTALLER_DIR = ROOT_DIR / "installer"
INNO_SCRIPT_PATH = INSTALLER_DIR / "ShanhaiYunyan.iss"
LEGACY_SETUP_EXE_PATH = DIST_DIR / f"{DISPLAY_NAME}_v{APP_VERSION}_Setup.exe"


def installer_variant(include_onnx: bool) -> str:
    return "local_model" if include_onnx else "lite"


def installer_variant_label(include_onnx: bool) -> str:
    return "本地模型版" if include_onnx else "轻量版"


def setup_base_name(include_onnx: bool) -> str:
    suffix = "LocalModel" if include_onnx else "Lite"
    return f"{DISPLAY_NAME}_v{APP_VERSION}_Setup_{suffix}"


def setup_exe_path(include_onnx: bool) -> Path:
    return DIST_DIR / f"{setup_base_name(include_onnx)}.exe"


def _safe_rmtree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def clean_installer_artifacts(include_onnx: bool = False) -> bool:
    """Remove only installer-related build outputs."""
    print("\n[清理] 清理安装包构建产物...")
    for path in (
        APP_DIR,
        PYINSTALLER_OUT_DIR,
        BUILD_DIR / "installer_work",
        BUILD_DIR / "installer_spec",
    ):
        if path.exists():
            _safe_rmtree(path)
            print(f"[OK] 删除 {path.relative_to(ROOT_DIR)}")
    for setup_path in {setup_exe_path(include_onnx), LEGACY_SETUP_EXE_PATH}:
        if setup_path.exists():
            setup_path.unlink()
            print(f"[OK] 删除 {setup_path.relative_to(ROOT_DIR)}")
    return True


def _pyinstaller_common_args() -> list[str]:
    static_dir = ROOT_DIR / "novel_agent" / "web" / "static"
    templates_dir = ROOT_DIR / "novel_agent" / "web" / "templates"
    prompts_dir = ROOT_DIR / "novel_agent" / "prompts"
    data_dir = RELEASE_DATA_DIR

    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        DISPLAY_NAME,
        "--noconfirm",
        "--clean",
        "--onedir",
        "--noconsole",
        "--workpath",
        str(BUILD_DIR / "installer_work"),
        "--specpath",
        str(BUILD_DIR / "installer_spec"),
        "--distpath",
        str(DIST_DIR),
        "--add-data",
        f"{static_dir};novel_agent/web/static",
        "--add-data",
        f"{templates_dir};novel_agent/web/templates",
        "--add-data",
        f"{prompts_dir};novel_agent/prompts",
        "--add-data",
        f"{data_dir};novel_agent/data",
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.protocols",
        "--hidden-import",
        "uvicorn.protocols.http",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "uvicorn.protocols.websockets",
        "--hidden-import",
        "uvicorn.protocols.websockets.auto",
        "--hidden-import",
        "uvicorn.lifespan",
        "--hidden-import",
        "uvicorn.lifespan.on",
        "--hidden-import",
        "pydantic_core",
        "--hidden-import",
        "pydantic_core._pydantic_core",
        "--collect-all",
        "pydantic_core",
        "--collect-all",
        "pydantic",
    ]
    args.extend(pyinstaller_skill_dependency_args())
    args.extend(pyinstaller_optional_exclude_args())

    ico_path = ROOT_DIR / "logo.ico"
    if ico_path.exists():
        args.extend(["--icon", str(ico_path)])
        print("[图标] 使用 logo.ico")
    else:
        print("[提示] 未找到 logo.ico，将使用默认图标")

    args.append(str(ROOT_DIR / "run.py"))
    return args


def run_pyinstaller_onedir() -> bool:
    """Build the installable application directory."""
    print("\n[构建] 运行 PyInstaller --onedir...")
    if not RELEASE_DATA_DIR.exists():
        prepare_release_data()

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(_pyinstaller_common_args(), cwd=ROOT_DIR)
    if result.returncode != 0:
        print("[X] PyInstaller 构建失败")
        return False
    if not PYINSTALLER_OUT_DIR.exists():
        print(f"[X] 未找到 PyInstaller 输出目录: {PYINSTALLER_OUT_DIR}")
        return False
    if APP_DIR.exists():
        _safe_rmtree(APP_DIR)
    PYINSTALLER_OUT_DIR.rename(APP_DIR)
    print(f"[OK] 应用目录: {APP_DIR.relative_to(ROOT_DIR)}")
    return True


def _skill_copy_ignore(_dir: str, names: list[str]) -> set[str]:
    ignored = set()
    for name in names:
        lowered = name.lower()
        if name == "__pycache__" or lowered.endswith((".pyc", ".pyo")):
            ignored.add(name)
        elif lowered.startswith("test_") and lowered.endswith(".py"):
            ignored.add(name)
        elif lowered in {"integration_guide.md", "troubleshooting.md", "usage.md"}:
            ignored.add(name)
    return ignored


def populate_app_layout(include_onnx: bool = False) -> bool:
    """Copy runtime-side files that should live next to the exe."""
    print("\n[创建] 安装版应用目录结构...")
    if not APP_DIR.exists():
        print(f"[X] 应用目录不存在: {APP_DIR}")
        return False

    for src_name in (".env.example", "使用说明.md"):
        src = ROOT_DIR / src_name
        if src.exists():
            shutil.copy2(src, APP_DIR / src_name)
            print(f"[OK] 复制 {src_name}")
        else:
            print(f"[提示] 未找到 {src_name}")

    data_dir = APP_DIR / "data"
    for dirname in ("projects", "stats", "sessions", "logs"):
        (data_dir / dirname).mkdir(parents=True, exist_ok=True)
    (data_dir / "trends_config.json").write_text(
        json.dumps(_default_trends_config(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (data_dir / "timeout_settings.json").write_text(
        json.dumps(_default_timeout_settings(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (data_dir / "skills_config.json").write_text(
        json.dumps(_default_skills_config(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("[OK] 创建默认 data 配置")

    if SOURCE_SKILLS_DIR.exists():
        skills_dst = APP_DIR / "skills"
        if skills_dst.exists():
            _safe_rmtree(skills_dst)
        shutil.copytree(SOURCE_SKILLS_DIR, skills_dst, ignore=_skill_copy_ignore)
        print("[OK] 复制外置 Skills")
    else:
        print("[警告] 未找到 skills 目录，安装包将不内置技能")

    if include_onnx:
        if SOURCE_ONNX_MODEL_DIR.exists():
            model_dst = APP_DIR / "novel_agent" / "models" / "embedding" / "default"
            if model_dst.exists():
                _safe_rmtree(model_dst)
            shutil.copytree(SOURCE_ONNX_MODEL_DIR, model_dst)
            print("[OK] 已内置本地 ONNX 向量模型")
        else:
            print("[提示] 未找到本地 ONNX 模型，跳过内置")
    else:
        print("[OK] 默认不内置本地 ONNX 模型，用户可在设置页按需安装模型包")

    create_start_bat()
    write_installer_manifest(include_onnx=include_onnx)
    return True


def create_start_bat() -> None:
    content = f"""@echo off
chcp 65001 > nul
title {DISPLAY_NAME}

if not exist "%~dp0data" mkdir "%~dp0data" 2>nul
if not exist "%~dp0data\\projects" mkdir "%~dp0data\\projects" 2>nul
if not exist "%~dp0data\\stats" mkdir "%~dp0data\\stats" 2>nul
if not exist "%~dp0data\\sessions" mkdir "%~dp0data\\sessions" 2>nul
if not exist "%~dp0data\\logs" mkdir "%~dp0data\\logs" 2>nul

if not exist "%~dp0.env" (
    if exist "%~dp0.env.example" copy "%~dp0.env.example" "%~dp0.env" > nul
)

start "" "%~dp0{DISPLAY_NAME}.exe"
"""
    (APP_DIR / "Start.bat").write_text("\r\n".join(content.splitlines()) + "\r\n", encoding="utf-8")
    (APP_DIR / f"启动{DISPLAY_NAME}.bat").write_text(
        "\r\n".join(content.splitlines()) + "\r\n",
        encoding="utf-8",
    )
    print("[OK] 创建启动脚本")


def write_installer_manifest(include_onnx: bool) -> None:
    manifest = {
        "version": APP_VERSION,
        "build_time": datetime.now().isoformat(),
        "installer_variant": installer_variant(include_onnx),
        "installer_variant_label": installer_variant_label(include_onnx),
        "include_nodejs": False,
        "include_onnx": include_onnx,
        "app_dir": str(APP_DIR),
        "files": {},
    }
    for name in (f"{DISPLAY_NAME}.exe", "Start.bat", ".env.example"):
        path = APP_DIR / name
        if path.exists():
            manifest["files"][name] = {
                "sha256": calculate_file_hash(path, "sha256"),
                "size": path.stat().st_size,
            }
    (APP_DIR / "installer_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("[OK] 写入 installer_manifest.json")


def _inno_path(path: Path) -> str:
    return str(path.resolve())


def write_inno_script(include_onnx: bool = False) -> bool:
    """Write the Inno Setup script used to compile the final installer."""
    print("\n[安装包] 生成 Inno Setup 脚本...")
    INSTALLER_DIR.mkdir(parents=True, exist_ok=True)
    app_source = _inno_path(APP_DIR)
    output_dir = _inno_path(DIST_DIR)
    flavor_label = installer_variant_label(include_onnx)
    output_base_name = setup_base_name(include_onnx)
    script = f'''#define MyAppName "{DISPLAY_NAME}"
#define MyAppVersion "{APP_VERSION}"
#define MyInstallerFlavor "{flavor_label}"
#define MyAppExeName "{DISPLAY_NAME}.exe"
#define SourceDir "{app_source}"

[Setup]
AppId={{{{F10F6C34-26F1-451F-9C41-650D29F5918D}}}}
AppName={{#MyAppName}}
AppVersion={{#MyAppVersion}}
AppVerName={{#MyAppName}} {{#MyAppVersion}} {{#MyInstallerFlavor}}
AppPublisher=山海云烟
DefaultDirName={{localappdata}}\\Programs\\ShanhaiYunyan
DefaultGroupName={{#MyAppName}}
DisableProgramGroupPage=yes
OutputDir={output_dir}
OutputBaseFilename={output_base_name}
Compression=lzma2/ultra64
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
SetupLogging=yes
UninstallDisplayIcon={{app}}\\{{#MyAppExeName}}

[Files]
Source: "{{#SourceDir}}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{{app}}\\data"
Name: "{{app}}\\data\\projects"
Name: "{{app}}\\data\\stats"
Name: "{{app}}\\data\\sessions"
Name: "{{app}}\\data\\logs"

[Icons]
Name: "{{group}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"
Name: "{{autodesktop}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: unchecked

[Run]
Filename: "{{cmd}}"; Parameters: "/C if not exist ""{{app}}\\.env"" copy ""{{app}}\\.env.example"" ""{{app}}\\.env"""; Flags: runhidden
Filename: "{{app}}\\{{#MyAppExeName}}"; Description: "启动 {{#MyAppName}}"; Flags: nowait postinstall skipifsilent
'''
    INNO_SCRIPT_PATH.write_text(script, encoding="utf-8")
    print(f"[OK] 脚本: {INNO_SCRIPT_PATH.relative_to(ROOT_DIR)}")
    return True


def find_iscc() -> str | None:
    candidates = [
        shutil.which("ISCC.exe"),
        shutil.which("ISCC"),
        str(Path.home() / "AppData" / "Local" / "Programs" / "Inno Setup 6" / "ISCC.exe"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


def compile_inno_installer(include_onnx: bool = False, skip_compile: bool = False) -> bool:
    """Compile Setup.exe when Inno Setup is installed."""
    if skip_compile:
        print("[跳过] 已按参数跳过 Inno Setup 编译")
        return True
    iscc = find_iscc()
    if not iscc:
        print("[提示] 未找到 Inno Setup Compiler（ISCC.exe）")
        print(f"      已生成应用目录和脚本，可安装 Inno Setup 后运行: ISCC \"{INNO_SCRIPT_PATH}\"")
        return True

    print("\n[安装包] 编译 Setup.exe...")
    result = subprocess.run([iscc, str(INNO_SCRIPT_PATH)], cwd=ROOT_DIR)
    if result.returncode != 0:
        print("[X] Inno Setup 编译失败")
        return False
    expected_setup = setup_exe_path(include_onnx)
    if not expected_setup.exists():
        print(f"[X] 未找到安装包: {expected_setup}")
        return False
    print(f"[OK] 安装包: {expected_setup.relative_to(ROOT_DIR)}")
    print(f"     大小: {expected_setup.stat().st_size / (1024 * 1024):.1f} MB")
    print(f"     SHA256: {calculate_file_hash(expected_setup, 'sha256')}")
    return True


def print_summary(include_onnx: bool = False) -> None:
    print("\n" + "=" * 60)
    print("安装包构建摘要")
    print("=" * 60)
    if APP_DIR.exists():
        total_size = sum(path.stat().st_size for path in APP_DIR.rglob("*") if path.is_file())
        print(f"应用目录: {APP_DIR}")
        print(f"应用目录大小: {total_size / (1024 * 1024):.1f} MB")
    expected_setup = setup_exe_path(include_onnx)
    if expected_setup.exists():
        print(f"安装包: {expected_setup}")
        print(f"安装包大小: {expected_setup.stat().st_size / (1024 * 1024):.1f} MB")
    else:
        print(f"Inno 脚本: {INNO_SCRIPT_PATH}")
        print("安装包未编译：请安装 Inno Setup 后重新运行本脚本。")
    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Windows installer for 山海·云烟")
    parser.add_argument("-y", "--yes", action="store_true", help="skip confirmation")
    parser.add_argument("--include-onnx", action="store_true", help="bundle local ONNX embedding model")
    parser.add_argument("--skip-compile", action="store_true", help="do not call Inno Setup compiler")
    args = parser.parse_args()

    print("=" * 60)
    print(f"{DISPLAY_NAME} - 安装包构建脚本")
    print("=" * 60)
    print("本脚本会生成安装版应用目录，并在检测到 Inno Setup 时生成 Setup.exe。")
    print("默认不内置 Node.js，也不内置本地 ONNX 模型。")
    if args.include_onnx:
        print("[选项] 本次会内置本地 ONNX 模型。")
    print(f"[版本] 输出安装包后缀: {setup_base_name(args.include_onnx)}.exe")

    if not check_requirements():
        return 1
    if not args.yes:
        confirm = input("确认开始构建？(y/n): ")
        if confirm.lower() != "y":
            print("已取消")
            return 0

    steps = [
        ("清理安装包产物", lambda: clean_installer_artifacts(include_onnx=args.include_onnx)),
        ("准备发布数据", prepare_release_data),
        ("PyInstaller onedir 构建", run_pyinstaller_onedir),
        ("创建应用目录结构", lambda: populate_app_layout(include_onnx=args.include_onnx)),
        ("生成 Inno Setup 脚本", lambda: write_inno_script(include_onnx=args.include_onnx)),
        ("编译安装包", lambda: compile_inno_installer(include_onnx=args.include_onnx, skip_compile=args.skip_compile)),
    ]
    for name, func in steps:
        print(f"\n{'=' * 60}")
        print(f"步骤: {name}")
        print("=" * 60)
        if not func():
            print(f"\n[X] {name} 失败，构建中止")
            return 1

    print_summary(include_onnx=args.include_onnx)
    print("\n构建流程完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
