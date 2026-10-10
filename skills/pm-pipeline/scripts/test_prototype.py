#!/usr/bin/env python3
"""原型页面自动化测试(纯 Python 标准库,跨平台,Python ≥3.8)。

用法:
  scripts/test_prototype.py <原型目录> [--ia IA清单.md] [--states 状态枚举.txt]

四项检查(对应 references/prototype-depth.md 的闸门):
  ① 页面完整性:IA/nav 清单引用的每个页面文件都存在,缺页列出
  ② 链接有效性:内部链接/锚点可解析(文件存在、#id 在目标页有对应锚点)
  ③ 占位残留:占位卡/lorem/TODO/待补 等未完成标记
  ④ 状态覆盖:--states 给的基线状态枚举,每个状态至少在某个页面出现(抽查)

页面清单来源(取并集):
  a) --ia 指定的 IA/页面清单文件(markdown,提取 `code`、列表项里的页面名/路径)
  b) 各页面内部链接(导航即事实清单:被链接的 .html 都必须存在)

退出码:0=全部通过;1=存在失败项;2=用法错误。
"""
import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

PLACEHOLDER_PATTERNS = [
    r"lorem", r"ipsum", r"\bTODO\b", r"\bFIXME\b", r"\bTBD\b",
    r"占位", r"待补", r"待定", r"待完善", r"未完待续", r"敬请期待",
    r"coming\s+soon", r"x{3,}",  # xxx 连用视为占位文本
]
SKIP_SCHEMES = ("http://", "https://", "mailto:", "tel:", "javascript:", "data:")


class PageScan(HTMLParser):
    """收集一页里的链接、锚点(id/name)与可见文本(去标签,记行号)。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []   # (行号, url)
        self.anchors = set()
        self.text = []    # (行号, 文本)
        self._skip = 0    # script/style 深度

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        for name, value in attrs:
            if value is None:
                continue
            if name in ("href", "src"):
                self.links.append((self.getpos()[0], value.strip()))
            elif name in ("id", "name"):
                self.anchors.add(value)

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.text.append((self.getpos()[0], data))


def scan_page(path):
    scan = PageScan()
    scan.feed(path.read_text(encoding="utf-8", errors="replace"))
    return scan


def parse_ia_file(path):
    """从 IA/页面清单 markdown 提取页面引用:`code` 片段与列表项文本里的 *.html。"""
    refs = set()
    text = path.read_text(encoding="utf-8", errors="replace")
    for m in re.finditer(r"`([^`]+)`", text):
        token = m.group(1).strip()
        if token.endswith(".html"):
            refs.add(token)
    for m in re.finditer(r"[\w./\-\u4e00-\u9fff]+\.html", text):
        refs.add(m.group(0))
    return refs


def parse_states_file(path):
    """基线状态枚举:一行一个;忽略空行、# 注释、markdown 列表符号。"""
    states = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip().lstrip("-*0123456789.、)） ").strip().strip("`")
        if line and not line.startswith("#") and not line.startswith("|"):
            states.append(line)
    return states


def main():
    parser = argparse.ArgumentParser(
        description="原型页面自动化测试:页面完整性/链接有效性/占位残留/状态覆盖",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码:0=通过 1=有失败项 2=用法错误",
    )
    parser.add_argument("dir", help="原型目录(递归扫描 *.html)")
    parser.add_argument("--ia", help="IA/页面清单 markdown(提取其中的 .html 引用作为应有页面)")
    parser.add_argument("--states", help="基线状态枚举文件(一行一个状态名)")
    args = parser.parse_args()

    root = Path(args.dir)
    if not root.is_dir():
        print(f"原型目录不存在: {root}", file=sys.stderr)
        return 2
    pages = sorted(root.rglob("*.html"))
    if not pages:
        print(f"目录下无 .html 页面: {root}", file=sys.stderr)
        return 2
    scans = {p.resolve(): scan_page(p) for p in pages}
    display = {p.resolve(): str(p.relative_to(root)) for p in pages}
    print(f"扫描页面 {len(pages)} 个: {root}\n")

    def rel_name(p):
        return display.get(p, p.name)

    failures = 0

    # ① 页面完整性:IA 清单 + 导航引用 vs 实际文件
    print("===== ① 页面完整性 =====")
    expected = {}  # 引用路径 -> 解析基准目录(nav 引用相对引用页,IA 引用相对原型根)
    if args.ia:
        ia_path = Path(args.ia)
        if ia_path.is_file():
            for ref in parse_ia_file(ia_path):
                expected.setdefault(ref, root)
        else:
            print(f"(IA 文件不存在: {ia_path},仅按导航引用核对)")
    for p, scan in scans.items():
        for _, url in scan.links:
            if ".html" in url:
                clean = url.split("#")[0].split("?")[0]
                if clean and not clean.startswith(SKIP_SCHEMES) and not Path(clean).is_absolute():
                    expected.setdefault(clean, p.parent)

    def page_exists(ref, base):
        if (base / ref).resolve().is_file() or (root / ref).resolve().is_file():
            return True
        # IA 清单常只写页面名:按文件名在已有页面里兜底匹配
        return Path(ref).name in {p.name for p in pages}

    missing = sorted(ref for ref, base in expected.items() if not page_exists(ref, base))
    if missing:
        failures += len(missing)
        print(f"缺页 {len(missing)} 个(IA/nav 引用但文件不存在):")
        for m in missing:
            print(f"  [缺页] {m}")
    else:
        print(f"通过:清单/导航引用的 {len(expected)} 个页面全部存在")

    # ② 链接有效性
    print("\n===== ② 链接有效性 =====")
    broken = []
    for p, scan in scans.items():
        for lineno, url in scan.links:
            if not url or url.startswith(SKIP_SCHEMES):
                continue
            if url.startswith("#"):
                if url[1:] and url[1:] not in scan.anchors:
                    broken.append((p, lineno, url, "页内锚点不存在"))
                continue
            clean, _, frag = url.partition("#")
            clean = clean.split("?")[0]
            if not clean:
                continue
            target = (p.parent / clean).resolve()
            if not target.is_file():
                broken.append((p, lineno, url, "目标文件不存在"))
            elif frag and target.suffix == ".html":
                target_scan = scans[target] if target in scans else scan_page(target)
                if frag not in target_scan.anchors:
                    broken.append((p, lineno, url, "目标页锚点不存在"))
    if broken:
        failures += len(broken)
        print(f"死链 {len(broken)} 处:")
        for p, lineno, url, why in broken:
            print(f"  [死链] {rel_name(p)}:{lineno} {url}({why})")
    else:
        print("通过:全部内部链接/锚点可解析")

    # ③ 占位残留
    print("\n===== ③ 占位残留检测 =====")
    pattern = re.compile("|".join(PLACEHOLDER_PATTERNS), re.IGNORECASE)
    leftovers = []
    for p, scan in scans.items():
        for lineno, text in scan.text:
            for m in pattern.finditer(text):
                leftovers.append((p, lineno, m.group(0)))
    if leftovers:
        failures += len(leftovers)
        print(f"占位残留 {len(leftovers)} 处:")
        for p, lineno, word in leftovers:
            print(f"  [占位] {rel_name(p)}:{lineno} 「{word}」")
    else:
        print("通过:未发现占位残留")

    # ④ 状态覆盖抽查
    print("\n===== ④ 状态覆盖抽查 =====")
    if args.states:
        states_path = Path(args.states)
        if not states_path.is_file():
            print(f"状态枚举文件不存在: {states_path}", file=sys.stderr)
            return 2
        states = parse_states_file(states_path)
        corpus = {}
        for p, scan in scans.items():
            corpus[p] = " ".join(t for _, t in scan.text)
        uncovered = []
        for s in states:
            hit = [p.name for p, text in corpus.items() if s in text]
            if not hit:
                uncovered.append(s)
        print(f"基线状态 {len(states)} 个,覆盖 {len(states) - len(uncovered)} 个")
        if uncovered:
            failures += len(uncovered)
            print(f"未覆盖 {len(uncovered)} 个(未在任何页面出现):")
            for s in uncovered:
                print(f"  [状态缺口] {s}")
        else:
            print("通过:全部基线状态在页面中出现")
    else:
        print("跳过:未提供 --states(给基线状态枚举文件后启用)")

    print()
    if failures:
        print(f"结果:共 {failures} 个失败项,修复后再过 G4 闸门")
        return 1
    print("结果:原型测试通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
