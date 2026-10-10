# DEPLOYMENT · 决策引擎部署文档

管线的「语义闸门 / 决策分流」能力依赖一个 System One 协议决策引擎。本文档覆盖部署与验收:

- **主用:Kev**(自托管,[github.com/jaredpalmer/kev](https://github.com/jaredpalmer/kev))——三种部署形态(A GPU 服务器 / B Modal 云 / C CPU 试用)
- **备配:Jev**(TypeSafe 托管 API)——当前挂起,有额度时启用
- 与管线的连通验证、验收 checklist、运维红线

管线侧只需环境变量切换,脚本零改动:

| 环境变量 | 作用 | 默认 |
|---|---|---|
| `JEV_BACKEND` | `jev` \| `kev`(主用部署时显式设为 `kev`) | `jev` |
| `KEV_BASE_URL` | Kev 服务地址(带不带 `/v1` 均可,适配器自动归一) | `http://localhost:8009` |
| `KEV_API_KEY` | 仅 Kev 服务端开了鉴权才需要,值与服务端相同 | 空 |
| `KEV_MODEL` | Kev 请求模型名 | `kev-latest` |
| `JEV_API_KEY` | Jev key(回退 `TYPESAFE_API_KEY`) | 空 |
| `JEV_BASE_URL` | Jev API 地址 | `https://api.typesafe.ai/v1` |

## 官方 README 关键事实(部署前必读)

来自 Kev 官方 README,不是推测:

1. **协议一致**:Kev 实现 TypeSafe 的 `POST /v1/systemone`,请求/响应字段相同(noul/choice/score 三型问题,choice/score 带 `confidence`,noul 返回概率);TypeSafe 官方 Python SDK 指向 Kev 地址即可不改代码使用
2. **校准开箱即用**:每个 checkpoint 出厂带拟合温度(fitted temperature),返回的概率分布即校准后结果;confidence 公式与 TypeSafe reference adapter 同源
3. **温度可重拟合**:每 checkpoint 附 temperature 值,官方 `scripts/calibrate_checkpoint.py` 支持在你自己的标注数据上重拟合;`kev.benchmark --remote <地址>` 可对任意 System One 端点(含 Jev)跑留出评测
4. **模型规格**:0.8B(任意 4 GB GPU / Apple Silicon,试用)/ 4B(官方建议起点,L40S 级 GPU 或 32 GB Mac)/ 9B(约 17 GB 显存)/ 27B(80 GB 显卡,51 GB 权重)
5. **上下文**:0.8B/4B/9B 验证上下文 8,192 token;服务端 state 上限 65,536 token,超限返回 422 而不是静默截断

## 1. Kev 主用部署

### A. GPU 服务器(推荐生产)

**前置条件**

- NVIDIA GPU + CUDA;显存按模型:0.8B ≥4 GB / 4B 建议 L40S 级 / 9B 约 17 GB / 27B 80 GB
- Python 3.12 或 3.13 + uv(官方要求;torch 暂无 3.14 wheel)
- 能访问 Hugging Face(首次启动下载基座权重 + 适配器)

**逐步命令**

```bash
git clone https://github.com/jaredpalmer/kev.git && cd kev
uv sync --extra serve
# 启动(4B 为官方建议起点;--run 可换 kev-0.8b / kev-9b / kev-27b,或 @v1.0 锁定版本)
KEV_API_KEY=$(openssl rand -hex 24) \
uv run --extra serve python -m kev.serve --run jaredpalmer/kev-4b --port 8009 --host 0.0.0.0 --device cuda
```

记下生成的 `KEV_API_KEY`,管线侧要配同一个值。

**验证命令**

```bash
curl -s http://<服务器>:8009/v1/models -H "Authorization: Bearer $KEV_API_KEY"
curl -s http://<服务器>:8009/v1/systemone \
  -H "Authorization: Bearer $KEV_API_KEY" -H 'content-type: application/json' -d '{
  "state": "客户要求工单状态枚举和字段字典对齐。",
  "model": "kev-latest",
  "questions": {"urgent": {"type": "noul", "instructions": "Does this need urgent human attention?"}}}'
# 期望返回:{"model": ..., "answers": {"urgent": {"type": "noul", "noul": 0.xx}}, "usage": {...}}
```

**常见坑**

- `pip install kev` 装的是**同名 ORM 包(K.E.V. ORM),不是本项目**;Kev 未发布 PyPI,必须源码安装
- 服务默认只绑 `127.0.0.1`;跨机访问必须 `--host 0.0.0.0`,且**务必设 `KEV_API_KEY`**(服务端默认无鉴权)
- `--device auto`(默认)按 CUDA → MPS → CPU 顺序探测;生产建议显式 `--device cuda`,探测失败直接报错而不是悄悄掉到 CPU
- CUDA 上跑 Qwen3.5 基座(0.8B/4B/9B)建议装 `flash-linear-attention`(官方部署镜像已含)
- 权重版本用 `@v1.0` tag 锁定,避免升级后行为漂移

### B. Modal 云(无 GPU 方案)

**前置条件**:Modal 账号(`pip install modal && modal setup`)。

**逐步命令**

```bash
curl -LO https://raw.githubusercontent.com/jaredpalmer/kev/main/skills/kev-deploy/scripts/kev_serve.py
KEV_API_KEY=$(openssl rand -hex 24) modal deploy kev_serve.py
# 端点形如 https://<你的-workspace>--kev-api.modal.run,KEV_MODEL=jaredpalmer/kev-9b 可换模型
```

**验证命令**:同 A 节的 curl,地址换成 Modal 端点。

**常见坑**

- 闲置缩放到零(不计费),但**冷启动约 35 秒**——管线侧调大超时:`jev_decide.py --timeout=60`
- 成本按 GPU 时价(官方参考:L40S ≈ $1.95/h,H100 ≈ $3.95/h,B200 ≈ $6.25/h);只在请求期间计费
- 管线侧配置:`JEV_BACKEND=kev`、`KEV_BASE_URL=https://<端点>`、`KEV_API_KEY=<部署时生成的值>`

### C. CPU 试用(任何机器,仅联调)

**前置条件**:任意机器(Intel Mac 无 MLX、不在官方支持列,只能走这条);Python 3.12/3.13 + uv。

```bash
git clone https://github.com/jaredpalmer/kev.git && cd kev && uv sync --extra serve
uv run --extra serve python -m kev.serve --run jaredpalmer/kev-0.8b --port 8009 --device cpu
```

**性能预期**:秒级/题,只适合验证连通性与管线联调,不适合标定与生产;0.8B 精度明显弱(官方基准:5% 错误预算下可自动化比例仅 0.14,大模型档 0.52–0.69)。

**常见坑**

- **不要拿 CPU 试用的结果做阈值标定**——0.8B 与生产档(4B+)的校准特性不同
- CPU 默认 fp32(与官方评测口径一致);内存吃紧可 `KEV_DTYPE=bf16`,但这就不再是评测口径

## 2. Jev 挂起备配

当前状态:**挂起**(有额度时启用)。配置位置:shell 环境变量(profile 或工程本地 env 文件,**key 不入库**)。

```bash
# 启用 Jev(有额度时):
export JEV_API_KEY=<TypeSafe dashboard 获取>
export JEV_BACKEND=jev                 # 或不设置(jev 是默认后端)
# JEV_BASE_URL 默认 https://api.typesafe.ai/v1,一般不用设

# 切回 Kev:
export JEV_BACKEND=kev
```

挂起期间无需任何配置:未设 `JEV_API_KEY` 且 `JEV_BACKEND=kev` 指向的服务不可达时,所有集成点自动降级为「转人工 + 人工核对清单」,不阻塞流程。

## 3. 与管线的连通验证

```bash
export JEV_BACKEND=kev KEV_BASE_URL=http://<主机>:8009   # 按实际部署填

# ① 通用决策入口冒烟(期望 exit 0 或 1,输出 JSON 含 "backend": "kev"、"decision"、"confidence")
echo '{"scenario":"连通测试","type":"noul","question":"这段文字是否表达了明确可执行的需求?","context":"原型需要覆盖全部异常分支。"}' \
  | python3 scripts/jev_decide.py -

# ② 语义闸门冒烟(期望逐项 PASS/FAIL/REVIEW,不再是降级清单)
python3 scripts/check_semantic.py <模块目录>

# ③ 阈值分流验证(同一请求打两个阈值,低阈值应 auto、0.99 应 human;exit 码 0 vs 1)
echo '{"scenario":"连通测试","type":"noul","question":"这段文字是否表达了明确可执行的需求?","context":"原型需要覆盖全部异常分支。"}' \
  | python3 scripts/jev_decide.py - --threshold=0.5
echo '{"scenario":"连通测试","type":"noul","question":"这段文字是否表达了明确可执行的需求?","context":"原型需要覆盖全部异常分支。"}' \
  | python3 scripts/jev_decide.py - --threshold=0.99

# ④ 降级路径验证(停掉 Kev 服务后重跑 ①,期望 exit 3 + 「Kev 未启动或不可达」)
```

## 4. 验收 checklist

装完逐项打勾,全过才算部署完成:

- [ ] `GET /v1/models` 返回已加载模型信息
- [ ] `POST /v1/systemone` 返回 `answers` JSON(noul/choice/score 三型各试一题)
- [ ] `jev_decide.py` 连通:exit 0/1,输出含 `"backend": "kev"`
- [ ] 阈值分流生效:同一请求 `--threshold=0.5` 与 `--threshold=0.99` 的路由(auto/human)符合预期
- [ ] 降级路径有效:停服务后 `jev_decide.py` exit 3、提示「Kev 未启动或不可达」;`check_semantic.py` 降级输出人工核对清单
- [ ] `check_semantic.py` 在真实模块上跑出逐项结果(非降级清单)
- [ ] 留出评测已完成,阈值按自有语料标定并记录(写进 `JEV_THRESHOLD` 或调用参数)
- [ ] 中文语料实测结论已归档到工程 `01-记忆/`

## 5. 运维红线

1. **阈值不可平移**:Jev 调好的阈值不能直接用于 Kev(官方基准:5% 错误预算下可自动化比例 Jev 0.70 vs Kev 4B/9B/27B 0.52–0.69)。用自有语料留出评测重新标定:

   ```bash
   # 在 kev 仓库内,对任意 System One 端点跑官方基准
   uv run python -m kev.benchmark --remote http://<主机>:8009 --suite evals/v4/transfer-v4 --out runs/my-eval
   ```

   更推荐用本工程真实 PRD/对照表构造留出集,配合 `scripts/calibrate_checkpoint.py` 重拟合温度
2. **中文实测**:Kev 基座为 Qwen3.5/3.8,但官方基准全是英文任务;中文决策质量无公开数据,上线前必须用真实中文语料实测
3. **版本锁定**:`--run jaredpalmer/kev-4b@v1.0` 固定权重版本;升级模型版本 = 重新走验收 checklist
4. **安全**:对外暴露必须 `KEV_API_KEY` 鉴权 + 反代 TLS;key 只进环境变量,不进仓库
