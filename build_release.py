#!/usr/bin/env python3
"""Build the public Windows release installer.

The release contract for this project is deliberately small:

- one installer exe with the bundled local ONNX retrieval model

No zip archives, portable folders, or checksum sidecars are kept in dist.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


ROOT_DIR = Path(__file__).parent
VERSION_FILE = ROOT_DIR / "VERSION"
CHANGELOG_FILE = ROOT_DIR / "CHANGELOG.md"
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
CHANGELOG_VERSION_PATTERN = re.compile(r"^## \[v(\d+\.\d+\.\d+)\]", re.MULTILINE)


def configure_output_encoding() -> None:
    """Keep redirected build logs readable on Windows."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def parse_semver(version: str) -> tuple[int, int, int]:
    version = str(version or "").strip()
    if not SEMVER_PATTERN.fullmatch(version):
        raise ValueError(f"Invalid version '{version}'. Expected semantic version like 1.0.1.")
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


def format_semver(parts: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in parts)


def bump_version(version: str, part: str) -> str:
    major, minor, patch = parse_semver(version)
    if part == "major":
        return format_semver((major + 1, 0, 0))
    if part == "minor":
        return format_semver((major, minor + 1, 0))
    if part == "patch":
        return format_semver((major, minor, patch + 1))
    raise ValueError(f"Unsupported bump part: {part}")


def read_version_file(path: Path = VERSION_FILE) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing version file: {path}")
    version = path.read_text(encoding="utf-8").strip()
    parse_semver(version)
    return version


def write_version_file(version: str, path: Path = VERSION_FILE) -> None:
    parse_semver(version)
    path.write_text(f"{version}\n", encoding="utf-8")


def latest_changelog_version(path: Path = CHANGELOG_FILE) -> str | None:
    if not path.exists():
        return None
    versions = [match.group(1) for match in CHANGELOG_VERSION_PATTERN.finditer(path.read_text(encoding="utf-8"))]
    if not versions:
        return None
    return max(versions, key=parse_semver)


def has_unreleased_changes(path: Path = CHANGELOG_FILE) -> bool:
    if not path.exists():
        return False
    content = path.read_text(encoding="utf-8")
    match = re.search(r"^## \[未发布\](.*?)(?=^## \[v|\Z)", content, flags=re.MULTILINE | re.DOTALL)
    return bool(match and re.search(r"^\s*-\s+", match.group(1), flags=re.MULTILINE))


def prepare_release_version(args: argparse.Namespace) -> str:
    current_version = read_version_file()
    if args.version and args.bump:
        raise ValueError("--version 和 --bump 只能选一个")

    if args.version:
        target_version = args.version
        write_version_file(target_version)
        print(f"[版本] 写入指定版本: {current_version} -> {target_version}")
    elif args.bump:
        target_version = bump_version(current_version, args.bump)
        write_version_file(target_version)
        print(f"[版本] 自动升版: {current_version} -> {target_version}")
    else:
        target_version = current_version

    latest_version = latest_changelog_version()
    suggested_patch = bump_version(latest_version, "patch") if latest_version else bump_version(target_version, "patch")
    print(f"[版本] 当前构建版本: {target_version}")
    print(f"[版本] CHANGELOG 最新发布: {latest_version or '未找到'}")
    print(f"[版本] 建议下一个 patch 版本: {suggested_patch}")

    if latest_version and parse_semver(target_version) <= parse_semver(latest_version) and has_unreleased_changes():
        print("[版本] 注意: CHANGELOG 存在未发布记录，但构建版本没有高于最新发布版本。")
        print("       如需发布下一版，请运行: python build_release.py --bump patch")
        if args.strict_version:
            raise ValueError("版本检测未通过: 当前构建版本没有高于 CHANGELOG 最新发布版本")

    return target_version


@dataclass(frozen=True)
class BuildContext:
    app_version: str
    display_name: str
    root_dir: Path
    dist_dir: Path
    app_dir: Path
    expected_exes: tuple[Path, ...]
    calculate_file_hash: Callable[[Path, str], str]


def load_build_context() -> BuildContext:
    from build_installer import APP_DIR, setup_exe_path
    from build_portable import APP_VERSION, DISPLAY_NAME, DIST_DIR, ROOT_DIR as PORTABLE_ROOT_DIR, calculate_file_hash

    return BuildContext(
        app_version=APP_VERSION,
        display_name=DISPLAY_NAME,
        root_dir=PORTABLE_ROOT_DIR,
        dist_dir=DIST_DIR,
        app_dir=APP_DIR,
        expected_exes=(setup_exe_path(True),),
        calculate_file_hash=calculate_file_hash,
    )


def _remove_path(path: Path, root_dir: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()
    print(f"[OK] 删除旧产物: {path.relative_to(root_dir)}")


def clean_release_dist(ctx: BuildContext) -> None:
    """Remove old release artifacts so dist ends with exactly the release exe file."""
    ctx.dist_dir.mkdir(parents=True, exist_ok=True)

    candidates = {
        ctx.app_dir,
        ctx.dist_dir / ctx.display_name,
        ctx.dist_dir / f"{ctx.display_name}.exe",
        ctx.dist_dir / f"{ctx.display_name}_v{ctx.app_version}_Portable",
        ctx.dist_dir / f"{ctx.display_name}_v{ctx.app_version}_Portable.zip",
        ctx.dist_dir / f"{ctx.display_name}_v{ctx.app_version}_Portable.zip.sha256",
        *ctx.expected_exes,
    }
    candidates.update(ctx.dist_dir.glob(f"{ctx.display_name}_v*_*.exe"))
    candidates.update(ctx.dist_dir.glob(f"{ctx.display_name}_v*_Portable"))
    candidates.update(ctx.dist_dir.glob(f"{ctx.display_name}_v*_Portable.zip"))
    candidates.update(ctx.dist_dir.glob(f"{ctx.display_name}_v*_Portable.zip.sha256"))

    for path in sorted(candidates):
        if path.exists():
            _remove_path(path, ctx.root_dir)


def build_subprocess_env(ctx: BuildContext) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["SHANHAI_APP_VERSION"] = ctx.app_version
    return env


def run_installer_build(ctx: BuildContext) -> bool:
    args = [sys.executable, str(ctx.root_dir / "build_installer.py"), "--yes", "--include-onnx"]

    label = "内含检索模型版"
    print(f"\n[构建] {label}")
    result = subprocess.run(args, cwd=ctx.root_dir, env=build_subprocess_env(ctx))
    if result.returncode != 0:
        print(f"[X] {label} 构建失败")
        return False

    exe_path = ctx.expected_exes[0]
    if not exe_path.exists():
        print(f"[X] 未找到输出文件: {exe_path.relative_to(ctx.root_dir)}")
        return False
    return True


def keep_only_release_exes(ctx: BuildContext) -> bool:
    """Prune dist after a successful build."""
    expected = {path.resolve() for path in ctx.expected_exes}
    missing = [path for path in ctx.expected_exes if not path.exists()]
    if missing:
        for path in missing:
            print(f"[X] 缺少发布 exe: {path.relative_to(ctx.root_dir)}")
        return False

    for child in ctx.dist_dir.iterdir():
        if child.resolve() not in expected:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
            print(f"[OK] 清理非发布产物: {child.relative_to(ctx.root_dir)}")
    return True


def print_summary(ctx: BuildContext) -> None:
    print("\n" + "=" * 60)
    print("发布构建完成")
    print("=" * 60)
    for exe_path in ctx.expected_exes:
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        sha256 = ctx.calculate_file_hash(exe_path, "sha256")
        print(f"{exe_path.relative_to(ctx.root_dir)}")
        print(f"  大小: {size_mb:.1f} MB")
        print(f"  SHA256: {sha256}")
    print("=" * 60)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the public Windows release installer.")
    parser.add_argument("--version", help="Set VERSION to an exact semantic version before building, e.g. 1.0.1.")
    parser.add_argument("--bump", choices=("patch", "minor", "major"), help="Bump VERSION before building.")
    parser.add_argument("--strict-version", action="store_true", help="Fail when VERSION is not ahead of the latest CHANGELOG release.")
    parser.add_argument("--check-version-only", action="store_true", help="Only print version detection information.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    args = parse_args(argv or sys.argv[1:])
    try:
        target_version = prepare_release_version(args)
    except Exception as exc:
        print(f"[X] 版本检测失败: {exc}")
        return 1

    os.environ["SHANHAI_APP_VERSION"] = target_version
    if args.check_version_only:
        return 0

    ctx = load_build_context()

    print("=" * 60)
    print(f"{ctx.display_name} v{ctx.app_version} - 内含检索模型版 exe 发布构建")
    print("=" * 60)
    print("输出目标:")
    print(f"  {ctx.expected_exes[0].relative_to(ctx.root_dir)}")
    print("不会生成 zip、便携目录或校验文件。")

    clean_release_dist(ctx)
    if not run_installer_build(ctx):
        return 1
    if not keep_only_release_exes(ctx):
        return 1

    print_summary(ctx)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
