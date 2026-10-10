# JEV-INTEGRATION · Jev 决策集成(通用模板)

Jev 是 TypeSafe AI(typesafe.ai)的 System One 模型:输入**状态 + 类型化问题**,返回**类型化决策 + 校准置信度**,不生成文本。它专为自动化设计——代码按置信度阈值决定「自动执行」还是「转人工复核」。

本文件定义:流水线上哪些决策点可以交给 Jev、怎么接、以及边界。

## 已核实的 API 事实(来自官方文档)

以下来自 https://docs.typesafe.ai 的 Quickstart 与 API Reference,不是推测:

- 端点:`POST https://api.typesafe.ai/v1/systemone`
- 认证:`Authorization: Bearer <API_KEY>`(API key 在 TypeSafe dashboard 获取;官方 SDK 读环境变量 `TYPESAFE_API_KEY`)
- 模型:请求用别名 `"jev-latest"`,响应里回实际版本号(如 `jev-1.13.0`)
- 请求体:`{"state": string|object|array, "model": "jev-latest", "questions": {...}}`
- 三种问题类型(可在一次调用里混用、并行评估、互相独立):
  - `noul`:是非判断 → 返回 `{"type":"noul","noul":0~1}`(值=「是」的概率,**不带 confidence**;需要时用 `|2p-1|` 折算)
  - `choice`:从给定选项里选一个 → 返回 `{"type":"choice","choice","probabilities","confidence"}`
  - `score`:按自定义档位打分 → 返回 `{"type":"score","score","legend","probabilities","confidence"}`
- `confidence`:0~1,由概率分布形状推导,可直接做阈值分流;官方推荐三段式:**高置信自动执行 / 中置信谨慎(要确认)/ 低置信转人工**,且**阈值随操作风险上调**(高风险动作用更高的阈值)
- 错误码:401(key 无效)/ 422(请求体校验失败)/ 429(限流)/ 529(过载);429/529 应指数退避重试
- 官方 Python SDK:`pip install typesafe-sdk`(需 Python ≥3.10),`TypeSafeClient()` 默认读 `TYPESAFE_API_KEY`、默认模型 `jev-latest`

### 占位部分(官方文档未给出,用配置兜底,不编造)

- 限流的具体数值、计费单价:官方页只有相对比较,没有公开数字 → 不写死
- dashboard 具体 URL → 只写「TypeSafe dashboard」
- 本仓库适配器 `scripts/jev_decide.py` 走**纯标准库 HTTP 直连**(不依赖 SDK,保住 Python ≥3.8 与零依赖约束);若官方 API 有变动,改 `JEV_BASE_URL` 或脚本里的 `ENDPOINT_PATH` 一处即可

## 配置

| 环境变量 | 必需 | 说明 |
|---|---|---|
| `JEV_BACKEND` | 否 | 决策后端:`jev`(默认,TypeSafe 托管 API)\| `kev`(自托管 Kev 服务) |
| `JEV_API_KEY` | jev 后端必需 | Jev API key;未设置时回退读 `TYPESAFE_API_KEY` |
| `JEV_BASE_URL` | 否 | 默认 `https://api.typesafe.ai/v1` |
| `JEV_MODEL` | 否 | 默认 `jev-latest`(kev 后端默认 `kev-latest`,可用 `KEV_MODEL` 单独覆盖) |
| `JEV_THRESHOLD` | 否 | 默认置信度阈值,默认 `0.85`;调用方可按决策点覆盖 |
| `KEV_BASE_URL` | kev 后端用 | Kev 服务地址,默认 `http://localhost:8009`(带不带 `/v1` 均可,脚本自动归一) |
| `KEV_API_KEY` | 否 | 仅当 Kev 服务端设了同名鉴权变量时才需要,值与服务端相同 |

后端不可用(key 缺失 / 网络不可达 / 调用失败)时,所有集成点**优雅降级为「转人工」**:不阻塞流程、不编造结果,留痕说明降级原因。

## 备用引擎:Kev

Kev(github.com/jaredpalmer/kev)是一组可自行训练/自托管的小型决策模型,**API 与 TypeSafe System One 协议一致**——同一个 `POST /v1/systemone`,同一份请求/响应字段,TypeSafe 官方 SDK 指向 Kev 服务地址即可不改代码使用。

### Jev vs Kev 对照要点

| 维度 | Jev | Kev |
|---|---|---|
| 部署 | TypeSafe 托管 API | 自托管(本地/GPU 服务器/Modal) |
| 协议 | `POST /v1/systemone` | **同一协议**,confidence 公式与 TypeSafe reference adapter 同源(choice `(p_max−1/K)/(1−1/K)`、score MAD 口径;noul 返回概率,`|2p−1|` 折算同样适用) |
| 校准 | 开箱即用 | 开箱即用:每个 checkpoint 带拟合温度(temperature),输出即校准后概率 |
| 配额/成本 | 按 API 用量 | 无配额,成本=自有算力 |
| 规格 | 单一托管模型 | 0.8B / 4B / 9B / 27B 四档;0.8B 可在 Mac CPU 试跑(`--device cpu`),4B 官方建议作为起点 |
| 官方基准(新源准确率/5% 错误预算下可自动化比例) | 0.857 / 0.70 | 27B 0.851 / 0.52–0.69;0.8B 明显弱(0.14) |

### 切换方法

```bash
# 终端启动 Kev(官方 quick start,首次会下载模型):
#   git clone https://github.com/jaredpalmer/kev.git && cd kev
#   uv sync --extra serve
#   uv run --extra serve python -m kev.serve --run jaredpalmer/kev-4b --port 8009
export JEV_BACKEND=kev
export KEV_BASE_URL=http://localhost:8009
# 之后 scripts/jev_decide.py 与 scripts/check_semantic.py 零改动走 Kev;
# 切回 Jev:unset JEV_BACKEND(或 JEV_BACKEND=jev)
```

### 红线(违反即返工)

1. **阈值语义不平移**:两者 confidence 公式一致,但分布特性不同——官方基准里同样 5% 错误预算下 Jev 可自动化 0.70,Kev-4B/9B/27B 为 0.52–0.69,Kev-0.8B 仅 0.14。**切后端后必须用自有语料做留出评测(kev.benchmark 支持 `--remote` 打任意 System One 端点),重新标定阈值后才能放行自动化**;Jev 上调好的阈值不能直接搬到 Kev
2. **中文表现需实测**:Kev 基座是 Qwen3.5/3.8,但官方基准全是英文任务,中文决策质量无公开数据;上线前用本工程真实 PRD/对照表跑一轮评测

### 上手准备清单

- **Jev**:TypeSafe dashboard 申请 API key + 确认额度;配 `JEV_API_KEY` 即可
- **Kev**:
  - 环境:Python 3.12/3.13 + uv;源码安装(`pip install kev` 是另一个同名 ORM 包,**不是**本项目,勿装错)
  - 硬件:Apple Silicon 走 MLX 开箱即用;**Intel Mac 无 MLX,不在官方支持列**,只能 `--device cpu` 试跑 0.8B;正式用建议 GPU 服务器(4B 建议 L40S 级)或官方 Modal 一键部署(缩放到零,闲置不计费)
  - 无 GPU 先试:Hugging Face Space(huggingface.co/spaces/jaredpalmer/kev)可在浏览器里跑 4B/0.8B

## 决策点清单(可交给 Jev 的管线决策)

通用原则:Jev 只做**判断与分流**,判断依据是传入的 state(文档内容/对照表/清单),不做写入。每个决策点标注推荐问题类型与默认阈值(按风险定,宁高勿低)。

| # | 决策点 | 时机 | 类型 | state(判据) | 默认阈值 | 高置信动作 | 低置信动作 |
|---|---|---|---|---|---|---|---|
| 1 | **闸门语义检查**:PRD 是否达标(指标可量化/状态机有出口/字段字典完整) | G2 闸门前 | noul ×N(一次调用批量问) | PRD 全文 | 0.70 | 语义项判 PASS | 转人工复核该项 |
| 2 | **审计发现初筛分类**:审计协议跑出的发现分成「真缺口/表述问题/误报」 | 基线审计后 | choice | 单条发现 + 相关章节摘录 | 0.80 | 按类进入对应处理队列 | 进人工复核队列 |
| 3 | **质量工单路由**:评审意见/返工项路由到 PRD / 流程图 / 原型负责人 | review 意见闭环时 | choice | 意见文本 + 三方对照表 | 0.75 | 自动指派并留痕 | 挂起,选项式问人 |
| 4 | **异常分流建议**:流程图异常分支在原型中是「做页面」还是「标注不在原型范围」 | S4 规划时 | choice | 异常分支描述 + 页面清单 | 0.80 | 写进 S4 页面计划(仍过 G4 确认) | 列入 G4 确认单由客户定 |
| 5 | **确认单口径一致性初判**:待发确认单与 state.md/决策日志的口径是否一致 | G1–G4 发确认单前 | noul | 确认单草稿 + state.md + 决策日志相关条目 | 0.85 | 判一致,允许进入发送流程 | 拦截,人工核对后再发 |

实现入口统一是 `scripts/jev_decide.py`;G2 语义闸门已由 `scripts/check_semantic.py` 封装(决策点 1)。

### 问题设计要点(来自官方文档的使用约束)

- **一问一判断**:每题只问一个具体、几秒内可答的判断;复合判断拆成多题一次调用并行问,在代码里加权合成,不要写「分析并给出建议」式大题
- **选项要给全**:choice 的 criteria 覆盖所有可能,不确定时加 `other` 兜底项
- **instructions 写完整**:问题 ID 不发给模型,判断逻辑全写在 instructions 里;引用 state 里的字段用反引号路径(如 `` `prd_excerpt` ``)
- **投机式提问**:可能用得上的问题一次问全,代码决定用哪些答案

## 集成模式:typed decision + 置信度阈值

```
         ┌────────────┐   confidence ≥ 阈值    ┌──────────────┐
state ──▶│ Jev 类型化判断│ ───────────────────▶ │ 自动执行 + 留痕  │
         └────────────┘ ───────────────────▶ │ 转人工 + 留痕   │
                          confidence < 阈值    └──────────────┘
```

- **留痕格式**(写入模块 `review/` 或决策日志):`| 日期 | 决策点 | decision | confidence | 阈值 | 路由(auto/human) |`,降级时追加 `降级原因`
- 阈值按决策点风险定:会改动客户可见物的(确认单、页面计划)阈值高;只做内部预筛的可放低

## 与「选项式确认」规则的关系

硬性规则 8(确认事项一律选项式)不变。Jev 接入后的分工:

- **高置信(≥阈值)**:内部流程性判断(分类、路由、预筛)自动执行,**不打扰客户**,但留痕可查
- **低置信(<阈值)或降级**:**必须选项式问人**——给可选项+推荐项(推荐项=Jev 的答案+置信度),人拍板后照常记决策日志
- Jev 的输出**永远可以作为推荐项的输入**,让选项式确认更省时,但不能代替人点选

## 不做什么(边界,违反即返工)

1. **Jev 不做业务事实写入**:不直接改 PRD/state.md/基线文件;它的输出只是「建议/分流信号」,落盘动作由人或既定脚本执行
2. **不替代客户确认点**:G1–G4 确认点永远是人;Jev 只能在确认点**之前**做初判、在确认单**生成**时做核对
3. **不编造置信结果**:调用失败/无 key 时输出「转人工+降级原因」,不输出任何假的 decision/confidence
4. **不做慢推理**:需要长链推理的判断拆成多个小问题在代码里合成;拆不动的就不交给 Jev
