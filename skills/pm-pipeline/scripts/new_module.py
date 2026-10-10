#!/usr/bin/env python3
"""用法: scripts/new_module.py M02 客服中心
在 10-模块/ 下建模块骨架(目录 + state.md + review 一致性对照表模板)。
跨平台:纯 pathlib,无外部依赖。
"""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STATE_TPL = """# {code} {name} · 工作状态

> 每轮工作结束必须更新本文件(AGENTS.md 硬性规则 3)

- 当前阶段:S1 需求采集(S1需求 / S2 PRD / S3流程图 / S4原型 / S5定稿 / DONE)
- 当前版本:PRD 未开始 | 流程图 未开始 | 原型 未开始
- 最近结论:(最近一次客户确认或关键结论,一行)
- 待办:
  - [ ] S1:采集需求,写 02-需求输入/{code}-{name}.md,发 G1 需求确认单
- 阻塞:无
- 更新:{today}
"""

MATRIX_TPL = """# {code} {name} · PRD ↔ 流程图 ↔ 原型 对照表

> G4 闸门必查(CHECKLIST.md)。任一产物改动后同步更新本表。

| PRD 功能点 | 流程图节点 ID | 原型页面 | 状态 |
|---|---|---|---|
| (待填) | | | |
"""


def main() -> int:
    if len(sys.argv) != 3:
        print("用法: new_module.py <编号> <名称>,例: new_module.py M02 客服中心", file=sys.stderr)
        return 2
    code, name = sys.argv[1], sys.argv[2]
    module_dir = ROOT / "10-模块" / f"{code}-{name}"
    if module_dir.is_dir():
        print(f"已存在: {module_dir}")
        return 1
    for sub in ("prd", "flows", "prototype", "review"):
        (module_dir / sub).mkdir(parents=True, exist_ok=True)
    (module_dir / "state.md").write_text(
        STATE_TPL.format(code=code, name=name, today=date.today().isoformat()),
        encoding="utf-8",
    )
    (module_dir / "review" / "一致性对照表.md").write_text(
        MATRIX_TPL.format(code=code, name=name), encoding="utf-8"
    )
    print(f"已创建: {module_dir}")
    for p in sorted(module_dir.rglob("*")):
        print(f"  {p.relative_to(module_dir)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
