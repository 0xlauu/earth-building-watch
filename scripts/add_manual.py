#!/usr/bin/env python3
"""把 Lau 人工转发的内容加入原始库和待审队列（见 EDITOR.md 第 1c 步）。

python3 scripts/add_manual.py --url URL --title 原标题 --source "Instagram · @账号" [--published YYYY-MM-DD] [--snippet 要点] [--lang zh]
只收已经打开核实过的链接。同一网址或同一标题已在库里就不重复加。
"""
import argparse, hashlib, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa
import fetch

ap = argparse.ArgumentParser()
ap.add_argument("--url", required=True)
ap.add_argument("--title", required=True)
ap.add_argument("--source", required=True)
ap.add_argument("--published", default="")
ap.add_argument("--snippet", default="")
ap.add_argument("--lang", default="")
ap.add_argument("--tier", default="T2", choices=["T1", "T1_5", "T2"])
a = ap.parse_args()
if not a.url.startswith(("http://", "https://")):
    sys.exit("url 必须是 http(s) 网址")
store = load_json(RAW, {"items": {}, "title_keys": {}})
iid = hashlib.sha1(fetch.canon_url(a.url).encode()).hexdigest()[:12]
tk = fetch.title_key(a.title)
if iid in store["items"] or (tk and tk in store["title_keys"]):
    sys.exit(f"已在库里：{store['title_keys'].get(tk, iid)}")
pub = fetch.parse_date(a.published + "T12:00:00+08:00") if a.published else None
store["items"][iid] = {"id": iid, "title": a.title, "url": a.url, "source_id": "manual", "source_name": f"Lau 转发 · {a.source}",
                       "tier": a.tier, "lang": a.lang, "aspect": "人工转发", "publisher": "", "published_at": pub.isoformat() if pub else None,
                       "first_seen": now_cst().isoformat(timespec="seconds"), "snippet": a.snippet[:600], "status": "pending"}
if tk:
    store["title_keys"][tk] = iid
save_json(RAW, store)
fetch.write_pending(store)
print(f"已加入：{iid}")
