# -*- coding: utf-8 -*-
"""
WorkBuddy Tokens 数据提取器
扫描 ~/.workbuddy/projects/**/*.jsonl，按 messageId 去重，
提取每一次 LLM 请求的 token 用量 / 积分 / 模型 / 工具 / 会话 / 项目信息。
输出: data.json（供看板直接读取）
"""
import json
import glob
import os
import re
import collections
from datetime import datetime, timezone, timedelta

HOME = os.path.expanduser("~")
PROJECTS_DIR = os.path.join(HOME, ".workbuddy", "projects")
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(OUT_DIR, "data.json")

CST = timezone(timedelta(hours=8))

# ---------- 任务类型分类规则 ----------
# 按工具族划分，覆盖 vibe coding / 研究 / 文档 / 数据 / 自动化 等场景
TOOL_CATEGORY = {
    # 编码执行
    "Edit": "编码开发", "Write": "编码开发", "MultiEdit": "编码开发",
    "NotebookEdit": "编码开发", "Bash": "编码开发", "PowerShell": "编码开发",
    # 代码检索理解
    "Read": "代码检索", "Grep": "代码检索", "Glob": "代码检索",
    "LSP": "代码检索", "ToolSearch": "代码检索",
    # 联网研究
    "WebSearch": "联网研究", "WebFetch": "联网研究",
    # 任务编排
    "Agent": "任务编排", "Task": "任务编排", "TaskCreate": "任务编排",
    "TaskUpdate": "任务编排", "TaskList": "任务编排", "TaskGet": "任务编排",
    "TaskOutput": "任务编排", "SendMessage": "任务编排", "ExitPlanMode": "任务编排",
    # 文档产出
    "Skill": "文档产出", "present_files": "文档产出", "show_widget": "文档产出",
    "read_me": "文档产出",
    # 多模态 / 部署
    "ImageGen": "多模态生成", "VideoGen": "多模态生成",
    "DeferExecuteTool": "外部集成",
    "workbuddy_cloudstudio_deploy": "部署运维",
    "automation_update": "自动化",
    "conversation_search": "记忆检索",
    "AskUserQuestion": "纯对话",
}


def categorize(tool_name, rec_type):
    if rec_type == "message" or not tool_name:
        return "纯对话"
    if tool_name in TOOL_CATEGORY:
        return TOOL_CATEGORY[tool_name]
    if tool_name.startswith("mcp__"):
        return "外部集成"
    return "其他工具"


def pretty_project(cwd, folder):
    """把 cwd 转成可读的项目名"""
    src = cwd or folder or ""
    src = src.replace("\\", "/").rstrip("/")
    base = src.split("/")[-1] if src else "unknown"
    # WorkBuddy 自动生成的时间戳工作区
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}", base):
        return "WorkBuddy 临时会话 " + base[:10]
    if re.fullmatch(r"\d{14}", base):
        return "WorkBuddy 临时会话"
    return base or "unknown"


def main():
    files = glob.glob(os.path.join(PROJECTS_DIR, "**", "*.jsonl"), recursive=True)
    seen_mid = set()
    records = []
    session_title = {}          # sessionId -> 标题
    session_file = {}           # sessionId -> 源文件

    for fp in files:
        folder = os.path.basename(os.path.dirname(fp))
        try:
            fh = open(fp, encoding="utf-8", errors="ignore")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"rawUsage"' not in line and '"ai-title"' not in line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue

                sid = o.get("sessionId")

                # 会话标题
                if o.get("type") == "ai-title":
                    t = o.get("title") or o.get("content") or o.get("text")
                    if isinstance(t, list):
                        t = " ".join(str(x.get("text", "")) for x in t if isinstance(x, dict))
                    if sid and t:
                        session_title[sid] = str(t).strip()[:60]
                    continue

                pd = o.get("providerData") or {}
                ru = pd.get("rawUsage") or {}
                if not ru:
                    continue

                mid = pd.get("messageId")
                if mid:
                    if mid in seen_mid:
                        continue          # 同一次 API 响应产生多个记录，只计一次
                    seen_mid.add(mid)

                ptd = ru.get("prompt_tokens_details") or {}
                ctd = ru.get("completion_tokens_details") or {}

                inp = int(ru.get("prompt_tokens") or 0)
                out = int(ru.get("completion_tokens") or 0)
                total = int(ru.get("total_tokens") or (inp + out))
                cached = int(
                    ru.get("prompt_cache_hit_tokens")
                    or ptd.get("cached_tokens")
                    or ru.get("cache_read_input_tokens")
                    or 0
                )
                reasoning = int(
                    ru.get("completion_thinking_tokens")
                    or ctd.get("reasoning_tokens")
                    or 0
                )
                credit = float(ru.get("credit") or 0)

                ts = int(o.get("timestamp") or 0)
                if ts and ts < 1e12:      # 秒 -> 毫秒
                    ts *= 1000
                if not ts:
                    continue

                tool = o.get("name") if o.get("type") == "function_call" else None
                cwd = o.get("cwd") or pd.get("cwd")

                if sid and sid not in session_file:
                    session_file[sid] = os.path.basename(fp)

                records.append({
                    "ts": ts,
                    "sid": sid or "unknown",
                    "proj": pretty_project(cwd, folder),
                    "model": pd.get("requestModelName") or pd.get("model") or "unknown",
                    "tool": tool or "",
                    "cat": categorize(tool, o.get("type")),
                    "in": inp,
                    "out": out,
                    "tot": total,
                    "cache": cached,
                    "think": reasoning,
                    "credit": round(credit, 4),
                })

    records.sort(key=lambda r: r["ts"])

    # ---------- 会话汇总 ----------
    sess = collections.OrderedDict()
    for r in records:
        s = sess.setdefault(r["sid"], {
            "sid": r["sid"], "proj": r["proj"], "start": r["ts"], "end": r["ts"],
            "calls": 0, "in": 0, "out": 0, "tot": 0, "cache": 0, "think": 0,
            "credit": 0.0, "models": collections.Counter(), "cats": collections.Counter(),
            "tools": collections.Counter(),
        })
        s["start"] = min(s["start"], r["ts"])
        s["end"] = max(s["end"], r["ts"])
        s["calls"] += 1
        for k in ("in", "out", "tot", "cache", "think"):
            s[k] += r[k]
        s["credit"] += r["credit"]
        s["models"][r["model"]] += 1
        s["cats"][r["cat"]] += r["tot"]
        if r["tool"]:
            s["tools"][r["tool"]] += 1

    sessions = []
    for s in sess.values():
        main_cat = s["cats"].most_common(1)[0][0] if s["cats"] else "纯对话"
        sessions.append({
            "sid": s["sid"],
            "title": session_title.get(s["sid"], "") or f"{s['proj']} · 未命名会话",
            "proj": s["proj"],
            "start": s["start"], "end": s["end"],
            "dur_min": round((s["end"] - s["start"]) / 60000, 1),
            "calls": s["calls"],
            "in": s["in"], "out": s["out"], "tot": s["tot"],
            "cache": s["cache"], "think": s["think"],
            "credit": round(s["credit"], 2),
            "model": s["models"].most_common(1)[0][0] if s["models"] else "unknown",
            "cat": main_cat,
            "top_tools": [{"n": k, "c": v} for k, v in s["tools"].most_common(6)],
        })
    sessions.sort(key=lambda x: x["start"], reverse=True)

    meta = {
        "generated_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S"),
        "source": PROJECTS_DIR,
        "files_scanned": len(files),
        "requests": len(records),
        "sessions": len(sessions),
        "first_ts": records[0]["ts"] if records else 0,
        "last_ts": records[-1]["ts"] if records else 0,
    }

    payload = {"meta": meta, "records": records, "sessions": sessions}
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    # 同时生成一个 JS 版本，便于双击 HTML 直接打开（规避 file:// 的 fetch 限制）
    with open(os.path.join(OUT_DIR, "data.js"), "w", encoding="utf-8") as f:
        f.write("window.TOKEN_DATA=")
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";")

    print(f"扫描文件: {len(files)}")
    print(f"唯一请求: {len(records)}")
    print(f"会话数量: {len(sessions)}")
    if records:
        print("时间范围: %s ~ %s" % (
            datetime.fromtimestamp(records[0]['ts'] / 1000, CST).strftime('%Y-%m-%d'),
            datetime.fromtimestamp(records[-1]['ts'] / 1000, CST).strftime('%Y-%m-%d')))
        print("总 tokens: %s" % format(sum(r['tot'] for r in records), ','))
        print("总 credit: %.2f" % sum(r['credit'] for r in records))
    print(f"输出: {OUT_JSON}")


if __name__ == "__main__":
    main()
