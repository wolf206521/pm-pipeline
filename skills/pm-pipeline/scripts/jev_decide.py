#!/usr/bin/env python3
"""用法:
  scripts/jev_decide.py request.json [--threshold 0.85] [--timeout 30]
  scripts/jev_decide.py - < request.json          # 从 stdin 读请求

System One 决策适配器(Jev / Kev 双后端):输入「决策场景+候选+上下文」,
输出类型化决策 + 校准置信度,按阈值分流「自动执行 / 转人工」。
API 事实见 references/jev-integration.md(端点/字段均来自官方文档)。

后端切换(环境变量 JEV_BACKEND):
  jev(默认):TypeSafe 托管 API,需 JEV_API_KEY(回退 TYPESAFE_API_KEY),
            base_url 默认 https://api.typesafe.ai/v1,模型默认 jev-latest
  kev:      本地/自托管 Kev 服务(github.com/jaredpalmer/kev,协议与 Jev 相同),
            base_url 取 KEV_BASE_URL,默认 http://localhost:8009,模型默认 kev-latest;
            无需 key(Kev 服务端默认开放;服务端设了 KEV_API_KEY 时客户端同名变量传同样的值)

request.json 两种形态:
  A. 简化形态(单个决策点,脚本组装成一个问题):
     {"scenario": "质量工单路由",          # 决策点名,仅留痕用
      "type": "choice",                    # choice(默认) | noul | score
      "question": "该意见应路由给哪个产物负责人?",
      "candidates": {"prd": "字段或逻辑问题", "flow": "流程问题"},  # choice 用 map;score 用数组;noul 可省
      "context": {"意见": "...", "对照表": "..."}}                 # 即 API 的 state
  B. 原生形态(直接透传 systemone API,可一次问多题):
     {"state": {...}, "questions": {"qid": {"type": "...", "instructions": "...", "criteria": ...}},
      "thresholds": {"qid": 0.9}}          # thresholds 可选,按题覆盖阈值

输出(stdout,JSON):
  {"route": "auto"|"human",   # auto=可自动执行;human=转人工复核
   "backend": "jev"|"kev",     # 实际使用的后端
   "degraded": false,          # true=后端不可用降级,decision 为空
   "decision": ...,            # 综合决策(置信度最低那题的答案;多题时见 answers)
   "confidence": 0.0,          # 综合置信度(取各题最低)
   "reasons": ["..."],         # 由概率分布推导的说明(模型不返回文本理由,不编造)
   "answers": {"qid": {...}},  # 逐题明细
   "model": "jev-1.13.0"}

退出码:0=route=auto;1=低置信转人工;2=用法错误;3=后端不可用降级转人工。
环境变量:JEV_BACKEND / JEV_API_KEY(回退 TYPESAFE_API_KEY)/ JEV_BASE_URL / JEV_MODEL /
        JEV_THRESHOLD / KEV_BASE_URL / KEV_API_KEY / KEV_MODEL。
跨平台:纯标准库,Python ≥3.8。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

ENDPOINT_PATH = "/systemone"
DEFAULT_THRESHOLD = 0.85
MAX_RETRIES = 2  # 429/529 指数退避重试次数

# 两个后端实现同一套 System One 协议(POST <base>/v1/systemone);
# confidence 公式同为 TypeSafe reference adapter 口径,noul 的 |2p-1| 折算两者通用。
BACKENDS = {
    "jev": {
        "default_base_url": "https://api.typesafe.ai/v1",
        "default_model": "jev-latest",
        "base_url_env": "JEV_BASE_URL",
        "model_env": "JEV_MODEL",
        "key_env": ("JEV_API_KEY", "TYPESAFE_API_KEY"),
        "key_required": True,
        "no_key_hint": "未配置 JEV_API_KEY(或 TYPESAFE_API_KEY)",
        "unreachable_hint": "Jev API 不可达",
    },
    "kev": {
        "default_base_url": "http://localhost:8009",
        "default_model": "kev-latest",
        "base_url_env": "KEV_BASE_URL",
        "model_env": "KEV_MODEL",
        "key_env": ("KEV_API_KEY",),  # 仅服务端开了鉴权才需要,值与服务端相同
        "key_required": False,
        "no_key_hint": "",  # Kev 无需 key
        "unreachable_hint": "Kev 未启动或不可达",
    },
}


class JevUnavailable(Exception):
    """无 key / 网络失败 / 非 2xx:调用方据此降级转人工,不编造结果。"""


def get_config():
    name = os.environ.get("JEV_BACKEND", "jev").strip().lower()
    if name not in BACKENDS:
        raise JevUnavailable(f"未知 JEV_BACKEND={name!r}(应为 jev|kev),降级转人工")
    spec = BACKENDS[name]
    api_key = None
    for env in spec["key_env"]:
        if os.environ.get(env):
            api_key = os.environ[env]
            break
    return {
        "backend": name,
        "api_key": api_key,
        "key_required": spec["key_required"],
        "no_key_hint": spec["no_key_hint"],
        "unreachable_hint": spec["unreachable_hint"],
        "base_url": os.environ.get(spec["base_url_env"], spec["default_base_url"]).rstrip("/"),
        "model": os.environ.get(spec["model_env"]) or os.environ.get("JEV_MODEL") or spec["default_model"],
    }


def configured():
    """当前后端是否具备调用条件(jev 需 key;kev 无需 key,可达性在调用时探测)。"""
    try:
        cfg = get_config()
    except JevUnavailable:
        return False
    return bool(cfg["api_key"]) or not cfg["key_required"]


def endpoint_url(base_url):
    """base_url 带不带 /v1 都能用,归一化为 <base>/v1/systemone。"""
    base = base_url.rstrip("/")
    return base + ENDPOINT_PATH if base.endswith("/v1") else base + "/v1" + ENDPOINT_PATH


def build_native_request(req, model):
    """把简化形态归一化成原生请求体 {state, model, questions} + thresholds。"""
    if "questions" in req:  # 原生形态,直接透传
        if "state" not in req:
            raise ValueError("原生形态缺 state 字段")
        return (
            {"state": req["state"], "model": req.get("model", model), "questions": req["questions"]},
            req.get("thresholds", {}),
        )
    qtype = req.get("type", "choice")
    question = {"type": qtype, "instructions": req["question"]}
    candidates = req.get("candidates")
    if qtype == "choice":
        if not isinstance(candidates, dict) or len(candidates) < 2:
            raise ValueError("choice 型 candidates 需为 ≥2 个选项的 map{选项: 说明}")
        question["criteria"] = candidates
    elif qtype == "score":
        if not isinstance(candidates, list) or not 2 <= len(candidates) <= 10:
            raise ValueError("score 型 candidates 需为 2~10 档的有序数组")
        question["criteria"] = candidates
    elif qtype == "noul":
        if candidates:
            question["criteria"] = candidates  # 可选:{true: 是的含义, false: 否的含义}
    else:
        raise ValueError(f"未知 type: {qtype}(应为 choice|noul|score)")
    qid = req.get("scenario", "decision")
    return (
        {"state": req.get("context", ""), "model": model, "questions": {qid: question}},
        {},
    )


def call_backend(payload, timeout=30):
    """POST <base>/v1/systemone(Jev 与 Kev 同一协议)。返回响应 dict;失败抛 JevUnavailable。"""
    cfg = get_config()
    if cfg["key_required"] and not cfg["api_key"]:
        raise JevUnavailable(f"{cfg['no_key_hint']},降级转人工")
    url = endpoint_url(cfg["base_url"])
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if cfg["api_key"]:
        headers["Authorization"] = "Bearer " + cfg["api_key"]
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        if attempt:
            time.sleep(2 ** attempt)  # 429/529 指数退避(官方文档建议)
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            if e.code == 401:
                if cfg["backend"] == "kev":
                    raise JevUnavailable("Kev 服务端要求鉴权但 KEV_API_KEY 未配置或不匹配(401),降级转人工")
                raise JevUnavailable("API key 无效(401),降级转人工")
            if e.code == 422:
                detail = e.read().decode("utf-8", "replace")[:300]
                raise JevUnavailable(f"请求体校验失败(422): {detail}")
            if e.code in (429, 529):
                continue  # 限流/过载,退避重试
            raise JevUnavailable(f"HTTP {e.code},降级转人工")
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            last_err = f"{cfg['unreachable_hint']}({cfg['base_url']}): {e}"
            continue  # 网络类问题重试
    raise JevUnavailable(f"重试 {MAX_RETRIES} 次仍失败({last_err}),降级转人工")


def normalize_answer(qid, answer):
    """把三种答案归一化成 {decision, confidence, reasons[]};reasons 由概率推导,不编造。"""
    atype = answer.get("type")
    if atype == "noul":
        p = answer.get("noul", 0.0)
        return {
            "decision": "yes" if p >= 0.5 else "no",
            "confidence": abs(2 * p - 1),  # 官方建议:noul 无 confidence,用 |2p-1| 折算
            "reasons": [f"{qid}: P(yes)={p:.2f}"],
        }
    if atype == "choice":
        probs = answer.get("probabilities", {})
        ranked = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)
        reasons = [f"{qid}: P({k})={v:.2f}" for k, v in ranked[:2]]
        if len(ranked) >= 2:
            reasons.append(f"与次优差距 {ranked[0][1] - ranked[1][1]:.2f}")
        return {
            "decision": answer.get("choice"),
            "confidence": answer.get("confidence", 0.0),
            "reasons": reasons,
        }
    if atype == "score":
        legend = answer.get("legend", {})
        score = answer.get("score", 0.0)
        nearest = legend.get(str(int(round(score))), "")
        return {
            "decision": score,
            "confidence": answer.get("confidence", 0.0),
            "reasons": [f"{qid}: score={score:.2f}(最接近档位: {nearest})"],
        }
    return {"decision": None, "confidence": 0.0, "reasons": [f"{qid}: 未知答案类型 {atype!r}"]}


def decide(req, default_threshold=DEFAULT_THRESHOLD, timeout=30):
    """主逻辑:请求 → 归一化 → 阈值分流。返回输出 dict(不处理退出码)。"""
    cfg = get_config()
    payload, thresholds = build_native_request(req, cfg["model"])
    resp = call_backend(payload, timeout=timeout)

    answers = {}
    reasons = []
    weakest_id, weakest_conf = None, 1.0
    for qid, answer in resp.get("answers", {}).items():
        norm = normalize_answer(qid, answer)
        thr = float(thresholds.get(qid, default_threshold))
        norm["threshold"] = thr
        norm["route"] = "auto" if norm["confidence"] >= thr else "human"
        norm["reasons"].append(
            f"confidence {norm['confidence']:.2f} {'≥' if norm['route'] == 'auto' else '<'} 阈值 {thr:.2f} → {norm['route']}"
        )
        answers[qid] = norm
        reasons.extend(norm["reasons"])
        if norm["confidence"] < weakest_conf:
            weakest_id, weakest_conf = qid, norm["confidence"]

    if not answers:
        raise JevUnavailable("响应无 answers 字段,降级转人工")
    route = "auto" if all(a["route"] == "auto" for a in answers.values()) else "human"
    return {
        "route": route,
        "backend": cfg["backend"],
        "degraded": False,
        "decision": answers[weakest_id]["decision"],
        "confidence": round(weakest_conf, 4),
        "reasons": reasons,
        "answers": answers,
        "model": resp.get("model"),
        "usage": resp.get("usage"),
    }


def degraded_result(exc):
    try:
        backend = get_config()["backend"]
    except JevUnavailable:
        backend = os.environ.get("JEV_BACKEND", "jev")
    return {
        "route": "human",
        "backend": backend,
        "degraded": True,
        "decision": None,
        "confidence": 0.0,
        "reasons": [f"{backend}_unavailable: {exc}"],
        "answers": {},
        "model": None,
    }


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = {a.split("=")[0][2:]: a.split("=")[1] for a in sys.argv[1:] if a.startswith("--") and "=" in a}
    if "-h" in sys.argv or "--help" in sys.argv:
        print(__doc__)
        return 0
    if len(args) != 1:
        print(__doc__)
        return 2
    threshold = float(opts.get("threshold", os.environ.get("JEV_THRESHOLD", DEFAULT_THRESHOLD)))
    timeout = int(opts.get("timeout", 30))
    try:
        raw = sys.stdin.read() if args[0] == "-" else open(args[0], encoding="utf-8").read()
        req = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        print(f"请求读取失败: {e}", file=sys.stderr)
        return 2
    try:
        out = decide(req, default_threshold=threshold, timeout=timeout)
    except (JevUnavailable, ValueError) as e:
        out = degraded_result(e)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 3 if isinstance(e, JevUnavailable) else 2
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["route"] == "auto" else 1


if __name__ == "__main__":
    sys.exit(main())
