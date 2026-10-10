#!/usr/bin/env python3
"""用法: scripts/check_semantic.py <模块目录名> [--threshold 0.7]
语义级自检闸门:在脚本级自检(check_all.py 的 check_prd/check_mermaid)之上,
用 Jev 做语义判断——指标是否可量化、状态机是否有出口、字段字典是否完整、
三方对照是否真一致。

行为:
  - 决策后端可用(Jev:配了 JEV_API_KEY;Kev:JEV_BACKEND=kev + KEV_BASE_URL 指向已启动服务):
    调 System One 接口(一次调用批量问多题),逐项给出 PASS / FAIL / REVIEW
    REVIEW = 置信度低于阈值,必须人工复核该项(与「低置信转人工」规则一致)
  - 后端不可用:降级为输出人工核对清单(现有行为),退出码 0

退出码:0=全部 PASS(或降级);1=存在 FAIL/REVIEW;2=用法错误;3=配了 key 但调用失败。
跨平台:纯标准库,Python ≥3.8;依赖同目录 jev_decide.py。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jev_decide  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# 语义闸门条目:(问题 ID, 类型, instructions) —— 一问一判断,批量一次调用
def build_questions(has_matrix):
    questions = {
        "metrics_quantifiable": {
            "type": "noul",
            "instructions": (
                "`prd` 的业务背景含可量化衡量指标(有具体数值、口径或目标值),"
                "而不是只有「提升体验」「优化效率」类口号?"
            ),
        },
        "state_machine_has_exits": {
            "type": "noul",
            "instructions": (
                "`prd` 状态机中每个状态都有入边和出边、存在终态,"
                "没有进得去出不来的状态孤岛?"
            ),
        },
        "field_dict_complete": {
            "type": "noul",
            "instructions": (
                "`prd` 字段字典中每个字段都标注了类型、必填、边界值、校验规则和默认值?"
            ),
        },
    }
    if has_matrix:
        questions["matrix_truly_consistent"] = {
            "type": "noul",
            "instructions": (
                "`matrix` 三方对照表每一行在 PRD 功能点、流程图节点、原型页面三列都有真实填写,"
                "状态列没有「不一致」「待补」「缺口」类标记,不是形式主义填表?"
            ),
        }
    return questions


# 降级时的人工核对清单(与 00-体系/CHECKLIST.md G2/G4 条目对应)
MANUAL_CHECKLIST = [
    "[ ] 业务背景有可量化衡量指标(具体数值/口径,不是「提升体验」)",
    "[ ] 状态机每个状态有入边和出边,有终态,无状态孤岛",
    "[ ] 字段字典每字段标了类型/必填/边界值/校验/默认值",
    "[ ] 三方对照表逐行真实对应,无「不一致/待补」残留",
]


def latest_file(module_dir, sub, pattern):
    files = sorted((module_dir / sub).glob(pattern))
    return files[-1] if files else None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = {a.split("=")[0][2:]: a.split("=")[1] for a in sys.argv[1:] if a.startswith("--") and "=" in a}
    if "-h" in sys.argv or "--help" in sys.argv:
        print(__doc__)
        return 0
    if len(args) != 1:
        print(__doc__)
        return 2
    threshold = float(opts.get("threshold", 0.7))
    module_dir = ROOT / "10-模块" / args[0]
    if not module_dir.is_dir():
        # 也支持直接传模块目录路径
        module_dir = Path(args[0])
        if not module_dir.is_dir():
            print(f"模块不存在: {args[0]}", file=sys.stderr)
            return 2

    prd = latest_file(module_dir, "prd", "v*.md")
    matrix = module_dir / "review" / "一致性对照表.md"
    if prd is None:
        print(f"(无 PRD 文件: {module_dir}/prd/v*.md,语义自检跳过)", file=sys.stderr)
        return 2

    state = {"prd": prd.read_text(encoding="utf-8")[:12000]}  # 截断控 token
    if matrix.is_file():
        state["matrix"] = matrix.read_text(encoding="utf-8")[:6000]

    if not jev_decide.configured():
        print("决策后端不可用(未配置 JEV_API_KEY,或 JEV_BACKEND=kev 但未启动),")
        print("语义自检降级为人工核对清单(配好 Jev key 或启动 Kev 后自动启用):")
        print(f"  对照文件: {prd}")
        for item in MANUAL_CHECKLIST:
            print("  " + item)
        return 0

    backend = jev_decide.get_config()["backend"]
    print(f"语义自检({backend}): {prd}" + (f" + {matrix.name}" if matrix.is_file() else ""))
    req = {"state": state, "questions": build_questions(matrix.is_file())}
    try:
        out = jev_decide.decide(req, default_threshold=threshold)
    except jev_decide.JevUnavailable as e:
        print(f"决策后端调用失败({e}),降级为人工核对清单:")
        for item in MANUAL_CHECKLIST:
            print("  " + item)
        return 3

    fail = False
    for qid, a in out["answers"].items():
        if a["route"] == "human":
            verdict = "REVIEW(低置信,转人工)"
            fail = True
        elif a["decision"] == "yes":
            verdict = "PASS"
        else:
            verdict = "FAIL(高置信判否)"
            fail = True
        print(f"  [{verdict}] {qid}: confidence={a['confidence']:.2f} 阈值={a['threshold']:.2f}")
    print(f"(model={out.get('model')}, usage={out.get('usage')})")
    if fail:
        print("结果:存在 FAIL/REVIEW 项,修复或人工复核后再过闸门")
        return 1
    print("结果:语义自检全部 PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
