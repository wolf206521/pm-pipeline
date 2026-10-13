# pm-pipeline · 多模块需求工程流水线

把散落的客户需求文档变成**可续跑、可审计、可交付**的结构化工程。

适用于:10+ 模块的中大型需求项目,需要多轮客户确认、跨会话/跨模型/跨工具接续推进。

> English summary: pm-pipeline is an agent skill that turns scattered client requirement docs into a structured, resumable, auditable requirements-engineering project. It provides a five-stage loop (collect → PRD → flow diagram → prototype → delivery) with client confirmation gates, a file-based memory system (AGENTS/MEMORY/state), a source-baseline mechanism, a requirement-completeness audit protocol, optional Jev (TypeSafe AI System One) integration for typed decisions with calibrated confidence thresholds (auto-act above threshold, escalate to human below), automated prototype testing (page completeness / link validity / placeholder residue / state coverage), and seven cross-platform Python scripts. Any model or agent tool can pick up the project mid-stream by reading the memory files. Contains no industry-specific content.

## 解决什么问题

- 需求散在几十份 docx 里,版本混乱,不知道哪版是权威 → **源资料基线机制**(自动选版,同版本标 ⚠️ 人工确认)
- 多模块并行推进,每个模块走到哪一步全靠脑子记 → **每模块 state.md + 五阶段状态机**
- 客户确认散落在聊天记录里,后来被推翻没处查 → **决策日志 + 选项式确认硬性规则**
- 换会话/换模型/换人要重新讲一遍背景 → **开工仪式:AGENTS.md → MEMORY.md → state.md,文件即上下文**
- PRD、流程图、原型各自为政互相对不上 → **三方一致性对照表闸门**
- 脚本自检查「形」查不了「义」(指标是否真可量化、状态机是否真有出口) → **Jev 语义闸门**(类型化判断+置信度阈值,低置信转人工;不配 key 自动降级为人工核对清单)
- 原型缺页、死链、占位残留靠人肉翻 → **原型自动化测试**(页面完整性/链接有效性/占位残留/状态覆盖四项)

## 安装

```bash
git clone https://github.com/wolf206521/pm-pipeline.git
cd pm-pipeline
python3 install.py            # 自动探测并安装到 ~/.kimi-code/skills、~/.claude/skills、~/.agents/skills、~/.codex/skills 中已存在的目录
python3 install.py --target ~/.claude/skills   # 或显式指定
```

也可手动:把 `skills/pm-pipeline/` 整个复制到你的 Agent 工具 skills 目录。

无 skill 加载器的模型(DeepSeek 网页版等):见 `skills/pm-pipeline/agents/GENERIC.md`,SKILL.md 全文可直接粘贴为系统提示。

## 快速开始

```bash
# 1. 建工程骨架(在你的项目目录)
mkdir -p 00-体系 01-记忆 02-需求输入/提取缓存 10-模块 20-交付 30-复盘 scripts
cp skills/pm-pipeline/templates/AGENTS.md .        # 替换 <项目名> 等占位符
cp skills/pm-pipeline/templates/MEMORY.md 01-记忆/
cp skills/pm-pipeline/templates/决策日志.md 01-记忆/
cp skills/pm-pipeline/references/*.md 00-体系/      # 改名为 WORKFLOW.md 等大写形式,见下
cp skills/pm-pipeline/scripts/*.py scripts/

# 2. 生成源资料基线(权威源目录默认 工程/客户需求,可 --auth 指定)
python3 scripts/refresh_baseline.py --auth /path/to/权威需求目录 --archive /path/to/历史资料目录

# 3. 建第一个模块并开工
python3 scripts/new_module.py M01 客户中心
python3 scripts/check_all.py M01-客户中心          # 交付前自检
python3 scripts/export_docx.py M01-客户中心 --prefix PROJ   # 定稿导出 docx
```

`references/` 文件名映射到工程 `00-体系/`:`workflow.md → WORKFLOW.md`、`checklist.md → CHECKLIST.md`、`conventions.md → CONVENTIONS.md`、`audit-protocol.md → AUDIT-PROTOCOL.md`、`evolution.md → EVOLUTION.md`、`jev-integration.md → JEV-INTEGRATION.md`、`prototype-depth.md → PROTOTYPE-DEPTH.md`。

## Jev 决策集成(可选)

Jev(TypeSafe AI 的 System One 模型)返回**类型化决策 + 校准置信度**,用于管线上的判断/分类/分流类决策点:闸门语义检查(PRD 是否达标)、审计发现初筛分类、质量工单路由、异常分流建议、确认单口径一致性初判。**置信度 ≥ 阈值自动执行,低于阈值转人工并留痕;客户确认点永远是人。**

```bash
export JEV_API_KEY=<在 TypeSafe dashboard 获取>   # 未设置时回退读 TYPESAFE_API_KEY
python3 scripts/check_semantic.py M01-客户中心     # G2 语义闸门
echo '{"scenario":"工单路由","type":"choice","question":"该意见应路由给哪个产物负责人?","candidates":{"prd":"字段或逻辑问题","flow":"流程问题","prototype":"页面问题"},"context":{"意见":"状态枚举和字段表对不上"}}' \
  | python3 scripts/jev_decide.py -                # 通用决策入口
```

不配 key 也不影响使用:所有 Jev 集成点自动降级为「转人工 + 人工核对清单」,不编造结果。详见 `skills/pm-pipeline/references/jev-integration.md`(含已核实的 API 事实与配置占位说明)。

**备用引擎 Kev**:Kev([github.com/jaredpalmer/kev](https://github.com/jaredpalmer/kev))是自托管的 System One 协议实现(同一 `POST /v1/systemone`,confidence 公式同源),无 API 配额。切换:

```bash
export JEV_BACKEND=kev
export KEV_BASE_URL=http://localhost:8009   # 先按 Kev 官方说明启动 kev.serve
```

⚠️ 红线:Jev 调好的阈值**不能直接搬到 Kev**——两者校准口径一致但分布不同(官方基准:5% 错误预算下可自动化比例 Jev 0.70 vs Kev 大模型 0.52–0.69),切换后须用自有语料留出评测重新标定;Kev 中文表现无官方数据,需实测。

## 上手准备

| 后端 | 要准备什么 |
|---|---|
| **Jev**(默认) | TypeSafe dashboard 申请 API key + 确认额度;`export JEV_API_KEY=...` 即可 |
| **Kev**(可选备用) | ① Python 3.12/3.13 + uv,**源码安装**(`pip install kev` 是同名 ORM 包,不是它)② 硬件:Apple Silicon 走 MLX 开箱即用;Intel Mac 无 MLX 不在官方支持列,0.8B 可 `--device cpu` 试跑;正式用建议 GPU 服务器(4B 建议 L40S 级)或官方 Modal 一键部署(闲置缩放到零)③ 无卡先试:[Hugging Face Space](https://huggingface.co/spaces/jaredpalmer/kev) 浏览器里跑 |
| 都不用 | 可以:不配任何后端,语义闸门自动降级为人工核对清单,其余能力不受影响 |

完整部署步骤(GPU 服务器 / Modal 云 / CPU 试用三形态)、连通验证与验收清单见 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 原型自动化测试

```bash
python3 scripts/test_prototype.py 10-模块/M01-客户中心/prototype \
  --ia 11-全局原型/IA.md --states 01-记忆/状态枚举.txt --prd 10-模块/M01-客户中心/prd/v0.3.md
```

五项检查:① 页面完整性(IA/导航清单 100% 覆盖,缺页不放行)② 链接有效性(内部链接/锚点可解析)③ 占位残留(lorem/TODO/「待补」等)④ 状态覆盖(基线状态枚举在页面中出现)⑤ manifest 声明检查(页面内嵌 `page-manifest` 声明字段/状态/操作,与 `data-field`/`data-state`/`data-op`/`data-perm` 标记双向核对;给 `--prd` 再与 PRD 字段字典、状态枚举、操作出处交叉核对)。声明约定与单页深度规范见 `references/prototype-depth.md`。

## 五阶段循环

```
S1 需求采集 ──G1──> S2 PRD ──G2──> S3 流程图 ──G3──> S4 原型 ──G4──> S5 定稿交付+复盘
```

每个 G 是确认点:产物先过自检闸门,再**选项式**发给确认方(给可选项+推荐项),结论记入 state.md 和决策日志。多模块项目推荐全局模式:G0.5 原型骨架先行,各模块跑到 G3 挂起,全部通过后统一出原型(详见 `skills/pm-pipeline/references/workflow.md`)。

## 依赖

- Python ≥ 3.8(脚本纯标准库,pathlib,Windows/macOS/Linux 通用)
- pandoc(导出 docx 与基线提取用;PATH 或常见安装位自动探测,Windows 有官方安装包)
- 可选配套 skill:laowang-prd(PRD 撰写+自检)、laowang-diagram(流程图+自检)、baoyu-design(HTML 原型)——`check_all.py` 自动探测,未安装则跳过对应自检

## 多工具支持

| 工具 | 接入方式 |
|---|---|
| Kimi Code | `install.py` 装到 `~/.kimi-code/skills` |
| Codex | `install.py` 装到 `~/.codex/skills`;界面元数据见 `agents/openai.yaml` |
| Claude Code | `install.py` 装到 `~/.claude/skills`,见 `agents/claude.md` |
| Cursor | Rules 方式接入,见 `agents/cursor.md` |
| DeepSeek 等通用模型 | SKILL.md 粘贴为系统提示,见 `agents/GENERIC.md` |

## 仓库结构

```
├── install.py                  # 安装器(探测多工具 skills 目录)
├── DEPLOYMENT.md               # 决策引擎(Kev 主用/Jev 备配)部署与配置协议(可选增强)
├── LICENSE                     # MIT
└── skills/pm-pipeline/
    ├── SKILL.md                # 主指令(自包含,可直接粘贴为系统提示)
    ├── references/             # workflow / checklist / conventions / audit-protocol / evolution / jev-integration / prototype-depth
    ├── templates/              # AGENTS.md / MEMORY.md / state.md / 决策日志 / G1确认单
    ├── scripts/                # new_module / check_all / check_semantic / test_prototype / jev_decide / export_docx / refresh_baseline(全 Python 3)
    └── agents/                 # openai.yaml / claude.md / cursor.md / GENERIC.md
```

## License

MIT
