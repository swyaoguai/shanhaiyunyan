#!/usr/bin/env python3
"""Build the two public Windows release installers.

The release contract for this project is deliberately small:

- one lightweight installer exe without the bundled local ONNX model
- one local-model installer exe with the bundled local ONNX model

No zip archives, portable folders, or checksum sidecars are kept in dist.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from build_installer import APP_DIR, setup_exe_path
from build_portable import APP_VERSION, DISPLAY_NAME, DIST_DIR, ROOT_DIR, calculate_file_hash


EXPECTED_EXES = (
    setup_exe_path(False),
    setup_exe_path(True),
)


def _remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def clean_release_dist() -> None:
    """Remove old release artifacts so dist ends with exactly the two exe files."""
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    candidates = {
        APP_DIR,
        DIST_DIR / DISPLAY_NAME,
        DIST_DIR / f"{DISPLAY_NAME}.exe",
        DIST_DIR / f"{DISPLAY_NAME}_v{APP_VERSION}_Portable",
        DIST_DIR / f"{DISPLAY_NAME}_v{APP_VERSION}_Portable.zip",
        DIST_DIR / f"{DISPLAY_NAME}_v{APP_VERSION}_Portable.zip.sha256",
        *EXPECTED_EXES,
    }
    for path in candidates:
        if path.exists():
            _remove_path(path)
            print(f"[OK] 删除旧产物: {path.relative_to(ROOT_DIR)}")


def run_installer_build(include_onnx: bool) -> bool:
    args = [sys.executable, str(ROOT_DIR / "build_installer.py"), "--yes"]
    if include_onnx:
        args.append("--include-onnx")

    label = "本地模型版" if include_onnx else "轻量版"
    print(f"\n[构建] {label}")
    result = subprocess.run(args, cwd=ROOT_DIR)
    if result.returncode != 0:
        print(f"[X] {label} 构建失败")
        return False

    exe_path = setup_exe_path(include_onnx)
    if not exe_path.exists():
        print(f"[X] 未找到输出文件: {exe_path.relative_to(ROOT_DIR)}")
        return False
    return True


def keep_only_release_exes() -> bool:
    """Prune dist after a successful build."""
    expected = {path.resolve() for path in EXPECTED_EXES}
    missing = [path for path in EXPECTED_EXES if not path.exists()]
    if missing:
        for path in missing:
            print(f"[X] 缺少发布 exe: {path.relative_to(ROOT_DIR)}")
        return False

    for child in DIST_DIR.iterdir():
        if child.resolve() not in expected:
            _remove_path(child)
            print(f"[OK] 清理非发布产物: {child.relative_to(ROOT_DIR)}")
    return True


def print_summary() -> None:
    print("\n" + "=" * 60)
    print("发布构建完成")
    print("=" * 60)
    for exe_path in EXPECTED_EXES:
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        sha256 = calculate_file_hash(exe_path, "sha256")
        print(f"{exe_path.relative_to(ROOT_DIR)}")
        print(f"  大小: {size_mb:.1f} MB")
        print(f"  SHA256: {sha256}")
    print("=" * 60)


def main() -> int:
    print("=" * 60)
    print(f"{DISPLAY_NAME} v{APP_VERSION} - 双版本 exe 发布构建")
    print("=" * 60)
    print("输出目标:")
    print(f"  1. {EXPECTED_EXES[0].relative_to(ROOT_DIR)}")
    print(f"  2. {EXPECTED_EXES[1].relative_to(ROOT_DIR)}")
    print("不会生成 zip、便携目录或校验文件。")

    clean_release_dist()
    if not run_installer_build(include_onnx=False):
        return 1
    if not run_installer_build(include_onnx=True):
        return 1
    if not keep_only_release_exes():
        return 1

    print_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
