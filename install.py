#!/usr/bin/env python3
"""pm-pipeline 安装器:把 skills/pm-pipeline 复制到各 Agent 工具的 skills 目录。

用法:
  python3 install.py              # 探测并安装到所有已发现的 skills 目录
  python3 install.py --target ~/.claude/skills   # 只装到指定目录
  python3 install.py --dry-run    # 只打印将要执行的动作

探测顺序:$KIMI_CODE_HOME/skills → ~/.kimi-code/skills → ~/.agents/skills
→ ~/.claude/skills → ~/.codex/skills(只安装到已存在的目录,不新建)。
跨平台:pathlib + shutil,Windows/macOS/Linux 通用。
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

SKILL_NAME = "pm-pipeline"
SRC = Path(__file__).resolve().parent / "skills" / SKILL_NAME

CANDIDATES = [
    Path(os.environ["KIMI_CODE_HOME"]) / "skills" if os.environ.get("KIMI_CODE_HOME") else None,
    Path.home() / ".kimi-code" / "skills",
    Path.home() / ".agents" / "skills",
    Path.home() / ".claude" / "skills",
    Path.home() / ".codex" / "skills",
]


def install(target: Path, dry_run: bool) -> None:
    dest = target / SKILL_NAME
    if dry_run:
        print(f"[dry-run] 将安装到 {dest}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(SRC, dest)
    print(f"已安装: {dest}")


def main() -> int:
    parser = argparse.ArgumentParser(description="安装 pm-pipeline skill 到 Agent 工具 skills 目录")
    parser.add_argument("--target", help="只安装到指定 skills 目录(不存在则创建)")
    parser.add_argument("--dry-run", action="store_true", help="只打印动作,不执行")
    args = parser.parse_args()

    if not SRC.is_dir():
        print(f"找不到 skill 源目录: {SRC}", file=sys.stderr)
        return 1

    if args.target:
        install(Path(args.target).expanduser(), args.dry_run)
        return 0

    found = [c for c in CANDIDATES if c is not None and c.is_dir()]
    if not found:
        print("未发现任何 Agent 工具的 skills 目录;请用 --target 显式指定。")
        return 1
    for target in found:
        install(target, args.dry_run)
    print(f"完成:共安装到 {len(found)} 个目录")
    return 0


if __name__ == "__main__":
    sys.exit(main())
