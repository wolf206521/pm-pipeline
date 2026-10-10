#!/usr/bin/env python3
"""用法: scripts/refresh_baseline.py [--auth 权威源目录] [--archive 历史源目录]
          [--outline-keyword 关键词]...(可重复,追加历史大纲识别关键词)

扫描两类源,重建 01-记忆/源资料基线.md 与 02-需求输入/提取缓存/:
  权威源(默认 工程/客户需求/)     —— 最新完整需求(大纲+全模块说明书+原型包)
  历史源(--archive 指定,可选)   —— 各模块历史版本(只读)

选版规则:版本号高者优先;同版本取修改时间最新;同版本多文件标 ⚠️,
人工确认登记在 01-记忆/基线确认.md(格式: <模块编号>=<文件名>|)。

docx 提取一律走 pandoc(权威文档转 gfm 保留结构,历史文档转 plain 文本),
不依赖 macOS textutil。跨平台:pathlib + zipfile + subprocess。
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "02-需求输入" / "提取缓存"
PROTO = ROOT / "02-需求输入" / "原型参考"
OUT = ROOT / "01-记忆" / "源资料基线.md"
CONFIRM = ROOT / "01-记忆" / "基线确认.md"

VER_RE = re.compile(r"V[0-9]+([._][0-9]+)*")
CODE_RE = re.compile(r"M[0-9][0-9]")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def find_pandoc():
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


def mdate(path):
    return datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()


def extract_ver(name):
    """文件名中提取版本号:V11_9 -> '11.9',V1.2 -> '1.2';无则 '0'。"""
    m = VER_RE.search(name)
    if not m:
        return "0"
    return m.group(0).lstrip("V").replace("_", ".")


def ver_pair(ver):
    parts = ver.split(".")
    major = int(parts[0]) if parts and parts[0].isdigit() else 0
    minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return major, minor


def pick_latest(entries):
    """entries: [(ver, mtime, mdate, base)] -> 最新一条;排序键 (major, minor, mtime)。"""
    if not entries:
        return None
    return max(entries, key=lambda e: (*ver_pair(e[0]), e[1]))


def pandoc_convert(pandoc, src, fmt, dst):
    subprocess.run(
        [pandoc, "-f", "docx", "-t", fmt, "--wrap=none", str(src), "-o", str(dst)],
        check=True, capture_output=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="重建源资料基线与提取缓存")
    parser.add_argument("--auth", default=str(ROOT / "客户需求"), help="权威源目录(默认 工程/客户需求)")
    parser.add_argument("--archive", default=None, help="历史源目录(可选,只读)")
    parser.add_argument("--outline-keyword", action="append", default=[],
                        help="追加历史大纲文件名识别关键词(默认已含: 设计大纲、PRD-设计大纲)")
    parser.add_argument("--dry-run", action="store_true",
                        help="只扫描并打印选版结果,不写任何文件(用于安装后路径自检)")
    args = parser.parse_args()

    auth = Path(args.auth)
    archive = Path(args.archive) if args.archive else None
    outline_keywords = ["设计大纲", "PRD-设计大纲"] + args.outline_keyword

    (CACHE / "历史").mkdir(parents=True, exist_ok=True)
    PROTO.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp())

    # ---------- 1. 扫描权威源 ----------
    a_outline, a_full, a_proto, a_other = [], [], [], []
    for f in sorted(auth.iterdir()) if auth.is_dir() else []:
        if not f.is_file() or f.name.startswith("."):
            continue
        base = f.name
        mt = f.stat().st_mtime
        if f.suffix == ".docx":
            if "设计大纲" in base:
                a_outline.append((extract_ver(base), mt, mdate(f), base))
            elif "全模块" in base:
                a_full.append((extract_ver(base), mt, mdate(f), base))
            else:
                a_other.append((mt, mdate(f), base))
        elif f.suffix == ".zip":
            a_proto.append((mt, mdate(f), base))
    best_outline = pick_latest(a_outline)
    best_full = pick_latest(a_full)

    # ---------- 2. 扫描历史源 ----------
    audit, h_outline, companion, req, modules, unclassified = [], [], [], [], [], []
    if archive and archive.is_dir():
        for f in sorted(archive.iterdir()):
            if not f.is_file() or f.suffix not in (".docx", ".pdf") or f.name.startswith("."):
                continue
            base = f.name
            mt = f.stat().st_mtime
            md = mdate(f)
            if any(k in base for k in ("审核报告", "评审", "批注")):
                audit.append((mt, md, base))
            elif any(k in base for k in outline_keywords):
                m = re.search(r"V[0-9]+(\.[0-9]+)?", base)
                h_outline.append((m.group(0).lstrip("V") if m else "0", mt, md, base))
            elif any(k in base for k in ("需求说明书", "建设方案")):
                m = CODE_RE.search(base)
                companion.append((m.group(0) if m else "??", mt, md, base))
            elif any(k in base for k in ("需求填写表", "操作需求", "智能接单", "接单流程")):
                req.append((mt, md, base))
            elif "详细" in base and "说明书" in base and base.index("详细") < base.index("说明书"):
                m = CODE_RE.search(base)
                if not m:
                    unclassified.append((mt, md, base))
                    continue
                raw_m = VER_RE.search(base)
                raw = raw_m.group(0).lstrip("V") if raw_m else ""
                nums = re.split(r"[._]", raw)
                v1 = nums[0] if nums and nums[0] else "0"
                v2 = nums[1] if len(nums) > 1 else ""
                ver = f"{v1}.{v2}" if v2 else f"{v1}.0"
                modules.append((m.group(0), ver, mt, md, base))
            else:
                unclassified.append((mt, md, base))

    def latest_per_module():
        """[(code, ver, mtime, mdate, base)] 每个模块取最新版本。"""
        result = []
        for code in sorted({m[0] for m in modules}):
            group = [m for m in modules if m[0] == code]
            result.append(max(group, key=lambda e: (*ver_pair(e[1]), e[2])))
        return result

    if args.dry_run:
        print("=== dry-run:只扫描不写文件 ===")
        print(f"权威源: {auth} ({'存在' if auth.is_dir() else '不存在!'})")
        if best_outline:
            print(f"  设计大纲最新: V{best_outline[0]} `{best_outline[3]}`")
        else:
            print("  设计大纲: (未找到)")
        if best_full:
            print(f"  全模块说明书最新: V{best_full[0]} `{best_full[3]}`")
        else:
            print("  全模块说明书: (未找到)")
        print(f"  原型包: {len(a_proto)} 个;未归类: {len(a_other)} 个")
        if archive:
            print(f"历史源: {archive} ({'存在' if archive.is_dir() else '不存在!'})")
            for code, ver, mt, md, base in latest_per_module():
                print(f"  {code}: V{ver} `{base}`")
            print(f"  历史大纲: {len(h_outline)} 个;配套: {len(companion)};原始需求: {len(req)};评审: {len(audit)};未归类: {len(unclassified)}")
        else:
            print("历史源: 未指定(--archive),跳过历史扫描")
        print("dry-run 通过:路径与选版规则可用")
        return 0

    pandoc = find_pandoc()
    if not pandoc:
        print("pandoc 不可用(预期在 PATH 或常见安装位;Windows 有官方安装包)")
        return 1

    # ---------- 3. 提取缓存 ----------
    full_md = None
    full_date = None
    if best_full:
        full_ver, _, _, full_base = best_full
        fs_dir = CACHE / f"全模块_V{full_ver}"
        if fs_dir.exists():
            shutil.rmtree(fs_dir)
        fs_dir.mkdir(parents=True)
        full_md = tmp / "full.md"
        pandoc_convert(pandoc, auth / full_base, "gfm", full_md)
        current = None
        targets = {}
        for line in full_md.read_text(encoding="utf-8").splitlines(keepends=True):
            heading = re.match(r"^# \*\*第 [0-9]+ 篇", line)
            appendix = re.match(r"^# \*\*附录", line)
            if heading:
                m = CODE_RE.search(line)
                current = fs_dir / f"{m.group(0)}.md" if m else current
            elif appendix:
                current = fs_dir / "附录.md"
            else:
                if current is None:
                    current = fs_dir / "00-全局约定.md"
                if current not in targets:
                    targets[current] = current.open("a", encoding="utf-8")
                targets[current].write(line)
        for fh in targets.values():
            fh.close()
        for line in full_md.read_text(encoding="utf-8").splitlines():
            if "发布日期" in line:
                m = DATE_RE.search(line)
                if m:
                    full_date = m.group(0)
                    break
        n = len(list(fs_dir.iterdir()))
        print(f"全模块说明书已拆分: {fs_dir} ({n} 个文件)")

    o_date = None
    if best_outline:
        o_ver, _, _, o_base = best_outline
        for old in CACHE.glob("大纲_*.md"):
            old.unlink()
        o_out = CACHE / f"大纲_V{o_ver}.md"
        pandoc_convert(pandoc, auth / o_base, "gfm", o_out)
        for line in o_out.read_text(encoding="utf-8").splitlines()[:30]:
            m = DATE_RE.search(line)
            if m:
                o_date = m.group(0)
                break
        print(f"大纲已提取: 提取缓存/大纲_V{o_ver}.md")

    proto_done = []
    for mt, md, base in a_proto:
        name = base[: -len(".zip")]
        dest = PROTO / name
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(auth / base) as zf:
            zf.extractall(dest)
        pages = len(list(dest.rglob("*.html")))
        proto_done.append((name, md, pages))

    for old in (CACHE / "历史").glob("*.txt"):
        old.unlink()
    for code, ver, mt, md, base in latest_per_module():
        src = archive / base
        try:
            pandoc_convert(pandoc, src, "plain", CACHE / "历史" / f"{code}_V{ver}.txt")
        except subprocess.CalledProcessError:
            print(f"⚠️ 提取失败: {base}")

    # ---------- 4. 原型参考 README ----------
    lines = [
        "# 原型参考(客户交付)",
        "",
        "> ⚠️ 客户说明:这些页面是**独立功能演示,未与主体后台互通**,仅作为布局与交互的参考。功能逻辑以说明书为准。",
        "",
        "| 原型包 | 日期 | 页面数 | 目录 |",
        "|---|---|---|---|",
    ]
    for name, md, pages in proto_done:
        lines.append(f"| {name} | {md} | {pages} | `{name}/` |")
    (PROTO / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ---------- 5. 生成基线文件 ----------
    confirm_lines = CONFIRM.read_text(encoding="utf-8").splitlines() if CONFIRM.is_file() else []
    out = [
        "# 源资料基线",
        "",
        f"> 由 `scripts/refresh_baseline.py` 于 {date.today().isoformat()} 生成。动工任何模块前必核对本文件;源有更新就重跑脚本。",
        "",
        f"## 一、权威基线({auth.name}/,最新完整需求)",
        "",
    ]
    if best_outline:
        o_ver, _, o_mdate, o_base = best_outline
        out += [
            "| 类型 | 版本 | 版本日期 | 文件 |",
            "|---|---|---|---|",
            f"| 设计大纲 | V{o_ver} | {o_date or o_mdate} | `{o_base}` |",
        ]
    if best_full:
        full_ver, _, full_mdate, full_base = best_full
        if not best_outline:
            out += [
                "| 类型 | 版本 | 版本日期 | 文件 |",
                "|---|---|---|---|",
            ]
        out.append(f"| 全模块说明书 | V{full_ver} | {full_date or full_mdate} | `{full_base}` |")
        if full_md and full_md.is_file():
            for line in full_md.read_text(encoding="utf-8").splitlines():
                if "模块范围" in line:
                    m = re.match(r".*模块范围[^|]*\| *", line)
                    text = line[m.end():] if m else line
                    text = text.replace("|", "").replace("*", "")
                    items = []
                    for part in text.split("、"):
                        part = re.sub(r"（.*?）", "", part).strip()
                        if CODE_RE.match(part):
                            items.append(part)
                    if items:
                        out += ["", "全模块说明书内各模块版本(权威):", ""]
                        out += [f"- {i}" for i in items]
                    break
    out += ["", "### 原型包(仅布局/交互参考,未与后台互通)", "", "| 原型包 | 日期 | 页面数 |", "|---|---|---|"]
    for name, md, pages in proto_done:
        out.append(f"| `{name}` | {md} | {pages} |")

    if archive:
        out += [
            "",
            f"## 二、历史资料库({archive.name}/,各模块历史最新版)",
            "",
            "> 已被权威基线取代,仅作历史追溯。文本缓存在 `提取缓存/历史/`。",
            "",
            "| 模块 | 版本 | 修改日期 | 文件名 | 状态 |",
            "|---|---|---|---|---|",
        ]
        for code, ver, mt, md, base in latest_per_module():
            same = sum(1 for m in modules if m[0] == code and m[1] == ver)
            flag = "✅"
            if same > 1:
                confirmed = any(l.startswith(f"{code}={base}|") for l in confirm_lines)
                flag = "✅ 已人工确认" if confirmed else f"⚠️ 同版本 {same} 个文件,需人工确认"
            out.append(f"| {code} | V{ver} | {md} | `{base}` | {flag} |")
        out += ["", "### 历史大纲", "", "| 版本 | 修改日期 | 文件名 |", "|---|---|---|"]
        for ver, mt, md, base in sorted(h_outline, key=lambda e: (*ver_pair(e[0]), e[1]), reverse=True):
            out.append(f"| V{ver} | {md} | `{base}` |")
        out += ["", "### 配套资料 / 原始需求 / 评审记录", "", "| 类型 | 模块 | 修改日期 | 文件名 |", "|---|---|---|---|"]
        for code, mt, md, base in sorted(companion, key=lambda e: e[0]):
            out.append(f"| 配套 | {code} | {md} | `{base}` |")
        for mt, md, base in sorted(req, key=lambda e: e[0], reverse=True):
            out.append(f"| 原始需求 | — | {md} | `{base}` |")
        for mt, md, base in sorted(audit, key=lambda e: e[0], reverse=True):
            out.append(f"| 评审 | — | {md} | `{base}` |")

    if unclassified or a_other:
        out += ["", "### 未归类(需人工判断)", "", "| 来源 | 修改日期 | 文件名 |", "|---|---|---|"]
        for mt, md, base in sorted(unclassified, key=lambda e: e[0], reverse=True):
            out.append(f"| 历史库 | {md} | `{base}` |")
        for mt, md, base in sorted(a_other, key=lambda e: e[0], reverse=True):
            out.append(f"| {auth.name} | {md} | `{base}` |")

    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"基线已生成: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
