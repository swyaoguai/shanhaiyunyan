#!/usr/bin/env python3
"""
便携版打包脚本
使用 PyInstaller 打包项目，创建便携目录。

注意：正式发布请使用 build_release.py。发布约定只保留内含检索模型版安装 exe，
不再生成 zip 压缩包。
"""

import os
import sys
import shutil
import hashlib
import subprocess
import json
import time
import re
from pathlib import Path
from datetime import datetime

# 项目配置
APP_NAME = "山海·云烟"
DISPLAY_NAME = "山海·云烟"
ROOT_DIR = Path(__file__).parent
VERSION_FILE = ROOT_DIR / "VERSION"
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
BUILD_DIR = ROOT_DIR / "build"
DIST_DIR = ROOT_DIR / "dist"


def configure_output_encoding() -> None:
    """Keep redirected build logs readable on Windows."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def read_app_version() -> str:
    """Read the release version from env or VERSION."""
    version = os.environ.get("SHANHAI_APP_VERSION", "").strip()
    if not version:
        version = VERSION_FILE.read_text(encoding="utf-8").strip() if VERSION_FILE.exists() else "1.0.0"
    if not SEMVER_PATTERN.fullmatch(version):
        raise ValueError(f"Invalid app version '{version}'. Expected semantic version like 1.0.1.")
    return version


configure_output_encoding()

APP_VERSION = read_app_version()
PORTABLE_DIR = DIST_DIR / f"{DISPLAY_NAME}_v{APP_VERSION}_Portable"
RELEASE_DATA_DIR = BUILD_DIR / "release_data" / "novel_agent_data"
SOURCE_ONNX_MODEL_DIR = ROOT_DIR / "novel_agent" / "models" / "embedding" / "default"
SOURCE_SKILLS_DIR = ROOT_DIR / "skills"
PRESET_API_CONFIG_ID = "preset-tsc5"
PRESET_API_CONFIG_NAME = "探索仓API"
PRESET_API_BASE = "https://api.tsc5.top/v1"


def calculate_file_hash(file_path: Path, algorithm: str = "sha256") -> str:
    """计算文件哈希值"""
    hash_obj = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()


def _default_trends_config() -> dict:
    return {
        "enabled": True,
        "auto_refresh": False,
        "refresh_interval": 300,
        "default_platforms": ["toutiao", "douyin"],
        "show_in_infinite_write": True,
        "show_in_multi_agent": True
    }


def _default_timeout_settings() -> dict:
    return {
        "llm": {
            "connect": 60,
            "read": 600,
            "write": 120,
            "pool": 60
        },
        "short_story": {
            "input_analysis": 120,
            "fusion": 180,
            "synopsis": 120,
            "outline": 180,
            "chapter": 300,
            "quality": 1800,
            "coherence": 1800,
            "title": 120,
            "tags": 120
        }
    }


def _default_skills_config() -> dict:
    return {
        "enabled_skills": {
            "trends_search": True,
            "agent_reach": True
        }
    }


def _default_global_api_config() -> dict:
    return {
        "configs": [
            {
                "id": PRESET_API_CONFIG_ID,
                "name": PRESET_API_CONFIG_NAME,
                "api_base": PRESET_API_BASE,
                "api_key": "",
                "api_keys": [],
                "models": [],
                "temperature": 0.7,
                "max_tokens": 4096,
                "created_at": "",
                "api_type": "openai_chat",
            }
        ],
        "active_config_id": PRESET_API_CONFIG_ID,
        "active_model": "",
    }


def _default_knowledge_base_config(local_onnx_enabled: bool = False) -> dict:
    return {
        "embedding_provider": "local_onnx" if local_onnx_enabled else "api",
        "siliconflow_api_key": "",
        "siliconflow_base_url": "https://api.siliconflow.cn/v1",
        "siliconflow_model": "BAAI/bge-m3",
        "siliconflow_embedding_dim": 1024,
        "onnx_model_dir": "novel_agent/models/embedding/default" if local_onnx_enabled else "",
        "onnx_model_file": "model.onnx",
        "onnx_tokenizer_dir": "",
        "onnx_max_length": 512,
        "onnx_threads": None,
        "onnx_pooling": "cls",
        "chunk_size": 500,
        "chunk_overlap": 50,
        "vector_weight": 0.7,
        "fulltext_weight": 0.3,
        "default_top_k": 5,
        "summary_search_enabled": False,
        "chapter_search_mode": "hybrid",
    }


def pyinstaller_skill_dependency_args() -> list[str]:
    """Return explicit PyInstaller args for dynamically loaded Skill dependencies."""
    return [
        "--hidden-import", "bs4",
        "--hidden-import", "bs4.builder._htmlparser",
        "--hidden-import", "ddgs",
        "--collect-submodules", "ddgs",
    ]


def pyinstaller_knowledge_dependency_args() -> list[str]:
    """Return PyInstaller args for ChromaDB modules loaded dynamically at runtime."""
    return [
        "--hidden-import", "chromadb.telemetry.product.posthog",
        "--hidden-import", "chromadb.api.rust",
        "--collect-submodules", "chromadb",
        "--collect-data", "chromadb",
    ]


def pyinstaller_optional_exclude_args() -> list[str]:
    """Return PyInstaller excludes for optional dev/ML stacks not needed at runtime."""
    optional_modules = [
        "datasets",
        "matplotlib",
        "nltk",
        "pandas",
        "scipy",
        "sklearn",
        "sentence_transformers",
        "torch",
        "torchaudio",
        "torchvision",
        "transformers",
    ]
    args: list[str] = []
    for module in optional_modules:
        args.extend(["--exclude-module", module])
    return args


def prepare_release_data():
    """准备不含个人信息的发布数据副本，不修改开发环境数据。"""
    print("\n[准备] 创建干净发布数据副本...")

    if RELEASE_DATA_DIR.exists():
        shutil.rmtree(RELEASE_DATA_DIR)
    RELEASE_DATA_DIR.mkdir(parents=True, exist_ok=True)

    for dirname in ("projects", "stats", "sessions"):
        path = RELEASE_DATA_DIR / dirname
        path.mkdir(parents=True, exist_ok=True)
        (path / ".gitkeep").touch()

    (RELEASE_DATA_DIR / "trends_config.json").write_text(
        json.dumps(_default_trends_config(), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    (RELEASE_DATA_DIR / "timeout_settings.json").write_text(
        json.dumps(_default_timeout_settings(), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    (RELEASE_DATA_DIR / "skills_config.json").write_text(
        json.dumps(_default_skills_config(), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    (RELEASE_DATA_DIR / "global_api_config.json").write_text(
        json.dumps(_default_global_api_config(), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    (RELEASE_DATA_DIR / "knowledge_base_config.json").write_text(
        json.dumps(_default_knowledge_base_config(local_onnx_enabled=False), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"[OK] 发布数据副本: {RELEASE_DATA_DIR.relative_to(ROOT_DIR)}")
    print("[OK] 未修改 .env、data/、novel_agent/data/ 中的开发数据")
    return True


def clean_build_artifacts():
    """清理旧的构建产物"""
    print("\n[清理] 清理旧的构建产物...")

    def _safe_rmtree(path: Path, retries: int = 3, delay: float = 1.0) -> bool:
        """Windows下安全删除目录，处理文件占用"""
        for i in range(retries):
            try:
                shutil.rmtree(path)
                return True
            except PermissionError:
                if i < retries - 1:
                    print(f"[Warning] 文件被占用，{delay}秒后重试删除: {path}")
                    time.sleep(delay)
                else:
                    print(f"[X] 删除失败，请先关闭正在运行的EXE: {path}")
                    return False
        return False

    # 清理dist目录
    if DIST_DIR.exists():
        if not _safe_rmtree(DIST_DIR):
            return False
        print(f"[OK] 删除 dist 目录")
    
    # 清理 build 目录中的 PyInstaller 临时文件。
    if BUILD_DIR.exists():
        for item in BUILD_DIR.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            print(f"[OK] 删除 {item.name}")
    
    return True


def check_requirements():
    """检查构建依赖"""
    try:
        import PyInstaller
        print(f"[OK] PyInstaller 已安装 (版本 {PyInstaller.__version__})")
    except ImportError:
        print("[X] PyInstaller 未安装")
        print("    请运行: pip install pyinstaller")
        return False
    
    return True


def run_pyinstaller():
    """使用PyInstaller打包为单一exe文件"""
    print("\n[构建] 运行PyInstaller...")
    
    # 静态资源路径
    static_dir = ROOT_DIR / "novel_agent" / "web" / "static"
    templates_dir = ROOT_DIR / "novel_agent" / "web" / "templates"
    prompts_dir = ROOT_DIR / "novel_agent" / "prompts"
    data_dir = RELEASE_DATA_DIR
    skills_dir = SOURCE_SKILLS_DIR
    
    # 确保发布数据目录存在并有基本配置
    if not data_dir.exists():
        prepare_release_data()
    
    # 确保trends_config.json存在
    trends_config_file = data_dir / "trends_config.json"
    if not trends_config_file.exists():
        default_config = _default_trends_config()
        trends_config_file.write_text(json.dumps(default_config, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[创建] trends_config.json")
    skills_config_file = data_dir / "skills_config.json"
    if not skills_config_file.exists():
        skills_config_file.write_text(
            json.dumps(_default_skills_config(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"[创建] skills_config.json")
    global_api_config_file = data_dir / "global_api_config.json"
    if not global_api_config_file.exists():
        global_api_config_file.write_text(
            json.dumps(_default_global_api_config(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"[创建] global_api_config.json")
    
    # 创建dist目录
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    
    # PyInstaller 命令 - 使用单文件模式
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", DISPLAY_NAME,
        "--noconfirm",
        "--clean",
        "--specpath", str(BUILD_DIR),
        # 使用单文件模式
        "--onefile",
        # 无控制台窗口 - 生产环境使用
        "--noconsole",
        # 添加静态资源
        "--add-data", f"{static_dir};novel_agent/web/static",
        "--add-data", f"{templates_dir};novel_agent/web/templates",
        "--add-data", f"{prompts_dir};novel_agent/prompts",
        "--add-data", f"{data_dir};novel_agent/data",
        "--add-data", f"{VERSION_FILE};.",
        # 隐藏导入
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols",
        "--hidden-import", "uvicorn.protocols.http",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.lifespan",
        "--hidden-import", "uvicorn.lifespan.on",
        "--hidden-import", "pydantic_core",
        "--hidden-import", "pydantic_core._pydantic_core",
        "--collect-all", "pydantic_core",
        "--collect-all", "pydantic",
        # 图标（如果存在）
    ]
    cmd.extend(pyinstaller_skill_dependency_args())
    cmd.extend(pyinstaller_knowledge_dependency_args())
    cmd.extend(pyinstaller_optional_exclude_args())
    if skills_dir.exists():
        cmd.extend(["--add-data", f"{skills_dir};skills"])
    else:
        print("[警告] 未找到 skills 目录，便携包将不内置技能")
    
    # 检查是否有图标文件
    ico_path = ROOT_DIR / "logo.ico"
    if ico_path.exists():
        cmd.extend(["--icon", str(ico_path)])
        print(f"[图标] 使用 logo.ico")
    else:
        print(f"[警告] 未找到 logo.ico，将使用默认图标")
    
    # 添加入口文件
    cmd.append(str(ROOT_DIR / "run.py"))
    
    result = subprocess.run(cmd, cwd=ROOT_DIR)
    
    if result.returncode != 0:
        print("[X] PyInstaller 构建失败")
        return False
    
    # 验证exe是否生成
    exe_path = DIST_DIR / f"{DISPLAY_NAME}.exe"
    if not exe_path.exists():
        print(f"[X] 未找到生成的exe文件: {exe_path}")
        return False
    
    print(f"[OK] PyInstaller 构建完成")
    print(f"     生成文件: {exe_path}")
    print(f"     文件大小: {exe_path.stat().st_size / (1024 * 1024):.1f} MB")

    
    return True


def create_portable_structure():
    """创建便携版目录结构"""
    print("\n[创建] 便携版目录结构...")
    
    # 清理并创建目录
    if PORTABLE_DIR.exists():
        shutil.rmtree(PORTABLE_DIR)
    PORTABLE_DIR.mkdir(parents=True)
    
    # 复制exe文件
    exe_src = DIST_DIR / f"{DISPLAY_NAME}.exe"
    exe_dst = PORTABLE_DIR / f"{DISPLAY_NAME}.exe"
    if exe_src.exists():
        shutil.copy2(exe_src, exe_dst)
        print(f"[OK] 复制 {APP_NAME}.exe")
        exe_src.unlink()
        print(f"[OK] 删除 dist 根目录临时 exe，避免误启动到开发数据")
    
    # 复制配置文件和文档
    resources = [
        (".env.example", ".env.example"),
        ("使用说明.md", "使用说明.md"),
    ]
    
    for src, dst in resources:
        src_path = ROOT_DIR / src
        dst_path = PORTABLE_DIR / dst
        
        if src_path.exists():
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)
            print(f"[OK] 复制 {src}")
        else:
            print(f"[警告] 未找到 {src}")
    
    # 创建data目录结构
    data_dir = PORTABLE_DIR / "data"
    (data_dir / "projects").mkdir(parents=True, exist_ok=True)
    (data_dir / "stats").mkdir(parents=True, exist_ok=True)
    
    # 创建默认配置
    trends_config = _default_trends_config()
    (data_dir / "trends_config.json").write_text(
        json.dumps(trends_config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (data_dir / "timeout_settings.json").write_text(
        json.dumps(_default_timeout_settings(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (data_dir / "skills_config.json").write_text(
        json.dumps(_default_skills_config(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (data_dir / "global_api_config.json").write_text(
        json.dumps(_default_global_api_config(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    
    print("[OK] 创建默认配置")

    if SOURCE_SKILLS_DIR.exists():
        skills_dst = PORTABLE_DIR / "skills"
        if skills_dst.exists():
            shutil.rmtree(skills_dst)
        shutil.copytree(
            SOURCE_SKILLS_DIR,
            skills_dst,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        print(f"[OK] 复制 Skills: {SOURCE_SKILLS_DIR.relative_to(ROOT_DIR)}")
    else:
        print("[警告] 未找到 skills 目录，便携包无法使用技能")

    # 复制本地 ONNX 向量模型到便携目录外置路径，避免运行时依赖开发目录或 PyInstaller 临时目录。
    if SOURCE_ONNX_MODEL_DIR.exists():
        model_dst = PORTABLE_DIR / "novel_agent" / "models" / "embedding" / "default"
        if model_dst.exists():
            shutil.rmtree(model_dst)
        shutil.copytree(SOURCE_ONNX_MODEL_DIR, model_dst)
        (data_dir / "knowledge_base_config.json").write_text(
            json.dumps(_default_knowledge_base_config(local_onnx_enabled=True), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[OK] 复制本地向量模型: {SOURCE_ONNX_MODEL_DIR.relative_to(ROOT_DIR)}")
    else:
        (data_dir / "knowledge_base_config.json").write_text(
            json.dumps(_default_knowledge_base_config(local_onnx_enabled=False), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("[提示] 未找到本地向量模型，便携包将不内置 local_onnx 模型")

    return True


def create_launcher():
    """创建启动器脚本"""
    print("\n[创建] 启动器脚本...")
    
    # Windows批处理文件
    bat_content = f'''@echo off
chcp 65001 > nul
title {DISPLAY_NAME}

echo.
echo ========================================
echo   {DISPLAY_NAME} v{APP_VERSION}
echo ========================================
echo.

REM 检查运行环境和写入权限
echo [1/3] 检查运行环境...
if not exist "%~dp0data" mkdir "%~dp0data" 2>nul
echo test > "%~dp0data\\.write_test" 2>nul
if errorlevel 1 (
    echo.
    echo [错误] 当前目录没有写入权限！
    echo.
    echo 可能的原因：
    echo   - 程序位于受保护的目录（如 C:\\Program Files）
    echo   - 目录权限不足
    echo.
    echo 建议：
    echo   - 将程序移动到有写入权限的目录
    echo     （如桌面、文档文件夹或 D:\\ 盘）
    echo   - 或以管理员身份运行（不推荐）
    echo.
    pause
    exit /b 1
)
del "%~dp0data\\.write_test" 2>nul
echo    [OK] 写入权限检查通过

REM 检查.env文件（静默创建，不强制编辑）
echo [2/3] 检查配置文件...
if not exist "%~dp0.env" (
    if exist "%~dp0.env.example" (
        copy "%~dp0.env.example" "%~dp0.env" > nul
        echo    [提示] 已创建 .env 配置文件
    ) else (
        echo    [警告] 未找到配置文件，将使用默认配置
    )
) else (
    echo    [OK] 配置文件已存在
)

REM 启动应用
echo [3/3] 启动服务...
echo.
echo 正在启动 {DISPLAY_NAME}...
echo 浏览器将自动打开 http://localhost:5656
echo.
echo 提示：
echo   - 首次使用请在Web界面的"设置"页面配置API密钥
echo   - 关闭此窗口将停止服务
echo.
"{DISPLAY_NAME}.exe"

pause
'''
    
    # 创建启动器
    bat_content = "\r\n".join(bat_content.splitlines()) + "\r\n"
    launcher_cn = PORTABLE_DIR / f"启动{DISPLAY_NAME}.bat"
    launcher_cn.write_text(bat_content, encoding="utf-8")
    print(f"[OK] 创建 启动{DISPLAY_NAME}.bat")
    
    launcher_en = PORTABLE_DIR / "Start.bat"
    launcher_en.write_text(bat_content, encoding="utf-8")
    print(f"[OK] 创建 Start.bat")
    
    # 创建README
    readme_content = f'''# {DISPLAY_NAME} v{APP_VERSION}

## 快速开始

1. **解压到合适的位置**
   - ✅ 推荐：桌面、文档文件夹、D盘等用户目录
   - ❌ 避免：C:\\Program Files、系统目录等受保护位置

2. **启动程序**
   - 双击 `启动{DISPLAY_NAME}.bat`
   - 浏览器会自动打开 http://localhost:5656

3. **配置API密钥**
   - 在Web界面点击"设置"
   - 填入您的API密钥
   - 保存配置即可使用

## 系统要求

- Windows 10/11 64位
- 无需安装 Node.js 或其他前端开发依赖
- 需要有写入权限的目录

## 配置说明

### 方式1：Web界面配置（推荐）

1. 启动程序后，在浏览器中打开 http://localhost:5656
2. 点击"设置"标签
3. 在"LLM配置"部分填入您的API密钥
4. 点击"保存配置"

### 方式2：.env 文件配置（可选）

如果您熟悉配置文件，也可以直接编辑 `.env` 文件：

```env
# API配置
OPENAI_API_KEY=your-api-key-here
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4

# 服务器配置（可选）
SERVER_HOST=0.0.0.0
SERVER_PORT=5656
```

**注意**：修改 .env 文件后需要重启程序。

## 目录结构

```
{DISPLAY_NAME}_v{APP_VERSION}_Portable/
├── {DISPLAY_NAME}.exe          # 主程序
├── 启动{DISPLAY_NAME}.bat   # 启动器（推荐）
├── Start.bat               # 启动器（英文）
├── 使用说明.md              # 完整使用说明文档
├── .env                    # 配置文件
├── data/                   # 数据目录
│   ├── projects/          # 项目数据
│   └── stats/             # Token统计
└── skills/                # 技能扩展
```

## 详细文档

请查看 `使用说明.md` 获取完整的使用说明，包括：
- 详细的功能介绍
- 配置说明
- Agent系统详解
- 高级功能使用
- 常见问题解答
- 最佳实践建议

## 常见问题

### 1. 提示"无法写入数据目录"

**原因**：程序位于受保护的目录（如 C:\\Program Files）

**解决方法**：
- 将整个文件夹移动到桌面或文档文件夹
- 或移动到 D:\\ 盘等非系统盘

### 2. 端口被占用

程序会自动寻找可用端口（5656-5665），如果都被占用会提示错误。

**解决方法**：
- 关闭占用端口的其他程序
- 或在 .env 中修改 SERVER_PORT

### 3. 浏览器没有自动打开

**解决方法**：
- 手动打开浏览器访问 http://localhost:5656
- 检查启动窗口中显示的实际端口号

## 数据安全

- 所有数据保存在 `data/` 目录
- 备份时只需复制整个程序文件夹
- API密钥保存在 `.env` 文件中，请妥善保管

## 问题反馈

如遇问题请联系开发者或查看日志文件：
- agent.log：主程序日志
- startup_error.txt：启动错误日志（如果存在）
'''
    
    readme_path = PORTABLE_DIR / "README.md"
    readme_path.write_text(readme_content, encoding="utf-8")
    print("[OK] 创建 README.md")
    
    return True


def generate_hash_file():
    """生成哈希校验文件"""
    print("\n[哈希] 生成校验文件...")
    
    hash_info = {
        "version": APP_VERSION,
        "build_time": datetime.now().isoformat(),
        "files": {}
    }
    
    # 计算所有重要文件的哈希
    important_files = [
        f"{DISPLAY_NAME}.exe",
        ".env.example",
        "使用说明.md",
    ]
    
    for filename in important_files:
        file_path = PORTABLE_DIR / filename
        if file_path.exists():
            sha256_hash = calculate_file_hash(file_path, "sha256")
            md5_hash = calculate_file_hash(file_path, "md5")
            file_size = file_path.stat().st_size
            
            hash_info["files"][filename] = {
                "sha256": sha256_hash,
                "md5": md5_hash,
                "size": file_size
            }
            print(f"[OK] {filename}")
            print(f"     SHA256: {sha256_hash[:16]}...")
            print(f"     MD5: {md5_hash}")
            print(f"     大小: {file_size / (1024 * 1024):.2f} MB")
    
    # 写入JSON格式的哈希文件
    hash_json_path = PORTABLE_DIR / "checksums.json"
    hash_json_path.write_text(
        json.dumps(hash_info, ensure_ascii=False, indent=2), 
        encoding="utf-8"
    )
    print(f"[OK] 生成 checksums.json")
    
    # 同时生成传统的SHA256SUMS格式
    sha256sums_content = []
    for filename, hashes in hash_info["files"].items():
        sha256sums_content.append(f"{hashes['sha256']}  {filename}")
    
    sha256sums_path = PORTABLE_DIR / "SHA256SUMS.txt"
    sha256sums_path.write_text("\n".join(sha256sums_content), encoding="utf-8")
    print(f"[OK] 生成 SHA256SUMS.txt")
    
    return True


def print_summary():
    """打印构建摘要"""
    print("\n" + "=" * 60)
    print("构建完成摘要")
    print("=" * 60)
    
    exe_path = PORTABLE_DIR / f"{DISPLAY_NAME}.exe"
    
    if exe_path.exists():
        print(f"\n单文件exe:")
        print(f"  路径: {exe_path}")
        print(f"  大小: {exe_path.stat().st_size / (1024 * 1024):.1f} MB")
        print(f"  SHA256: {calculate_file_hash(exe_path, 'sha256')}")
    
    print(f"\n便携版目录: {PORTABLE_DIR}")
    print("提示: 正式发布请运行 python build_release.py，只输出内含检索模型版安装 exe。")
    print("\n" + "=" * 60)


def main():
    print("=" * 60)
    print(f"{DISPLAY_NAME} - 便携版打包脚本")
    print("=" * 60)
    print()
    print("本脚本将执行以下操作:")
    print("  1. 清理旧的构建产物")
    print("  2. 创建干净发布数据副本（不修改开发数据）")
    print("  3. 使用PyInstaller打包为单一exe")
    print("  4. 创建便携版目录结构")
    print("  5. 生成哈希校验文件")
    print("  6. 不创建 zip；正式发布请使用 build_release.py")
    print()
    
    # 检查依赖
    if not check_requirements():
        return
    
    # 支持 -y 参数跳过确认
    if len(sys.argv) > 1 and sys.argv[1] == '-y':
        print("自动确认模式")
    else:
        confirm = input("确认开始构建？(y/n): ")
        if confirm.lower() != 'y':
            print("已取消")
            return
    
    # 构建步骤
    steps = [
        ("清理构建产物", clean_build_artifacts),
        ("准备发布数据", prepare_release_data),
        ("PyInstaller打包", run_pyinstaller),
        ("创建目录结构", create_portable_structure),
        ("创建启动器", create_launcher),
        ("生成哈希校验", generate_hash_file),
    ]
    
    for name, func in steps:
        print(f"\n{'='*60}")
        print(f"步骤: {name}")
        print("=" * 60)
        
        if not func():
            print(f"\n[X] {name} 失败，构建中止")
            return
    
    # 打印摘要
    print_summary()
    
    print("\n构建成功完成！")


if __name__ == "__main__":
    main()
