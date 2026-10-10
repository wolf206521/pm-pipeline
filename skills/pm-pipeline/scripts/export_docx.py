#!/usr/bin/env python3
"""用法: scripts/export_docx.py M02-客服中心 [prd版本,默认最新] [--prefix 前缀]
把模块最新版 PRD(及流程图说明)导出为 docx 到 20-交付/。

pandoc 探测顺序:PATH → 常见安装位(macOS/Linux: ~/.local/bin、/usr/local/bin、
/opt/homebrew/bin;Windows: %LOCALAPPDATA%\\Pandoc、Program Files)。
跨平台:pathlib + subprocess,不依赖 textutil。
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def find_pandoc():
    """返回 pandoc 可执行文件路径,找不到返回 None。"""
    on_path = shutil.which("pandoc")
    if on_path:
        return on_path
    candidates = [
        Path.home() / ".local" / "bin" / "pandoc",
        Path("/usr/local/bin/pandoc"),
        Path("/opt/homebrew/bin/pandoc"),
    ]
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / "Pandoc" / "pandoc.exe")
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        candidates.append(Path(program_files) / "Pandoc" / "pandoc.exe")
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def version_key(path):
    """v0.10 排在 v0.9 之后:按数字元组排序。"""
    parts = re.findall(r"\d+", path.stem)
    return tuple(int(p) for p in parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="导出模块 PRD/流程图说明为 docx")
    parser.add_argument("module", help="模块目录名,例: M02-客服中心")
    parser.add_argument("version", nargs="?", help="PRD 版本,例: v0.3(默认最新)")
    parser.add_argument("--prefix", default="", help="交付文件名前缀,例: PROJ(默认无前缀)")
    args = parser.parse_args()

    module_dir = ROOT / "10-模块" / args.module
    if not module_dir.is_dir():
        print(f"模块不存在: {module_dir}")
        return 1

    pandoc = find_pandoc()
    if not pandoc:
        print("pandoc 不可用(预期在 PATH 或常见安装位;Windows 有官方安装包)")
        return 1

    if args.version:
        prd = module_dir / "prd" / f"{args.version}.md"
    else:
        versions = sorted((module_dir / "prd").glob("v*.md"), key=version_key)
        prd = versions[-1] if versions else None
    if prd is None or not prd.is_file():
        print(f"找不到 PRD: {module_dir}/prd/")
        return 1

    code, _, name = args.module.partition("-")
    prefix = f"{args.prefix}_" if args.prefix else ""
    out_dir = ROOT / "20-交付"
    out_dir.mkdir(exist_ok=True)

    out = out_dir / f"{prefix}{code}_{name}_PRD_{prd.stem}.docx"
    subprocess.run(
        [pandoc, "-f", "markdown", "-t", "docx", str(prd), "-o", str(out), "--toc", "--toc-depth=3"],
        check=True,
    )
    print(f"已导出: {out}")

    for f in sorted((module_dir / "flows").glob("*.md")):
        flow_out = out_dir / f"{prefix}{code}_{name}_流程图_{f.stem}.docx"
        subprocess.run([pandoc, "-f", "markdown", "-t", "docx", str(f), "-o", str(flow_out)], check=True)
        print(f"已导出: 20-交付/{flow_out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
