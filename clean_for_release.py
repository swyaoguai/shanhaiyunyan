#!/usr/bin/env python3
"""
清理个人数据脚本
运行此脚本以清除所有个人设置和数据，恢复到默认状态
用于发布前准备

使用方法:
  python clean_for_release.py       # 交互式确认
  python clean_for_release.py -y    # 跳过确认直接清理
"""

import os
import sys
import shutil
import json
from pathlib import Path

# 项目根目录
ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "novel_agent" / "data"
ROOT_DATA_DIR = ROOT_DIR / "data"  # 根目录下的data文件夹

def clean_env_file():
    """清理.env文件，重置为模板"""
    env_file = ROOT_DIR / ".env"
    env_template = ROOT_DIR / ".env.example"
    
    if env_file.exists():
        print(f"[清理] 删除 .env 文件")
        env_file.unlink()
    
    # 创建默认.env模板
    default_env = """# OpenAI兼容API配置
OPENAI_API_KEY=
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4

# 硅基流动向量模型配置（可选，用于知识库）
SILICONFLOW_API_KEY=
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_EMBEDDING_MODEL=BAAI/bge-m3
SILICONFLOW_EMBEDDING_DIM=1024

# 服务配置
HOST=0.0.0.0
PORT=5656
DEBUG=false

# 生成配置
MAX_TOKENS=4096
TEMPERATURE=0.7
"""
    env_template.write_text(default_env, encoding="utf-8")
    print(f"[创建] .env.example 模板文件")

def clean_data_directory():
    """清理data目录中的个人数据"""
    
    # 需要删除的文件（novel_agent/data下）
    files_to_delete = [
        DATA_DIR / "global_api_config.json",
        DATA_DIR / "agent_configs.json",
        DATA_DIR / "knowledge_base_config.json",
        DATA_DIR / "projects.json",
    ]
    
    for f in files_to_delete:
        if f.exists():
            print(f"[删除] {f.relative_to(ROOT_DIR)}")
            f.unlink()
    
    # 需要删除的目录（novel_agent/data下）
    dirs_to_delete = [
        DATA_DIR / "projects",
        DATA_DIR / "stats",
        DATA_DIR / "knowledge_base",
        DATA_DIR / "sessions",  # 会话持久化目录
    ]
    
    for d in dirs_to_delete:
        if d.exists():
            print(f"[删除目录] {d.relative_to(ROOT_DIR)}")
            shutil.rmtree(d)
    
    # 清理根目录下的data文件夹
    if ROOT_DATA_DIR.exists():
        print(f"[Delete Dir] {ROOT_DATA_DIR.relative_to(ROOT_DIR)}")
        try:
            shutil.rmtree(ROOT_DATA_DIR)
        except PermissionError as e:
            print(f"[Warning] Some files are locked, trying to force delete...")
            # 尝试使用命令行强制删除
            import subprocess
            try:
                subprocess.run(['cmd', '/c', 'rd', '/s', '/q', str(ROOT_DATA_DIR)],
                             capture_output=True, check=False)
            except Exception:
                print(f"[Skip] Cannot delete {ROOT_DATA_DIR}, please close any applications using it")
    
    # 重置热点配置为默认值
    trends_config = {
        "enabled": True,
        "auto_refresh": False,
        "refresh_interval": 300,
        "default_platforms": ["toutiao", "douyin"],
        "show_in_infinite_write": True,
        "show_in_multi_agent": True
    }
    trends_file = DATA_DIR / "trends_config.json"
    trends_file.write_text(json.dumps(trends_config, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[重置] trends_config.json")

def clean_cache():
    """清理Python缓存"""
    cache_dirs = list(ROOT_DIR.rglob("__pycache__"))
    for d in cache_dirs:
        if d.exists():
            shutil.rmtree(d)
            print(f"[删除缓存] {d.relative_to(ROOT_DIR)}")
    
    # 删除.pyc文件
    for pyc in ROOT_DIR.rglob("*.pyc"):
        pyc.unlink()
        print(f"[删除] {pyc.relative_to(ROOT_DIR)}")

def clean_logs():
    """清理日志文件"""
    for log in ROOT_DIR.rglob("*.log"):
        log.unlink()
        print(f"[删除日志] {log.relative_to(ROOT_DIR)}")

def create_default_directories():
    """创建必要的空目录"""
    dirs_to_create = [
        DATA_DIR / "projects",
        DATA_DIR / "stats",
        DATA_DIR / "sessions",
    ]
    
    for d in dirs_to_create:
        d.mkdir(parents=True, exist_ok=True)
        # 创建.gitkeep保持目录
        (d / ".gitkeep").touch()
        print(f"[创建目录] {d.relative_to(ROOT_DIR)}")

def main():
    print("=" * 50)
    print("NovelAgent - Clean Script")
    print("=" * 50)
    print()
    
    # 支持 -y 参数跳过确认
    if len(sys.argv) > 1 and sys.argv[1] == '-y':
        print("Auto-confirm mode enabled")
    else:
        confirm = input("WARNING: This will delete all user data. Continue? (y/n): ")
        if confirm.lower() != 'y':
            print("Cancelled")
            return
    
    print()
    print("[Start Cleaning]")
    print("-" * 30)
    
    clean_env_file()
    clean_data_directory()
    clean_cache()
    clean_logs()
    create_default_directories()
    
    print("-" * 30)
    print("[Clean Complete]")
    print()
    print("Project has been reset to default state.")

if __name__ == "__main__":
    main()
