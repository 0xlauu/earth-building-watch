#!/usr/bin/env python3
"""给汇报机器人用：打印最新一期的摘要、待审数量和信源健康。

用法：python3 scripts/status.py            # 中文文本，可直接改写成汇报
      python3 scripts/status.py --json     # 机器可读
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa

latest = load_json(os.path.join(ROOT, "docs", "latest.json"), {})
state = load_json(STATE, {})
pending = load_json(PENDING, {"count": 0})
cfg = load_json(CONFIG, {})
fails = [f"{k}（{v.get('error','')[:60]}）" for k, v in state.items() if not k.startswith("_") and not v.get("ok")]
info = {"site_published": cfg.get("published", False), "site": cfg.get("base_url"), "latest": latest,
        "pending_count": pending.get("count", 0), "last_fetch": state.get("_last_fetch", {}), "failing_sources": fails,
        "today": today_cst(), "has_today_issue": latest.get("date") == today_cst()}
if "--json" in sys.argv:
    print(json.dumps(info, ensure_ascii=False, indent=1)); sys.exit(0)
print(f"今天 {info['today']}，最新一期 {latest.get('date','无')}（{'是今天' if info['has_today_issue'] else '不是今天'}）")
if latest:
    c = latest["counts"]
    print(f"精选 {c['pick']}，简讯 {c['brief']}，丢弃 {c['drop']}，合并 {c['merged']}")
    print("导语：" + (latest.get("lead") or ""))
    for i, p in enumerate(latest["picks"][:3], 1):
        print(f"{i}. [{p['category']}·{p['score']}] {p['title']}\n   对你：{p['for_you']}\n   {p['url']}")
    for a in latest.get("actions", []):
        print("可做：" + a)
    print("日报：" + latest.get("daily_url", "") + ("" if info["site_published"] else "（网站还没上线）"))
print(f"待审 {info['pending_count']} 条；上次抓取 {info['last_fetch'].get('at','无')}")
print("抓取失败的信源：" + ("、".join(fails) if fails else "无"))
