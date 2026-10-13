#!/usr/bin/env python3
"""原型页面自动化测试(纯 Python 标准库,跨平台,Python ≥3.8)。

用法:
  scripts/test_prototype.py <原型目录> [--ia IA清单.md] [--states 状态枚举.txt] [--prd PRD.md]

五项检查(对应 references/prototype-depth.md 的闸门):
  ① 页面完整性:IA/nav 清单引用的每个页面文件都存在,缺页列出
  ② 链接有效性:内部链接/锚点可解析(文件存在、#id 在目标页有对应锚点)
  ③ 占位残留:占位卡/lorem/TODO/待补 等未完成标记
  ④ 状态覆盖:--states 给的基线状态枚举,每个状态至少在某个页面出现(抽查)
  ⑤ manifest 三层声明:页面内嵌 <script type="application/json" id="page-manifest">
     声明本页字段/状态/操作,与页面 data-field/data-state/data-op 标记双向核对;
     给 --prd 时再与 PRD 字段字典(名称/必填/类型)和状态枚举交叉核对

页面清单来源(取并集):
  a) --ia 指定的 IA/页面清单文件(markdown 或任何含 *.html 引用的文本,提取 `code`
     片段与列表项里的页面名/路径;JS 数据文件同样按文本提取 .html 引用)
  b) 各页面内部链接(导航即事实清单:被链接的 .html 都必须存在)

页面声明约定(⑤ 的扫描对象):
  data-field="字段key"    标在渲染该字段的表头/单元格/表单项上
  data-state="状态enum"   标在状态徽章上,元素文本 = manifest 声明的中文名
  data-op="操作id"        标在按钮上;元素须带 onclick/href/data-feedback 之一(防死按钮)
  data-perm="权限点"      manifest 里声明了 permission 的字段/操作,页面须有对应标记
  data-confirm="true"     manifest 里 confirm:true 的危险操作,元素必须携带
  四态(正常/空/错/加载)与权限 denied 态必须以静态 HTML 存在于页面(hidden 切换),
  不得只写在 JS 字符串里,否则静态扫描不可见。

退出码:0=全部通过;1=存在失败项;2=用法错误。
"""
import argparse
import json
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
MANIFEST_SCRIPT_ID = "page-manifest"  # 页面内嵌声明:<script type="application/json" id="page-manifest">


class PageScan(HTMLParser):
    """收集一页里的链接、锚点(id/name)、可见文本(去标签,记行号)、
    内嵌 manifest(page-manifest 脚本块原文)与 data-* 声明标记。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []        # (行号, url)
        self.anchors = set()
        self.text = []         # (行号, 文本)
        self._skip = 0         # script/style 深度
        self.manifest = None        # page-manifest JSON 原文(无则 None)
        self.manifest_dup = False   # 同页出现多个 page-manifest
        self._manifest_buf = None   # 正在收集的 manifest 片段
        self.data_fields = []  # (行号, data-field 值)
        self.data_states = []  # (行号, data-state 值)
        self.data_ops = []     # (行号, data-op 值, {onclick/href/confirm/feedback})
        self.data_perms = set()  # data-perm 值集合

    def handle_starttag(self, tag, attrs):
        ad = dict(attrs)
        if tag in ("script", "style"):
            self._skip += 1
            if tag == "script" and ad.get("id") == MANIFEST_SCRIPT_ID:
                if self.manifest is not None or self._manifest_buf is not None:
                    self.manifest_dup = True
                self._manifest_buf = []
        for name, value in attrs:
            if name == "data-field" and value:
                self.data_fields.append((self.getpos()[0], value.strip()))
            elif name == "data-state" and value:
                self.data_states.append((self.getpos()[0], value.strip()))
            elif name == "data-op" and value:
                self.data_ops.append((self.getpos()[0], value.strip(), {
                    "onclick": "onclick" in ad,
                    "href": bool(ad.get("href")),
                    "confirm": "data-confirm" in ad,
                    "feedback": "data-feedback" in ad,
                }))
            elif name == "data-perm" and value:
                self.data_perms.add(value.strip())
            if value is None:
                continue
            if name in ("href", "src"):
                self.links.append((self.getpos()[0], value.strip()))
            elif name in ("id", "name"):
                self.anchors.add(value)

    def handle_endtag(self, tag):
        if tag == "script" and self._manifest_buf is not None:
            if self.manifest is None:
                self.manifest = "".join(self._manifest_buf)
            self._manifest_buf = None
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._manifest_buf is not None:
            self._manifest_buf.append(data)
        elif not self._skip and data.strip():
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


def parse_prd_field_dict(path):
    """解析 PRD markdown 的字段字典:表头同时含「字段名」「必填」的表格。

    返回 (fields, enum_values, text):
      fields      = {字段名: [条目, ...]};条目 = {"label": 中文名, "type": 类型, "required": 必填原文}
                    同一字段名可出现在多张实体表(如各单据的 status),全部保留,
                    核对时「任一实体条目与页面声明一致」即通过
      enum_values = 所有「类型」为 enum 的字段、取值范围单元格里 {...} 内的枚举 token 并集
      text        = PRD 全文(供状态中文名、操作出处编号做存在性核对)
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    fields = {}
    enum_values = set()
    lines = text.splitlines()

    def col_idx(header, *names):
        for n in names:
            for idx, h in enumerate(header):
                if n in h:
                    return idx
        return None

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("|") and "字段名" in line and "必填" in line:
            header = [c.strip() for c in line.strip("|").split("|")]
            ci_key = col_idx(header, "字段名")
            ci_label = col_idx(header, "中文名")
            ci_type = col_idx(header, "类型")
            ci_req = col_idx(header, "必填")
            ci_range = col_idx(header, "取值范围", "边界")
            j = i + 1
            if j < len(lines) and set(lines[j].replace("|", "").strip()) <= set("-: "):
                j += 1  # 跳过表头分隔行
            while j < len(lines) and lines[j].strip().startswith("|"):
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]

                def cell(ci):
                    return cells[ci] if ci is not None and ci < len(cells) else ""

                key = cell(ci_key)
                if key:
                    fields.setdefault(key, []).append({
                        "label": cell(ci_label),
                        "type": cell(ci_type),
                        "required": cell(ci_req),
                    })
                    if cell(ci_type) == "enum":
                        m = re.search(r"\{([^}]*)\}", cell(ci_range) or " ".join(cells))
                        if m:
                            for tok in re.split(r"[,，、/\s]+", m.group(1)):
                                if tok.strip():
                                    enum_values.add(tok.strip())
                j += 1
            i = j
        else:
            i += 1
    return fields, enum_values, text


def norm_required(prd_req):
    """PRD 必填列 → 规范值:是→True,否→False,条件*→"conditional";无法识别→None(不核对)。"""
    r = (prd_req or "").strip()
    if r == "是":
        return True
    if r == "否":
        return False
    if r.startswith("条件"):
        return "conditional"
    return None


def check_manifest(mf, scan, prd_fields, prd_enums, prd_text):
    """单页 manifest 三层声明检查,返回 [(行号, 问题描述), ...]。prd_* 为空时不做 PRD 交叉核对。"""
    problems = []
    page_text = " ".join(t for _, t in scan.text)
    if not isinstance(mf, dict):
        return [(0, "manifest 顶层必须是 JSON 对象")]
    for k in ("page_id", "title"):
        if not mf.get(k):
            problems.append((0, f"manifest 缺顶层字段 {k}"))

    fields = [f for f in (mf.get("fields") or []) if isinstance(f, dict)]
    states = [s for s in (mf.get("states") or []) if isinstance(s, dict)]
    ops = [o for o in (mf.get("ops") or []) if isinstance(o, dict)]
    transitions = [t for t in (mf.get("transitions") or []) if isinstance(t, dict)]
    for f in fields:
        if not f.get("key") or not f.get("label"):
            problems.append((0, f"fields 条目缺 key/label: {str(f)[:60]}"))
    for s in states:
        if not s.get("enum") or not s.get("label"):
            problems.append((0, f"states 条目缺 enum/label: {str(s)[:60]}"))
    for o in ops:
        if not o.get("id") or not o.get("label"):
            problems.append((0, f"ops 条目缺 id/label: {str(o)[:60]}"))

    f_keys = {f["key"] for f in fields if f.get("key")}
    s_enums = {s["enum"] for s in states if s.get("enum")}
    o_ids = {o["id"] for o in ops if o.get("id")}
    f_rendered = {v for _, v in scan.data_fields}
    s_rendered = {v for _, v in scan.data_states}
    o_rendered = {v for _, v, _ in scan.data_ops}

    # ---- 字段层:声明 ↔ 渲染 双向核对 ----
    for k in sorted(f_keys - f_rendered):
        problems.append((0, f'[字段未渲染] manifest 声明字段 "{k}",页面无 data-field="{k}"'))
    for lineno, v in scan.data_fields:
        if v not in f_keys:
            problems.append((lineno, f'[字段未声明] 页面 data-field="{v}" 未在 manifest fields 声明'))
    for f in fields:
        label = f.get("label")
        if label and f.get("key") in f_rendered and label not in page_text:
            problems.append((0, f'[字段标签未出现] 字段 "{f.get("key")}" 的中文名「{label}」未在页面文本出现'))

    # ---- 状态层:声明 ↔ 呈现 双向核对 + 流转入口 ----
    for e in sorted(s_enums - s_rendered):
        problems.append((0, f'[状态未呈现] manifest 声明状态 "{e}",页面无 data-state="{e}"'))
    for lineno, v in scan.data_states:
        if v not in s_enums:
            problems.append((lineno, f'[状态未声明] 页面 data-state="{v}" 未在 manifest states 声明(不得发明状态名)'))
    for s in states:
        label = s.get("label")
        if label and s.get("enum") in s_rendered and label not in page_text:
            problems.append((0, f'[状态标签未出现] 状态 "{s.get("enum")}" 的中文名「{label}」未在页面文本出现'))
    for t in transitions:
        fr, to, op = t.get("from"), t.get("to"), t.get("op")
        if fr not in s_enums or to not in s_enums:
            problems.append((0, f'[流转声明无效] 流转 "{fr}"→"{to}" 不在 manifest states 内'))
        if op not in o_ids:
            problems.append((0, f'[流转无入口] 流转 "{fr}"→"{to}" 引用的操作 "{op}" 不在 manifest ops 内'))

    # ---- 操作层:声明 ↔ 入口 双向核对 + 反馈回路 + 危险操作二次确认 + 权限落位 ----
    for k in sorted(o_ids - o_rendered):
        problems.append((0, f'[操作无入口] manifest 声明操作 "{k}",页面无 data-op="{k}"(PRD 操作须在页面有入口)'))
    for lineno, v, _ in scan.data_ops:
        if v not in o_ids:
            problems.append((lineno, f'[操作未声明] 页面 data-op="{v}" 未在 manifest ops 声明'))
    for lineno, v, meta in scan.data_ops:
        if not (meta["onclick"] or meta["href"] or meta["feedback"]):
            problems.append((lineno, f'[死按钮] data-op="{v}" 无 onclick/href/data-feedback,点击无反馈'))
    confirm_ops = {o["id"] for o in ops if o.get("confirm") is True}
    for lineno, v, meta in scan.data_ops:
        if v in confirm_ops and not meta["confirm"]:
            problems.append((lineno, f'[危险操作无二次确认] 操作 "{v}" manifest 标了 confirm:true,元素缺 data-confirm'))
        if meta["confirm"] and v not in confirm_ops:
            problems.append((lineno, f'[确认标记未声明] 元素带 data-confirm,但 manifest 操作 "{v}" 未标 confirm:true'))
    perms_declared = {f["permission"] for f in fields if f.get("permission")}
    perms_declared |= {o["permission"] for o in ops if o.get("permission")}
    for pm in sorted(perms_declared):
        if pm not in scan.data_perms:
            problems.append((0, f'[权限点未落位] manifest 声明 permission "{pm}",页面无 data-perm="{pm}"'))

    # ---- PRD 交叉核对(给 --prd 时启用) ----
    if prd_fields or prd_enums or prd_text:
        for f in fields:
            key = f.get("key")
            if not key:
                continue
            if f.get("derived") is True:
                if not f.get("note"):
                    problems.append((0, f'[derived 缺说明] 字段 "{key}" 不在 PRD 字典,须写 note 说明来源(不编造)'))
                continue
            hits = prd_fields.get(key)
            if hits is None:
                problems.append((0, f'[PRD 无此字段] 字段 "{key}"({f.get("label")})不在 PRD 字段字典(页面不得出现字典外字段);确为派生展示列请标 "derived": true 并写 note'))
                continue

            def entry_ok(e):
                if e["label"] and f.get("label") and f["label"] != e["label"]:
                    return False
                if e["type"] and f.get("type") and f["type"] != e["type"]:
                    return False
                req = norm_required(e["required"])
                if req is not None and "required" in f and f["required"] != req:
                    return False
                return True

            if not any(entry_ok(e) for e in hits):
                variants = ";".join(f'「{e["label"]}/{e["type"]}/{e["required"]}」' for e in hits)
                problems.append((0, f'[字段与 PRD 不符] "{key}":页面(「{f.get("label")}」/{f.get("type")}/{f.get("required")!r})'
                                   f'与 PRD 各实体定义均不一致: {variants}'))
        for s in states:
            enum, label = s.get("enum"), s.get("label")
            if enum and prd_enums and enum not in prd_enums:
                problems.append((0, f'[状态枚举不在 PRD] "{enum}"({label})不在 PRD 任何 enum 字段的取值集内'))
            if label and prd_text and label not in prd_text:
                problems.append((0, f'[状态名不在 PRD] 状态中文名「{label}」未在 PRD 出现'))
        for o in ops:
            if o.get("kind") == "ui":
                continue  # 纯 UI 演示控件(重试/态切换),不要求 PRD 出处
            ref = o.get("prd_ref")
            if not ref:
                problems.append((0, f'[操作无出处] 操作 "{o.get("id")}"({o.get("label")})缺 prd_ref(每个操作须能在 PRD 找到出处)'))
                continue
            for tok in re.split(r"[,，、/\s|]+", str(ref)):
                if tok and prd_text and tok not in prd_text:
                    problems.append((0, f'[操作出处不在 PRD] 操作 "{o.get("id")}" 的 prd_ref "{tok}" 未在 PRD 出现'))
    return problems


def main():
    parser = argparse.ArgumentParser(
        description="原型页面自动化测试:页面完整性/链接有效性/占位残留/状态覆盖/manifest 三层声明",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码:0=通过 1=有失败项 2=用法错误",
    )
    parser.add_argument("dir", help="原型目录(递归扫描 *.html)")
    parser.add_argument("--ia", help="IA/页面清单文件(markdown 或含 .html 引用的文本/JS 数据文件)")
    parser.add_argument("--states", help="基线状态枚举文件(一行一个状态名)")
    parser.add_argument("--prd", help="PRD markdown(解析字段字典表,核对 manifest 字段的名称/必填/类型与状态枚举、操作出处)")
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

    # ⑤ manifest 三层声明检查(字段/状态/操作;给 --prd 时叠加 PRD 交叉核对)
    print("\n===== ⑤ manifest 声明检查(字段/状态/操作) =====")
    prd_fields, prd_enums, prd_text = {}, set(), ""
    if args.prd:
        prd_path = Path(args.prd)
        if not prd_path.is_file():
            print(f"PRD 文件不存在: {prd_path}", file=sys.stderr)
            return 2
        prd_fields, prd_enums, prd_text = parse_prd_field_dict(prd_path)
        print(f"PRD 字段字典:{len(prd_fields)} 个字段、{len(prd_enums)} 个枚举值 ← {prd_path.name}")
    manifest_problems = []  # (页面, 行号, 问题)
    n_manifest = 0
    for p, scan in scans.items():
        if scan.manifest is None:
            continue
        n_manifest += 1
        if scan.manifest_dup:
            manifest_problems.append((p, 0, "存在多个 page-manifest,每页只允许一个"))
            continue
        try:
            mf = json.loads(scan.manifest)
        except json.JSONDecodeError as e:
            manifest_problems.append((p, 0, f"manifest JSON 解析失败: {e}"))
            continue
        for lineno, msg in check_manifest(mf, scan, prd_fields, prd_enums, prd_text):
            manifest_problems.append((p, lineno, msg))
    if n_manifest == 0:
        print('跳过:未发现 page-manifest(页面内嵌 <script type="application/json" id="page-manifest"> 后启用)')
    else:
        n_without = len(scans) - n_manifest
        print(f"检出 manifest 页面 {n_manifest} 个;无 manifest 页面 {n_without} 个(业务页应内嵌 manifest,无声明页面由人工逐页过)")
        for p, scan in scans.items():
            if scan.manifest is None:
                print(f"  [无 manifest] {rel_name(p)}")
        if manifest_problems:
            failures += len(manifest_problems)
            print(f"声明问题 {len(manifest_problems)} 处:")
            for p, lineno, msg in manifest_problems:
                where = f"{rel_name(p)}:{lineno}" if lineno else rel_name(p)
                print(f"  {where} {msg}")
        else:
            print("通过:全部 manifest 页面的字段/状态/操作声明与页面标记一致"
                  + (",且与 PRD 字段字典/枚举核对一致" if args.prd else ""))

    print()
    if failures:
        print(f"结果:共 {failures} 个失败项,修复后再过 G4 闸门")
        return 1
    print("结果:原型测试通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
