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
    VERSION_FILE,
    _default_global_api_config,
    _default_knowledge_base_config,
    _default_skills_config,
    _default_timeout_settings,
    _default_trends_config,
    calculate_file_hash,
    check_requirements,
    prepare_release_data,
    pyinstaller_knowledge_dependency_args,
    pyinstaller_optional_exclude_args,
    pyinstaller_skill_dependency_args,
)


APP_DIR = DIST_DIR / f"{DISPLAY_NAME}_v{APP_VERSION}_App"
PYINSTALLER_OUT_DIR = DIST_DIR / DISPLAY_NAME
INSTALLER_DIR = ROOT_DIR / "installer"
INNO_SCRIPT_PATH = INSTALLER_DIR / "ShanhaiYunyan.iss"
LEGACY_SETUP_EXE_PATH = DIST_DIR / f"{DISPLAY_NAME}_v{APP_VERSION}_Setup.exe"
LEGACY_VARIANT_SETUP_EXE_PATHS = {
    DIST_DIR / f"{DISPLAY_NAME}_v{APP_VERSION}_Setup_Lite.exe",
    DIST_DIR / f"{DISPLAY_NAME}_v{APP_VERSION}_Setup_LocalModel.exe",
}
DEFAULT_LOCAL_ONNX_MODEL_DIR = "novel_agent/models/embedding/default"

CHINESE_INNO_MESSAGES = r"""
[Messages]
SetupAppTitle=安装程序
SetupWindowTitle=安装 - %1
UninstallAppTitle=卸载程序
UninstallAppFullTitle=%1 卸载
InformationTitle=信息
ConfirmTitle=确认
ErrorTitle=错误
SetupLdrStartupMessage=即将安装 %1。是否继续？
LdrCannotCreateTemp=无法创建临时文件。安装已中止
LdrCannotExecTemp=无法执行临时目录中的文件。安装已中止
LastErrorMessage=%1。%n%n错误 %2：%3
SetupFileMissing=安装目录中缺少文件 %1。请修复此问题或重新获取安装程序。
SetupFileCorrupt=安装文件已损坏。请重新获取安装程序。
SetupFileCorruptOrWrongVer=安装文件已损坏，或与当前安装程序版本不兼容。请修复此问题或重新获取安装程序。
InvalidParameter=命令行参数无效：%n%n%1
SetupAlreadyRunning=安装程序已经在运行。
WindowsVersionNotSupported=此程序不支持当前 Windows 版本。
AdminPrivilegesRequired=安装此程序需要以管理员身份登录。
SetupAppRunningError=安装程序检测到 %1 正在运行。%n%n请关闭所有实例后单击“确定”继续，或单击“取消”退出。
UninstallAppRunningError=卸载程序检测到 %1 正在运行。%n%n请关闭所有实例后单击“确定”继续，或单击“取消”退出。
ExitSetupTitle=退出安装
ExitSetupMessage=安装尚未完成。如果现在退出，程序将不会被安装。%n%n您可以稍后再次运行安装程序完成安装。%n%n确定退出安装吗？
AboutSetupMenuItem=关于安装程序(&A)...
AboutSetupTitle=关于安装程序
ButtonBack=< 上一步(&B)
ButtonNext=下一步(&N) >
ButtonInstall=安装(&I)
ButtonOK=确定
ButtonCancel=取消
ButtonYes=是(&Y)
ButtonYesToAll=全部是(&A)
ButtonNo=否(&N)
ButtonNoToAll=全部否(&O)
ButtonFinish=完成(&F)
ButtonBrowse=浏览(&B)...
ButtonWizardBrowse=浏览(&B)...
ButtonNewFolder=新建文件夹(&M)
SelectLanguageTitle=选择安装语言
SelectLanguageLabel=请选择安装过程中使用的语言。
ClickNext=单击“下一步”继续，或单击“取消”退出安装程序。
BrowseDialogTitle=浏览文件夹
BrowseDialogLabel=请在下面的列表中选择文件夹，然后单击“确定”。
NewFolderName=新建文件夹
WelcomeLabel1=欢迎使用 [name] 安装向导
WelcomeLabel2=将在您的计算机上安装 [name/ver]。%n%n建议继续前关闭其他应用程序。
WizardPassword=密码
PasswordLabel1=此安装受密码保护。
PasswordLabel3=请输入密码，然后单击“下一步”继续。密码区分大小写。
PasswordEditLabel=密码(&P)：
IncorrectPassword=输入的密码不正确，请重试。
WizardLicense=许可协议
LicenseLabel=请在继续前阅读以下重要信息。
LicenseLabel3=请阅读以下许可协议。必须接受协议条款才能继续安装。
LicenseAccepted=我接受协议(&A)
LicenseNotAccepted=我不接受协议(&D)
WizardInfoBefore=信息
InfoBeforeLabel=请在继续前阅读以下重要信息。
InfoBeforeClickLabel=准备好继续安装时，请单击“下一步”。
WizardInfoAfter=信息
InfoAfterLabel=请在继续前阅读以下重要信息。
InfoAfterClickLabel=准备好继续安装时，请单击“下一步”。
WizardSelectDir=选择安装位置
SelectDirDesc=[name] 应安装到哪里？
SelectDirLabel3=安装程序会将 [name] 安装到以下文件夹。
SelectDirBrowseLabel=单击“下一步”继续。如需选择其他文件夹，请单击“浏览”。
DiskSpaceGBLabel=至少需要 [gb] GB 可用磁盘空间。
DiskSpaceMBLabel=至少需要 [mb] MB 可用磁盘空间。
CannotInstallToNetworkDrive=安装程序不能安装到网络驱动器。
CannotInstallToUNCPath=安装程序不能安装到 UNC 路径。
InvalidPath=必须输入带盘符的完整路径，例如：%n%nC:\APP%n%n或 UNC 路径，例如：%n%n\\server\share
InvalidDrive=选择的驱动器或 UNC 共享不存在或无法访问。请选择其他位置。
DiskSpaceWarningTitle=磁盘空间不足
DiskSpaceWarning=安装程序至少需要 %1 KB 可用空间，但所选驱动器只有 %2 KB 可用。%n%n是否仍要继续？
DirNameTooLong=文件夹名称或路径过长。
InvalidDirName=文件夹名称无效。
DirExistsTitle=文件夹已存在
DirExists=文件夹：%n%n%1%n%n已经存在。是否继续安装到该文件夹？
DirDoesntExistTitle=文件夹不存在
DirDoesntExist=文件夹：%n%n%1%n%n不存在。是否创建该文件夹？
WizardSelectComponents=选择组件
SelectComponentsDesc=要安装哪些组件？
SelectComponentsLabel2=请选择要安装的组件，清除不需要安装的组件。准备好后单击“下一步”。
FullInstallation=完整安装
CompactInstallation=精简安装
CustomInstallation=自定义安装
ComponentsDiskSpaceGBLabel=当前选择至少需要 [gb] GB 磁盘空间。
ComponentsDiskSpaceMBLabel=当前选择至少需要 [mb] MB 磁盘空间。
WizardSelectTasks=选择附加任务
SelectTasksDesc=需要执行哪些附加任务？
SelectTasksLabel2=请选择安装 [name] 时需要执行的附加任务，然后单击“下一步”。
WizardSelectProgramGroup=选择开始菜单文件夹
SelectStartMenuFolderDesc=安装程序应将快捷方式放在哪里？
SelectStartMenuFolderLabel3=安装程序将在以下开始菜单文件夹中创建快捷方式。
SelectStartMenuFolderBrowseLabel=单击“下一步”继续。如需选择其他文件夹，请单击“浏览”。
MustEnterGroupName=必须输入文件夹名称。
GroupNameTooLong=文件夹名称或路径过长。
InvalidGroupName=文件夹名称无效。
NoProgramGroupCheck2=不创建开始菜单文件夹(&D)
WizardReady=准备安装
ReadyLabel1=安装程序已准备好开始在您的计算机上安装 [name]。
ReadyLabel2a=单击“安装”继续安装，或单击“上一步”检查或更改设置。
ReadyLabel2b=单击“安装”继续。
ReadyMemoUserInfo=用户信息：
ReadyMemoDir=安装位置：
ReadyMemoType=安装类型：
ReadyMemoComponents=选择的组件：
ReadyMemoGroup=开始菜单文件夹：
ReadyMemoTasks=附加任务：
WizardPreparing=准备安装
PreparingDesc=安装程序正在准备在您的计算机上安装 [name]。
PreviousInstallNotCompleted=之前程序的安装/卸载尚未完成。需要重新启动计算机才能完成该操作。%n%n重新启动后，请再次运行安装程序完成 [name] 的安装。
CannotContinue=安装程序无法继续。请单击“取消”退出。
ApplicationsFound=以下应用程序正在使用安装程序需要更新的文件。建议允许安装程序自动关闭这些应用程序。
ApplicationsFound2=以下应用程序正在使用安装程序需要更新的文件。建议允许安装程序自动关闭这些应用程序。安装完成后，安装程序会尝试重新启动这些应用程序。
CloseApplications=自动关闭应用程序(&A)
DontCloseApplications=不关闭应用程序(&D)
ErrorCloseApplications=安装程序无法自动关闭所有应用程序。建议在继续前手动关闭正在使用待更新文件的应用程序。
PrepareToInstallNeedsRestart=安装程序必须重新启动计算机。重新启动后，请再次运行安装程序完成 [name] 的安装。%n%n是否现在重新启动？
WizardInstalling=正在安装
InstallingLabel=请稍候，安装程序正在将 [name] 安装到您的计算机。
FinishedHeadingLabel=正在完成 [name] 安装向导
FinishedLabelNoIcons=安装程序已在您的计算机上安装 [name]。
FinishedLabel=安装程序已在您的计算机上安装 [name]。可以通过已安装的快捷方式启动应用程序。
ClickFinish=单击“完成”退出安装程序。
FinishedRestartLabel=要完成 [name] 的安装，必须重新启动计算机。是否现在重新启动？
FinishedRestartMessage=要完成 [name] 的安装，必须重新启动计算机。%n%n是否现在重新启动？
ShowReadmeCheck=是，我要查看 README 文件
YesRadio=是，立即重新启动计算机(&Y)
NoRadio=否，稍后再重新启动计算机(&N)
RunEntryExec=运行 %1
RunEntryShellExec=查看 %1
SetupAborted=安装未完成。%n%n请修复问题后再次运行安装程序。
StatusClosingApplications=正在关闭应用程序...
StatusCreateDirs=正在创建目录...
StatusExtractFiles=正在解压文件...
StatusDownloadFiles=正在下载文件...
StatusCreateIcons=正在创建快捷方式...
StatusCreateIniEntries=正在创建 INI 项...
StatusCreateRegistryEntries=正在创建注册表项...
StatusRegisterFiles=正在注册文件...
StatusSavingUninstall=正在保存卸载信息...
StatusRunProgram=正在完成安装...
StatusRestartingApplications=正在重新启动应用程序...
StatusRollback=正在回滚更改...
ErrorExecutingProgram=无法执行文件：%n%1
UninstallNotFound=文件 %1 不存在，无法卸载。
UninstallOpenError=无法打开文件 %1，无法卸载。
ConfirmUninstall=确定要卸载 %1 吗？%n%n程序文件会被移除；项目、知识库、API 配置（.env）、备份、统计和日志默认保留在安装目录。%n%n如需彻底清除，请卸载后手动删除安装目录中的 data 文件夹和 .env 文件。
UninstallStatusLabel=请稍候，正在从您的计算机中移除 %1。
UninstalledAll=%1 已成功从您的计算机中移除。
UninstalledMost=%1 卸载完成。%n%n某些项目无法移除，可以手动删除。
UninstalledAndNeedsRestart=要完成 %1 的卸载，必须重新启动计算机。%n%n是否现在重新启动？
UninstallDataCorrupted=文件 %1 已损坏，无法卸载。
WizardUninstalling=卸载状态
StatusUninstalling=正在卸载 %1...
ShutdownBlockReasonInstallingApp=正在安装 %1。
ShutdownBlockReasonUninstallingApp=正在卸载 %1。
"""


def installer_variant(include_onnx: bool) -> str:
    return "local_model" if include_onnx else "lite"


def installer_variant_label(include_onnx: bool) -> str:
    return "内含检索模型版" if include_onnx else "无检索模型版"


def setup_base_name(include_onnx: bool) -> str:
    if include_onnx:
        return f"{DISPLAY_NAME}创作平台V{APP_VERSION}"
    return f"{DISPLAY_NAME}创作平台V{APP_VERSION}_无检索模型版"


def setup_exe_path(include_onnx: bool) -> Path:
    return DIST_DIR / f"{setup_base_name(include_onnx)}.exe"


def _safe_rmtree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _upsert_env_values(env_path: Path, values: dict[str, str]) -> None:
    """Update selected .env.example keys while preserving comments and ordering."""
    if not env_path.exists():
        return

    lines = env_path.read_text(encoding="utf-8").splitlines()
    updated_keys: set[str] = set()
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            key, _value = line.split("=", 1)
            normalized_key = key.strip()
            if normalized_key in values:
                output.append(f"{normalized_key}={values[normalized_key]}")
                updated_keys.add(normalized_key)
                continue
        output.append(line)

    missing = [key for key in values if key not in updated_keys]
    if missing and output and output[-1].strip():
        output.append("")
    for key in missing:
        output.append(f"{key}={values[key]}")

    env_path.write_text("\n".join(output) + "\n", encoding="utf-8")


def configure_env_example_for_variant(include_onnx: bool, local_model_available: bool) -> None:
    """Make the bundled-model installer default to local ONNX on first launch."""
    env_path = APP_DIR / ".env.example"
    if not include_onnx or not local_model_available:
        return
    _upsert_env_values(
        env_path,
        {
            "KB_EMBEDDING_PROVIDER": "local_onnx",
            "KB_ONNX_MODEL_DIR": DEFAULT_LOCAL_ONNX_MODEL_DIR,
            "KB_ONNX_MODEL_FILE": "model.onnx",
            "KB_ONNX_TOKENIZER_DIR": "",
            "KB_ONNX_MAX_LENGTH": "512",
            "KB_ONNX_POOLING": "cls",
        },
    )
    print("[OK] 内含检索模型版默认启用本地 ONNX 向量模型")


def clean_installer_artifacts(include_onnx: bool = True) -> bool:
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
    for setup_path in {setup_exe_path(include_onnx), LEGACY_SETUP_EXE_PATH, *LEGACY_VARIANT_SETUP_EXE_PATHS}:
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
        "--add-data",
        f"{VERSION_FILE};.",
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
    args.extend(pyinstaller_knowledge_dependency_args())
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


def populate_app_layout(include_onnx: bool = True) -> bool:
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
    (data_dir / "global_api_config.json").write_text(
        json.dumps(_default_global_api_config(), ensure_ascii=False, indent=2),
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

    local_model_available = False
    if include_onnx:
        if SOURCE_ONNX_MODEL_DIR.exists():
            model_dst = APP_DIR / "novel_agent" / "models" / "embedding" / "default"
            if model_dst.exists():
                _safe_rmtree(model_dst)
            shutil.copytree(SOURCE_ONNX_MODEL_DIR, model_dst)
            local_model_available = True
            (data_dir / "knowledge_base_config.json").write_text(
                json.dumps(_default_knowledge_base_config(local_onnx_enabled=True), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print("[OK] 已内置本地 ONNX 向量模型")
        else:
            print(f"[X] 未找到本地 ONNX 模型: {SOURCE_ONNX_MODEL_DIR.relative_to(ROOT_DIR)}")
            print("    正式发布必须内置检索模型；如仅做本地调试，请使用 --without-onnx。")
            return False
    else:
        (data_dir / "knowledge_base_config.json").write_text(
            json.dumps(_default_knowledge_base_config(local_onnx_enabled=False), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("[OK] 默认不内置本地 ONNX 模型，用户可在设置页按需安装模型包")

    configure_env_example_for_variant(include_onnx=include_onnx, local_model_available=local_model_available)
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


def write_inno_script(include_onnx: bool = True) -> bool:
    """Write the Inno Setup script used to compile the final installer."""
    print("\n[安装包] 生成 Inno Setup 脚本...")
    INSTALLER_DIR.mkdir(parents=True, exist_ok=True)
    app_source = _inno_path(APP_DIR)
    output_dir = _inno_path(DIST_DIR)
    flavor_label = installer_variant_label(include_onnx)
    output_base_name = setup_base_name(include_onnx)
    script = f'''#define MyAppName "{DISPLAY_NAME}创作平台"
#define MyAppVersion "{APP_VERSION}"
#define MyInstallerFlavor "{flavor_label}"
#define MyAppExeName "{DISPLAY_NAME}.exe"
#define SourceDir "{app_source}"

[Setup]
AppId={{{{F10F6C34-26F1-451F-9C41-650D29F5918D}}}}
AppName={{#MyAppName}}
AppVersion={{#MyAppVersion}}
AppVerName={{#MyAppName}} V{{#MyAppVersion}}
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
Source: "{{#SourceDir}}\\*"; DestDir: "{{app}}"; Excludes: "data\\*,.env"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{{#SourceDir}}\\data\\*"; DestDir: "{{app}}\\data"; Flags: ignoreversion recursesubdirs createallsubdirs onlyifdoesntexist uninsneveruninstall

[Dirs]
Name: "{{app}}\\data"; Flags: uninsneveruninstall
Name: "{{app}}\\data\\projects"; Flags: uninsneveruninstall
Name: "{{app}}\\data\\stats"; Flags: uninsneveruninstall
Name: "{{app}}\\data\\sessions"; Flags: uninsneveruninstall
Name: "{{app}}\\data\\logs"; Flags: uninsneveruninstall
Name: "{{app}}\\data\\knowledge_base"; Flags: uninsneveruninstall
Name: "{{app}}\\data\\backups"; Flags: uninsneveruninstall

[Icons]
Name: "{{group}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"
Name: "{{autodesktop}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: unchecked

[Run]
Filename: "{{cmd}}"; Parameters: "/C if not exist ""{{app}}\\.env"" copy ""{{app}}\\.env.example"" ""{{app}}\\.env"""; Flags: runhidden
Filename: "{{app}}\\{{#MyAppExeName}}"; Description: "启动 {{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
procedure ForceStopRunningApp();
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{{cmd}}'), '/C taskkill /F /T /IM "{{#MyAppExeName}}" >NUL 2>NUL', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(600);
end;

function InitializeSetup(): Boolean;
begin
  ForceStopRunningApp();
  Result := True;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  ForceStopRunningApp();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  ForceStopRunningApp();
  Result := True;
end;
{CHINESE_INNO_MESSAGES}
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


def compile_inno_installer(include_onnx: bool = True, skip_compile: bool = False) -> bool:
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


def print_summary(include_onnx: bool = True) -> None:
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
    parser.add_argument("--include-onnx", action="store_true", help="bundle local ONNX embedding model (default for release builds)")
    parser.add_argument("--without-onnx", action="store_true", help="local debug only: build without bundled ONNX model")
    parser.add_argument("--skip-compile", action="store_true", help="do not call Inno Setup compiler")
    args = parser.parse_args()
    if args.include_onnx and args.without_onnx:
        parser.error("--include-onnx 和 --without-onnx 不能同时使用")
    include_onnx = not args.without_onnx

    print("=" * 60)
    print(f"{DISPLAY_NAME} - 安装包构建脚本")
    print("=" * 60)
    print("本脚本会生成安装版应用目录，并在检测到 Inno Setup 时生成 Setup.exe。")
    print("默认不内置 Node.js；正式发布默认内置本地 ONNX 模型。")
    if include_onnx:
        print("[选项] 本次会内置本地 ONNX 模型。")
    else:
        print("[选项] 本次为本地调试包，不内置本地 ONNX 模型。")
    print(f"[版本] 输出安装包后缀: {setup_base_name(include_onnx)}.exe")

    if not check_requirements():
        return 1
    if not args.yes:
        confirm = input("确认开始构建？(y/n): ")
        if confirm.lower() != "y":
            print("已取消")
            return 0

    steps = [
        ("清理安装包产物", lambda: clean_installer_artifacts(include_onnx=include_onnx)),
        ("准备发布数据", prepare_release_data),
        ("PyInstaller onedir 构建", run_pyinstaller_onedir),
        ("创建应用目录结构", lambda: populate_app_layout(include_onnx=include_onnx)),
        ("生成 Inno Setup 脚本", lambda: write_inno_script(include_onnx=include_onnx)),
        ("编译安装包", lambda: compile_inno_installer(include_onnx=include_onnx, skip_compile=args.skip_compile)),
    ]
    for name, func in steps:
        print(f"\n{'=' * 60}")
        print(f"步骤: {name}")
        print("=" * 60)
        if not func():
            print(f"\n[X] {name} 失败，构建中止")
            return 1

    print_summary(include_onnx=include_onnx)
    print("\n构建流程完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
