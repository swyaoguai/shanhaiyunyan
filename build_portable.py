#!/usr/bin/env python3
"""
便携版打包脚本
使用PyInstaller打包项目，创建单一exe文件
自动清理数据、添加哈希校验
"""

import os
import sys
import shutil
import zipfile
import hashlib
import urllib.request
import subprocess
import json
import time
from pathlib import Path
from datetime import datetime

# 项目配置
APP_NAME = "NovelAgent"
DISPLAY_NAME = "文思Agent"
APP_VERSION = "1.1.0"
ROOT_DIR = Path(__file__).parent
BUILD_DIR = ROOT_DIR / "build"
DIST_DIR = ROOT_DIR / "dist"
PORTABLE_DIR = DIST_DIR / f"{APP_NAME}_v{APP_VERSION}_Portable"

# Node.js Portable版本下载地址（Windows x64）
NODEJS_URL = "https://nodejs.org/dist/v20.10.0/node-v20.10.0-win-x64.zip"
NODEJS_ZIP = "node-v20.10.0-win-x64.zip"


def calculate_file_hash(file_path: Path, algorithm: str = "sha256") -> str:
    """计算文件哈希值"""
    hash_obj = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()


def clean_before_build():
    """打包前清理所有个人数据"""
    print("\n[清理] 打包前清理个人数据...")
    
    clean_script = ROOT_DIR / "clean_for_release.py"
    if clean_script.exists():
        # 调用清理脚本，使用-y参数跳过确认
        result = subprocess.run(
            [sys.executable, str(clean_script), "-y"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print("[OK] 数据清理完成")
            if result.stdout:
                # 显示清理脚本的输出（可选）
                for line in result.stdout.strip().split('\n')[-5:]:
                    print(f"     {line}")
            return True
        else:
            print(f"[X] 清理失败: {result.stderr}")
            return False
    else:
        print("[Warning] 清理脚本不存在，跳过清理步骤")
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
    
    # 清理build目录中的PyInstaller临时文件（保留Node.js缓存）
    if BUILD_DIR.exists():
        for item in BUILD_DIR.iterdir():
            if item.name != NODEJS_ZIP and not item.name.startswith("node-"):
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                print(f"[OK] 删除 {item.name}")
    
    # 清理spec文件
    for spec in ROOT_DIR.glob("*.spec"):
        spec.unlink()
        print(f"[OK] 删除 {spec.name}")
    
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
    data_dir = ROOT_DIR / "novel_agent" / "data"
    
    # 确保data目录存在并有基本配置
    if not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        print(f"[创建] data目录: {data_dir}")
    
    # 确保trends_config.json存在
    trends_config_file = data_dir / "trends_config.json"
    if not trends_config_file.exists():
        default_config = {
            "enabled": True,
            "auto_refresh": False,
            "refresh_interval": 300,
            "default_platforms": ["toutiao", "douyin"],
            "show_in_infinite_write": True,
            "show_in_multi_agent": True
        }
        trends_config_file.write_text(json.dumps(default_config, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[创建] trends_config.json")
    
    # 创建dist目录
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    
    # PyInstaller 命令 - 使用单文件模式
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--noconfirm",
        "--clean",
        # 使用单文件模式
        "--onefile",
        # 无控制台窗口 - 生产环境使用
        "--noconsole",
        # 添加静态资源
        "--add-data", f"{static_dir};novel_agent/web/static",
        "--add-data", f"{templates_dir};novel_agent/web/templates",
        "--add-data", f"{prompts_dir};novel_agent/prompts",
        "--add-data", f"{data_dir};novel_agent/data",
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
    exe_path = DIST_DIR / f"{APP_NAME}.exe"
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
    exe_src = DIST_DIR / f"{APP_NAME}.exe"
    exe_dst = PORTABLE_DIR / f"{APP_NAME}.exe"
    if exe_src.exists():
        shutil.copy2(exe_src, exe_dst)
        print(f"[OK] 复制 {APP_NAME}.exe")
    
    # 复制配置文件
    resources = [
        (".env.example", ".env.example"),
    ]
    
    for src, dst in resources:
        src_path = ROOT_DIR / src
        dst_path = PORTABLE_DIR / dst
        
        if src_path.exists():
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)
            print(f"[OK] 复制 {src}")
    
    # 创建data目录结构
    data_dir = PORTABLE_DIR / "data"
    (data_dir / "projects").mkdir(parents=True, exist_ok=True)
    (data_dir / "stats").mkdir(parents=True, exist_ok=True)
    
    # 创建默认配置
    trends_config = {
        "enabled": True,
        "auto_refresh": False,
        "refresh_interval": 300,
        "default_platforms": ["toutiao", "douyin"],
        "show_in_infinite_write": True,
        "show_in_multi_agent": True
    }
    (data_dir / "trends_config.json").write_text(
        json.dumps(trends_config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    
    print("[OK] 创建默认配置")
    return True


def download_nodejs():
    """下载Node.js便携版"""
    print("\n[下载] Node.js便携版...")
    
    nodejs_dir = PORTABLE_DIR / "nodejs"
    nodejs_dir.mkdir(parents=True, exist_ok=True)
    
    zip_path = BUILD_DIR / NODEJS_ZIP
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    
    if not zip_path.exists():
        print(f"    下载中: {NODEJS_URL}")
        try:
            urllib.request.urlretrieve(NODEJS_URL, zip_path)
            print(f"[OK] 下载完成: {NODEJS_ZIP}")
        except Exception as e:
            print(f"[X] 下载失败: {e}")
            print("    请手动下载Node.js")
            return False
    else:
        print(f"[OK] 使用缓存: {NODEJS_ZIP}")
    
    # 解压
    print("    解压中...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(BUILD_DIR)
    
    # 移动到目标目录
    extracted_dir = BUILD_DIR / "node-v20.10.0-win-x64"
    if extracted_dir.exists():
        for item in extracted_dir.iterdir():
            shutil.move(str(item), str(nodejs_dir / item.name))
        extracted_dir.rmdir()
    
    print("[OK] Node.js解压完成")
    return True


def create_launcher():
    """创建启动器脚本"""
    print("\n[创建] 启动器脚本...")
    
    # Windows批处理文件
    bat_content = f'''@echo off
chcp 65001 > nul
title {DISPLAY_NAME}

REM 设置环境变量
set PATH=%~dp0nodejs;%PATH%
set NODE_PATH=%~dp0nodejs\\node_modules

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

REM 检查.env文件
echo [2/3] 检查配置文件...
if not exist "%~dp0.env" (
    if exist "%~dp0.env.example" (
        copy "%~dp0.env.example" "%~dp0.env" > nul
        echo    [提示] 已创建 .env 配置文件
        echo.
        echo 请编辑 .env 文件配置您的API密钥，然后重新启动。
        echo.
        notepad "%~dp0.env"
        pause
        exit /b
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
echo 提示：关闭此窗口将停止服务
echo.
"{APP_NAME}.exe"

pause
'''
    
    # 创建启动器
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

2. **配置API密钥**
   - 首次运行会自动创建 `.env` 配置文件
   - 编辑 `.env` 文件，填入您的API密钥

3. **启动程序**
   - 双击 `启动{DISPLAY_NAME}.bat`
   - 浏览器会自动打开 http://localhost:5656

## 系统要求

- Windows 10/11 64位
- 无需安装其他依赖（Node.js已内置）
- 需要有写入权限的目录

## 配置说明

### .env 文件配置项

```env
# API配置
OPENAI_API_KEY=your-api-key-here
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4

# 服务器配置（可选）
SERVER_HOST=0.0.0.0
SERVER_PORT=5656
```

## 目录结构

```
{APP_NAME}_v{APP_VERSION}_Portable/
├── {APP_NAME}.exe          # 主程序
├── 启动{DISPLAY_NAME}.bat   # 启动器（推荐）
├── Start.bat               # 启动器（英文）
├── .env                    # 配置文件
├── data/                   # 数据目录
│   ├── projects/          # 项目数据
│   └── stats/             # Token统计
└── nodejs/                # Node.js运行时
```

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
        f"{APP_NAME}.exe",
        ".env.example",
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


def create_zip():
    """创建发布压缩包"""
    print("\n[打包] 创建发布压缩包...")
    
    zip_name = f"{APP_NAME}_v{APP_VERSION}_Portable.zip"
    zip_path = DIST_DIR / zip_name
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file in PORTABLE_DIR.rglob("*"):
            if file.is_file():
                arcname = file.relative_to(PORTABLE_DIR)
                zipf.write(file, arcname)
    
    # 计算压缩包哈希
    zip_hash = calculate_file_hash(zip_path, "sha256")
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    
    print(f"[OK] 创建: {zip_name}")
    print(f"     大小: {size_mb:.1f} MB")
    print(f"     SHA256: {zip_hash}")
    
    # 写入压缩包哈希
    zip_hash_path = DIST_DIR / f"{zip_name}.sha256"
    zip_hash_path.write_text(f"{zip_hash}  {zip_name}", encoding="utf-8")
    print(f"[OK] 创建: {zip_name}.sha256")
    
    return True


def print_summary():
    """打印构建摘要"""
    print("\n" + "=" * 60)
    print("构建完成摘要")
    print("=" * 60)
    
    exe_path = PORTABLE_DIR / f"{APP_NAME}.exe"
    zip_path = DIST_DIR / f"{APP_NAME}_v{APP_VERSION}_Portable.zip"
    
    if exe_path.exists():
        print(f"\n单文件exe:")
        print(f"  路径: {exe_path}")
        print(f"  大小: {exe_path.stat().st_size / (1024 * 1024):.1f} MB")
        print(f"  SHA256: {calculate_file_hash(exe_path, 'sha256')}")
    
    if zip_path.exists():
        print(f"\n便携版压缩包:")
        print(f"  路径: {zip_path}")
        print(f"  大小: {zip_path.stat().st_size / (1024 * 1024):.1f} MB")
    
    print(f"\n便携版目录: {PORTABLE_DIR}")
    print("\n" + "=" * 60)


def main():
    print("=" * 60)
    print(f"{DISPLAY_NAME} - 便携版打包脚本")
    print("=" * 60)
    print()
    print("本脚本将执行以下操作:")
    print("  1. 清理所有个人数据")
    print("  2. 清理旧的构建产物")
    print("  3. 使用PyInstaller打包为单一exe")
    print("  4. 创建便携版目录结构")
    print("  5. 下载Node.js便携版")
    print("  6. 生成哈希校验文件")
    print("  7. 创建发布压缩包")
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
        ("清理个人数据", clean_before_build),
        ("清理构建产物", clean_build_artifacts),
        ("PyInstaller打包", run_pyinstaller),
        ("创建目录结构", create_portable_structure),
        ("下载Node.js", download_nodejs),
        ("创建启动器", create_launcher),
        ("生成哈希校验", generate_hash_file),
        ("创建压缩包", create_zip),
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