#!/usr/bin/env python3
"""把每日机器人用 X 连接器抓到的帖子导入原始库和待审队列。

两步用法（见 EDITOR.md 第 1b 步）：
  python3 scripts/x_ingest.py --plan
      打印今天要做的 X 连接器调用（user-X / search_posts_all 的完整参数，start_time = 现在减 24 小时）。
  python3 scripts/x_ingest.py data/x/inbox/YYYY-MM-DD/*.json
      每个文件是一次 search_posts_all 的原样返回（JSON），文件名 = 查询 id，例如 x-people.json。
      导入规则和 fetch.py 一样：按网址和标题去重；48 小时内的进待审，更早的只归档。
"""
import glob, hashlib, json, os, re, sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa
import fetch

XCFG = os.path.join(ROOT, "sources_x.json")
INBOX = os.path.join(ROOT, "data", "x", "inbox")


def plan():
    cfg = load_json(XCFG, {})
    start = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    day = today_cst()
    os.makedirs(os.path.join(INBOX, day), exist_ok=True)
    print(f"# 今天 {day}：调用 {len(cfg['queries'])} 次 user-X / search_posts_all。每次把完整返回原样存成下面的文件。")
    for q in cfg["queries"]:
        args = {"query": q["query"], "start_time": start, "sort_order": q.get("sort_order", "recency"), **cfg["common_args"]}
        print(f"\n## {q['id']}（{q['label']}）→ 存到 data/x/inbox/{day}/{q['id']}.json")
        print(json.dumps(args, ensure_ascii=False))


def ingest(files):
    cfg = load_json(XCFG, {})
    qcfg = {q["id"]: q for q in cfg.get("queries", [])}
    blocked = {x["username"].lower() for x in cfg.get("excluded", [])}
    store = load_json(RAW, {"items": {}, "title_keys": {}})
    state = load_json(STATE, {})
    now = datetime.now(timezone.utc)
    now_s = now_cst().isoformat(timespec="seconds")
    tot = {"files": 0, "posts": 0, "matched": 0, "new_pending": 0, "new_archived": 0}
    per_q = {}
    for f in files:
        qid = os.path.splitext(os.path.basename(f))[0]
        q = qcfg.get(qid, {"filter": True, "label": qid})
        try:
            resp = json.load(open(f))
        except Exception as e:  # noqa
            print(f"[{qid}] 读不了：{e}"); continue
        if isinstance(resp, dict) and "data" not in resp and "errors" in resp:
            print(f"[{qid}] 连接器返回错误：{str(resp['errors'])[:200]}"); continue
        users = {u["id"]: u for u in (resp.get("includes", {}) or {}).get("users", [])}
        posts = resp.get("data") or []
        tot["files"] += 1
        tot["posts"] += len(posts)
        n_m = n_p = 0
        for p in posts:
            u = users.get(p.get("author_id"), {})
            uname = u.get("username") or ""
            if uname.lower() in blocked:
                continue
            text = (p.get("text") or "").strip()
            links = [x.get("unwound_url") or x.get("expanded_url") for x in (p.get("entities", {}) or {}).get("urls", [])
                     if x.get("expanded_url") and not re.search(r"x\.com/.+/(photo|video)/", x.get("expanded_url", ""))]
            link_titles = " ".join(x.get("title", "") for x in (p.get("entities", {}) or {}).get("urls", []))
            if q.get("filter", True) and not fetch.EARTH_RE.search(f"{text} {link_titles}"):
                continue
            n_m += 1
            url = p.get("url") or f"https://x.com/{uname or 'i'}/status/{p['id']}"
            iid = hashlib.sha1(fetch.canon_url(url).encode()).hexdigest()[:12]
            clean = re.sub(r"https://t\.co/\S+", "", text).strip()
            first = clean.split("\n")[0].strip() or clean
            title = (first[:80] + "…") if len(first) > 80 else first
            tk = fetch.title_key(clean[:120])
            if iid in store["items"] or (tk and tk in store["title_keys"]):
                continue
            pub = fetch.parse_date(p.get("created_at"))
            status = "pending" if pub and (now - pub) <= timedelta(hours=fetch.FRESH_HOURS) else "archived"
            snippet = clean[:600] + (("  链接：" + " ".join(links[:3])) if links else "")
            rec = {"id": iid, "title": title, "url": url, "source_id": "x", "source_name": f"X · @{uname}（{q.get('label', qid)}）",
                   "tier": "T2", "lang": p.get("lang", ""), "aspect": "社交媒体", "publisher": u.get("name", ""),
                   "published_at": pub.isoformat() if pub else None, "first_seen": now_s, "snippet": snippet, "status": status,
                   "x_query": qid, "x_metrics": p.get("public_metrics", {})}
            store["items"][iid] = rec
            if tk:
                store["title_keys"][tk] = iid
            if status == "pending":
                n_p += 1; tot["new_pending"] += 1
            else:
                tot["new_archived"] += 1
        tot["matched"] += n_m
        per_q[qid] = {"posts": len(posts), "matched": n_m, "new_pending": n_p}
        print(f"[{qid}] 帖子 {len(posts)}，命中 {n_m}，新进待审 {n_p}")
    save_json(RAW, store)
    prev = state.get("x", {})
    state["x"] = {"last_run": now_s, "ok": tot["files"] > 0, "last_ok": now_s if tot["files"] else prev.get("last_ok"),
                  "entries": tot["posts"], "matched": tot["matched"], "new_pending": tot["new_pending"], "queries": per_q,
                  "posts_read_total": prev.get("posts_read_total", 0) + tot["posts"],
                  "total_collected": sum(1 for r in store["items"].values() if r["source_id"] == "x")}
    save_json(STATE, state)
    fetch.write_pending(store)
    print(json.dumps(tot, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--plan":
        plan()
    elif len(sys.argv) > 1:
        fs = [f for a in sys.argv[1:] for f in glob.glob(a)]
        ingest(fs)
    else:
        print(__doc__)
