#!/usr/bin/env python3
"""用法: scripts/check_all.py M02-客服中心
交付前自检:check_prd.py + check_mermaid.py + 人工核对项提醒。

自检脚本探测顺序(找到第一个即停):
  1. $KIMI_CODE_HOME/skills
  2. ~/.kimi-code/skills
  3. ~/.agents/skills
  4. ~/.claude/skills
  5. ~/.codex/skills
找不到对应 skill 时跳过该项并提示安装方式,不算失败。
跨平台:纯 pathlib,无外部依赖。
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKILL_DIR_CANDIDATES = [
    Path(os.environ["KIMI_CODE_HOME"]) / "skills" if os.environ.get("KIMI_CODE_HOME") else None,
    Path.home() / ".kimi-code" / "skills",
    Path.home() / ".agents" / "skills",
    Path.home() / ".claude" / "skills",
    Path.home() / ".codex" / "skills",
]

CHECKS = [
    ("PRD", "laowang-prd", "check_prd.py", ("prd", "v*.md")),
    ("流程图", "laowang-diagram", "check_mermaid.py", ("flows", "*.mmd")),
]


def find_check_script(skill_name, script_name):
    for base in SKILL_DIR_CANDIDATES:
        if base is None:
            continue
        candidate = base / skill_name / "scripts" / script_name
        if candidate.is_file():
            return candidate
    return None


def main() -> int:
    if len(sys.argv) != 2:
        print("用法: check_all.py <模块目录名>,例: check_all.py M02-客服中心", file=sys.stderr)
        return 2
    module = sys.argv[1]
    module_dir = ROOT / "10-模块" / module
    if not module_dir.is_dir():
        print(f"模块不存在: {module_dir}")
        return 1

    fail = False
    for label, skill_name, script_name, (sub, pattern) in CHECKS:
        print(f"===== {label} 自检({script_name})=====", flush=True)
        script = find_check_script(skill_name, script_name)
        if script is None:
            print(f"(未找到 {skill_name},跳过;安装该 skill 后自动启用,见 README 依赖说明)")
        else:
            files = sorted((module_dir / sub).glob(pattern))
            if not files:
                print(f"(无{label}文件,跳过)")
            for f in files:
                print(f"--- {f}", flush=True)
                result = subprocess.run([sys.executable, str(script), str(f)])
                if result.returncode != 0:
                    fail = True
        print()

    print("===== 人工核对项(脚本无法替代)=====")
    print("[ ] 各确认点闸门逐条过: 00-体系/CHECKLIST.md")
    print(f"[ ] 三方对照表已更新且无缺口: {module_dir}/review/一致性对照表.md")
    print("[ ] 无编造数值、无模糊词(尽快/适当/若干)")
    print("[ ] 确认结果已记入 state.md 和 01-记忆/决策日志.md")
    print("[ ] 语义闸门: scripts/check_semantic.py(配 JEV_API_KEY 自动启用,否则人工核对)")
    print("[ ] 原型测试: scripts/test_prototype.py <原型目录> --ia <IA清单> --states <状态枚举>")
    print()

    if fail:
        print("结果:存在未通过项,修复后再交付")
        return 1
    print("结果:脚本检查通过,请完成人工核对项")
    return 0


if __name__ == "__main__":
    sys.exit(main())
