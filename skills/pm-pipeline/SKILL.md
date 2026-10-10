---
name: pm-pipeline
description: |
  多模块需求工程流水线:把散落的客户需求 docx 变成可续跑、可审计、可交付的结构化工程。
  内置五阶段循环(S1需求→G1确认→S2 PRD→G2确认→S3流程图→G3确认→S4原型→G4确认→S5交付)、
  开工记忆仪式(AGENTS→MEMORY→state)、闸门自检(脚本级+Jev 语义级)、选项式确认、源资料基线、
  需求完整性审计协议、原型页面自动化测试(完整性/死链/占位残留/状态覆盖)、Jev 类型化决策集成
  (置信度阈值分流:高置信自动、低置信转人工)、自我进化机制,以及七个跨平台 Python 脚本。
  用户说「搭需求工程体系」「多模块 PRD 管理」「需求流水线」「模块状态追踪」
  「把一堆需求文档工程化」时使用。
  适用于 10+ 模块、多轮客户确认、需要跨会话/跨模型续跑的中大型需求项目。
  不含任何具体行业内容;不替代 PRD/流程图/原型撰写 skill,而是把它们串成流水线。
version: "1.1"
updated: "2026-10-10"
---

# pm-pipeline · 多模块需求工程流水线

一堆客户 docx 进去,一个任何模型都能接手续跑的结构化工程出来。

核心不是「写文档」,而是**让工程状态不丢**:每个模块走到哪、客户确认过什么、源资料哪版是权威,全部落在文件里——换会话、换模型、换人,都能从文件现场重建上下文。

## 能力边界

| 能力 | 输入 | 产出 |
|------|------|------|
| **工程初始化** | 散落的需求 docx/zip 目录 | 四层工程骨架(体系/记忆/需求输入/模块) |
| **五阶段循环** | 单模块需求 | S1→S5 状态机推进,每阶段带确认闸门 |
| **基线机制** | 权威源+历史源目录 | `源资料基线.md` + 提取缓存(自动选版,同版本标 ⚠️) |
| **闸门自检** | 模块 PRD/流程图 | 脚本自检 + 人工核对清单;配 Jev 后追加语义级闸门 |
| **原型测试** | 原型目录 | 页面完整性/死链/占位残留/状态覆盖四项自动化检查 |
| **Jev 决策集成** | 决策场景+候选+上下文 | 类型化决策+置信度;高置信自动执行,低置信/无 key 转人工留痕 |
| **交付导出** | 定稿 Markdown | docx(pandoc,带目录) |
| **审计协议** | 需求基线 | 五维度审计(状态孤岛/功能孤岛/事件断链/覆盖缺失/逻辑遗漏) |
| **自我进化** | 复盘结论 | 落地到闸门/硬性规则/脚本的进化日志 |

**不做**:编造业务数据(缺失一律 `[待补:需业务方提供]`);代替 PRD/流程图/原型撰写 skill(只做串联与编排,撰写交给专业 skill);代替客户做确认。

## 启动必读

1. 本文件 `SKILL.md`
2. [references/workflow.md](references/workflow.md) —— S1–S5 状态机 + G1–G4 闸门定义
3. [references/checklist.md](references/checklist.md) —— 各闸门自检条目

按需再读:

- [references/conventions.md](references/conventions.md) —— 命名/版本/目录规则
- [references/audit-protocol.md](references/audit-protocol.md) —— 需求完整性审计协议(五维度)
- [references/evolution.md](references/evolution.md) —— 自我进化机制
- [references/jev-integration.md](references/jev-integration.md) —— Jev 决策集成(决策点清单/阈值模式/边界)
- [references/prototype-depth.md](references/prototype-depth.md) —— 单页深度规范(五层结构+状态四态)
- [templates/](templates/) —— AGENTS.md / MEMORY.md / state.md / 决策日志 / G1确认单 骨架

## 工程目录结构(初始化时建立)

```
<工程根>/
├── AGENTS.md            # 工程宪法:开工仪式 + 硬性规则 + skill 路由表(模板见 templates/)
├── 00-体系/             # WORKFLOW / CHECKLIST / CONVENTIONS / AUDIT-PROTOCOL / EVOLUTION / JEV-INTEGRATION / PROTOTYPE-DEPTH
├── 01-记忆/             # MEMORY.md(索引)/ 决策日志 / 术语表 / 客户画像 / 源资料基线
├── 02-需求输入/         # 各模块需求摘要 + 提取缓存(权威文档拆分) + 原型参考
├── 10-模块/             # 每模块一目录:state.md + prd/ + flows/ + prototype/ + review/
├── 11-全局原型/         # (可选,全局模式)IA + 设计系统 + 导航壳
├── 20-交付/             # 导出的 docx
├── 30-复盘/             # 模块定稿复盘
└── scripts/             # 本 skill scripts/ 的七个 Python 脚本拷入
```

## 开工仪式(每次会话固定顺序)

1. 读 `AGENTS.md`
2. 读 `01-记忆/MEMORY.md`(长期记忆索引)
3. 读当前模块 `10-模块/<模块编号>-*/state.md`(工作记忆)
4. 然后才动手

会话结束前:更新当前模块 `state.md`;有确认或取舍 → 更新 `01-记忆/决策日志.md`。

## 五阶段循环(速览)

```
S1 需求采集 ──G1──> S2 PRD ──G2──> S3 流程图 ──G3──> S4 原型 ──G4──> S5 定稿交付+复盘
```

- 每个 G 是**确认点**:产物先过 CHECKLIST 闸门,再选项式发给确认方,结论记入 state.md + 决策日志
- 确认方有意见 → 回对应阶段,版本 +0.1,记录进 `review/`
- 多模块大项目推荐**全局模式**:G0.5 全局原型骨架先行确认,各模块只跑到 G3,全部通过后统一 S4/G4(详见 workflow.md)

## 硬性规则(违反即返工)

1. **不编造数据**:缺失写 `[待补:需业务方提供]`
2. **未过闸门不出示客户**
3. **记忆必更新**:每轮结束更新 state.md;确认结果进决策日志
4. **Markdown 是唯一事实源**:docx 只是导出物
5. **三方一致性**:PRD ↔ 流程图 ↔ 原型改动三处同步
6. **源资料只读**:原始文件只引用不修改,衍生物进提取缓存
7. 不写「尽快/适当/若干」等模糊词
8. **确认事项一律选项式**:给可选项+推荐项,文档只做留痕不做确认入口
9. **Jev 只做判断分流**:不做业务事实写入、不替代确认点(确认点永远是人);低置信/无 key 一律转人工并留痕

## 脚本(全部 Python 3,跨平台)

| 脚本 | 用法 | 作用 |
|---|---|---|
| `new_module.py` | `new_module.py M02 客服中心` | 建模块骨架(state.md + 对照表) |
| `check_all.py` | `check_all.py M02-客服中心` | 串联 check_prd/check_mermaid + 人工核对提醒;自动探测多工具 skills 目录 |
| `check_semantic.py` | `check_semantic.py M02-客服中心 [--threshold 0.7]` | Jev 语义闸门:指标可量化/状态机有出口/字段字典完整/三方对照真一致;无 key 降级为人工核对清单 |
| `test_prototype.py` | `test_prototype.py <原型目录> [--ia IA.md] [--states 状态枚举.txt]` | 原型四项检查:页面完整性/链接有效性/占位残留/状态覆盖 |
| `jev_decide.py` | `jev_decide.py request.json [--threshold 0.85]` | Jev 调用适配器:类型化决策+置信度阈值分流(auto/human),无 key 优雅降级 |
| `export_docx.py` | `export_docx.py M02-客服中心 [版本] [--prefix 前缀]` | pandoc 导出 docx 到 20-交付/ |
| `refresh_baseline.py` | `refresh_baseline.py [--auth 目录] [--archive 目录]` | 扫描源资料,自动选版,重建基线+提取缓存 |

Jev 配置(可选,不配则相关能力自动降级为人工流程):`JEV_API_KEY`(回退 `TYPESAFE_API_KEY`)、`JEV_BASE_URL`(默认 `https://api.typesafe.ai/v1`)、`JEV_MODEL`(默认 `jev-latest`)、`JEV_THRESHOLD`(默认 0.85)。备用引擎:`JEV_BACKEND=kev` + `KEV_BASE_URL`(默认 `http://localhost:8009`)切到自托管 Kev(同一 System One 协议;阈值须用自有语料重新标定)。详见 `references/jev-integration.md`。

依赖:Python ≥3.8;pandoc(导出/基线提取用,PATH 或常见安装位自动探测,Windows 有官方安装包)。

## 配套 skill(不捆绑,按需安装)

- PRD 撰写:laowang-prd(自带 check_prd.py 自检脚本)
- 流程图:laowang-diagram(自带 check_mermaid.py)
- HTML 原型:baoyu-design

`check_all.py` 会按 `$KIMI_CODE_HOME/skills → ~/.kimi-code/skills → ~/.agents/skills → ~/.claude/skills → ~/.codex/skills` 顺序探测这些自检脚本,找不到则跳过并提示。

## 多工具接入

见 [agents/](agents/):Codex(openai.yaml)/ Claude Code(claude.md)/ Cursor(cursor.md)/ 无 skill 加载器的通用模型(GENERIC.md,SKILL.md 全文可直接粘贴为系统提示)。
