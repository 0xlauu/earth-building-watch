#!/usr/bin/env python3
"""生土观察：抓取信源，判重，写入原始库和待审队列。不调用任何模型，不用付费接口。

用法：python3 scripts/fetch.py [--only 信源id,...] [--bootstrap-days 14]
规则：
- 每条资料按规范化网址的 sha1 判重；同一标题（规范化后）也只收一次。
- 第一次见到时，发布时间在 48 小时内的进入待审（pending），更早的只归档（archived），以后也不会再冒出来。
- 原始库为空时（第一次运行）放宽到 --bootstrap-days 天，作为首期回顾。
- 没有可信发布时间的条目标为 undated，不进待审。
- 待审队列 data/pending.json = 状态为 pending 且还没出现在任何 data/edited/*.json 里的条目。
"""
import argparse, hashlib, html, json, re, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *  # noqa

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36 EarthBuildingWatch/1.0"
FRESH_HOURS = 48
DEFAULT_MAX_NEW = 20

EARTH_RE = re.compile(
    r"rammed[- ]earth|earthen|\badobe (brick|block|house|building|wall|construction|architecture)|\bcob (house|building|wall|construction)"
    r"|compressed (stabili[sz]ed )?earth|stabili[sz]ed earth|\bCSEB\b|earth[- ](building|construction|architecture|plaster|block|brick|wall|mortar|render|floor)"
    r"|clay[- ](plaster|render|building|brick|wall|board)|unfired (clay|earth)|raw earth|soil[- ]based (material|construction)|mud[- ](brick|building|house|plaster|architecture)"
    r"|pis[ée]\b|terre crue|\bbauge\b|torchis|enduits? (de|en|à la) terre|\blehm\w*|stampflehm|lehmputz"
    r"|\btapial\b|tierra (cruda|apisonada|compactada)|construcci[oó]n con tierra|arquitectura de tierra|bahareque|bajareque|\btaipa\b|terra crua"
    r"|夯土|生土|土坯|泥抹|黏土抹|粘土抹|土楼|窑洞",
    re.I,
)


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    last = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read()
        except Exception as e:  # noqa
            last = e
            time.sleep(2)
    raise last


def strip_html(s, limit=600):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def canon_url(u):
    try:
        p = urllib.parse.urlsplit(u.strip())
        q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
        if p.netloc.endswith("news.google.com"):
            q = []
        return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/") or "/", urllib.parse.urlencode(q), ""))
    except Exception:
        return u.strip()


def title_key(t):
    t = re.sub(r"\s+-\s+[^-]{2,60}$", "", t or "")  # Google 新闻标题末尾的“ - 媒体名”
    return re.sub(r"[\W_]+", "", t.lower())[:120]


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = parsedate_to_datetime(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:
        pass
    s2 = s.replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d"):
        try:
            d = datetime.fromisoformat(s2) if fmt is None else datetime.strptime(s[:10], fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d.astimezone(timezone.utc)
        except Exception:
            continue
    # “Wed, 09 Sep 2026 00:00:00 EST” 这类
    m = re.match(r"\w{3}, (\d{1,2}) (\w{3}) (\d{4}) (\d\d):(\d\d):(\d\d) ([A-Z]{3})", s)
    if m:
        offs = {"EST": -5, "EDT": -4, "CST": -6, "PST": -8, "GMT": 0, "UTC": 0}
        try:
            d = datetime.strptime(" ".join(m.groups()[:3]) + " " + ":".join(m.groups()[3:6]), "%d %b %Y %H:%M:%S")
            return (d - timedelta(hours=offs.get(m.group(7), 0))).replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def local(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def child_text(el, name):
    for c in el:
        if local(c.tag) == name:
            return (c.text or "").strip()
    return ""


def parse_feed(body):
    root = ET.fromstring(body.lstrip() if isinstance(body, bytes) else body)
    out = []
    items = [e for e in root.iter() if local(e.tag) in ("item", "entry")]
    for it in items:
        title = strip_html(child_text(it, "title"), 300)
        link = child_text(it, "link")
        if not link:
            for c in it:
                if local(c.tag) == "link" and c.get("href") and c.get("rel", "alternate") == "alternate":
                    link = c.get("href")
                    break
        date = child_text(it, "pubDate") or child_text(it, "published") or child_text(it, "updated") or child_text(it, "date")
        desc = child_text(it, "description") or child_text(it, "summary") or child_text(it, "encoded") or child_text(it, "content")
        publisher = ""
        for c in it:
            if local(c.tag) == "source":
                publisher = (c.text or "").strip()
        cats = [(c.text or "").strip() for c in it if local(c.tag) == "category"]
        out.append({"title": title, "url": link.strip(), "published": date, "snippet": strip_html(desc), "publisher": publisher, "categories": cats})
    return out


def fetch_crossref(src, since_days=14):
    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%d")
    out = []
    for q in src["queries"]:
        url = ("https://api.crossref.org/works?" + urllib.parse.urlencode({
            "query.bibliographic": q, "filter": f"from-created-date:{since},type:journal-article,type:proceedings-article,type:book-chapter",
            "rows": 40, "select": "DOI,title,URL,created,issued,container-title,abstract,author", "mailto": "earth-building-watch@users.noreply.github.com"}))
        status, body = http_get(url)
        for it in json.loads(body)["message"]["items"]:
            title = strip_html((it.get("title") or [""])[0], 300)
            created = it.get("created", {}).get("date-time")
            authors = ", ".join(f"{a.get('family','')}" for a in (it.get("author") or [])[:3])
            out.append({"title": title, "url": it.get("URL") or f"https://doi.org/{it['DOI']}", "published": created,
                        "snippet": strip_html(it.get("abstract", "")), "publisher": "; ".join(it.get("container-title") or []),
                        "authors": authors, "categories": []})
        time.sleep(1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--bootstrap-days", type=int, default=14)
    ap.add_argument("--force-bootstrap", action="store_true", help="补抓首期时用：按 bootstrap 窗口处理")
    args = ap.parse_args()

    store = load_json(RAW, {"items": {}, "title_keys": {}})
    state = load_json(STATE, {})
    bootstrap = len(store["items"]) == 0 or args.force_bootstrap
    window = timedelta(days=args.bootstrap_days) if bootstrap else timedelta(hours=FRESH_HOURS)
    now = datetime.now(timezone.utc)
    now_s = now_cst().isoformat(timespec="seconds")
    only = set(filter(None, args.only.split(",")))
    totals = {"sources": 0, "ok": 0, "seen": 0, "new_pending": 0, "new_archived": 0}

    for src in load_sources():
        if only and src["id"] not in only:
            continue
        if src.get("enabled") is False:
            continue
        totals["sources"] += 1
        st = {"last_run": now_s, "ok": False}
        try:
            if src["kind"] == "crossref":
                entries = fetch_crossref(src)
                st["http"] = 200
            else:
                status, body = http_get(src["url"])
                st["http"] = status
                entries = parse_feed(body)
            first_import = src["id"] not in state or not state[src["id"]].get("ever_ok")
            new_p = new_a = matched = 0
            max_new = src.get("max_new", DEFAULT_MAX_NEW)
            for e in entries:
                if not e["title"] or not e["url"]:
                    continue
                text = f"{e['title']} {e['snippet']} {' '.join(e['categories'])}"
                if src.get("filter") and not EARTH_RE.search(text):
                    continue
                matched += 1
                cu = canon_url(e["url"])
                iid = hashlib.sha1(cu.encode()).hexdigest()[:12]
                tk = title_key(e["title"])
                if iid in store["items"] or (tk and tk in store["title_keys"]):
                    continue
                pub = parse_date(e["published"])
                title = e["title"]
                publisher = e.get("publisher", "")
                if src["id"].startswith("gnews-"):
                    m = re.match(r"^(.*)\s+-\s+([^-]{2,80})$", title)
                    if m:
                        title, publisher = m.group(1).strip(), publisher or m.group(2).strip()
                if pub is None:
                    status_ = "undated"
                elif (now - pub) <= window or pub > now:
                    status_ = "pending"
                else:
                    status_ = "archived"
                # 新信源第一次导入（不是全库首跑）：只收 48 小时内的
                if status_ == "pending" and first_import and not bootstrap and (now - pub) > timedelta(hours=FRESH_HOURS):
                    status_ = "archived"
                if status_ == "pending" and new_p >= max_new:
                    status_ = "overflow"
                rec = {"id": iid, "title": title, "url": e["url"], "source_id": src["id"], "source_name": src["name"],
                       "tier": src["tier"], "lang": src["lang"], "aspect": src.get("aspect", ""), "publisher": publisher,
                       "published_at": pub.isoformat() if pub else None, "first_seen": now_s, "snippet": e["snippet"],
                       "status": status_}
                if e.get("authors"):
                    rec["authors"] = e["authors"]
                store["items"][iid] = rec
                if tk:
                    store["title_keys"][tk] = iid
                if status_ == "pending":
                    new_p += 1
                else:
                    new_a += 1
            st.update(ok=True, ever_ok=True, entries=len(entries), matched=matched, new_pending=new_p, new_archived=new_a)
            totals["ok"] += 1
            totals["seen"] += len(entries)
            totals["new_pending"] += new_p
            totals["new_archived"] += new_a
        except Exception as ex:  # noqa
            st.update(ok=False, error=f"{type(ex).__name__}: {str(ex)[:200]}")
            st["ever_ok"] = state.get(src["id"], {}).get("ever_ok", False)
        prev = state.get(src["id"], {})
        st["total_collected"] = sum(1 for r in store["items"].values() if r["source_id"] == src["id"])
        st["last_ok"] = now_s if st.get("ok") else prev.get("last_ok")
        state[src["id"]] = st
        print(f"[{src['id']}] {'ok' if st.get('ok') else 'FAIL'} entries={st.get('entries','-')} matched={st.get('matched','-')} "
              f"new_pending={st.get('new_pending',0)} new_archived={st.get('new_archived',0)} {st.get('error','')}")

    save_json(RAW, store)
    state["_last_fetch"] = {"at": now_s, "bootstrap": bootstrap, **totals}
    save_json(STATE, state)
    write_pending(store)
    print(json.dumps(state["_last_fetch"], ensure_ascii=False))


def write_pending(store=None):
    store = store or load_json(RAW, {"items": {}})
    done = edited_ids()
    items = [r for r in store["items"].values() if r["status"] == "pending" and r["id"] not in done]
    order = {"T1": 0, "T1_5": 1, "T2": 2}
    items.sort(key=lambda r: (order.get(r["tier"], 3), r.get("published_at") or ""), reverse=False)
    save_json(PENDING, {"generated_at": now_cst().isoformat(timespec="seconds"), "count": len(items), "items": items})
    print(f"pending.json: {len(items)} 条待审")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--pending-only":
        write_pending()
    else:
        main()
