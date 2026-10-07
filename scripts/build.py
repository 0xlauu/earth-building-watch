#!/usr/bin/env python3
"""生土观察：把 data/edited/*.json 生成静态网站到 docs/（GitHub Pages 从 main 分支的 /docs 发布）。

用法：python3 scripts/build.py
同时：刷新 data/pending.json（去掉已编辑的条目），写 docs/latest.json 给汇报机器人，
写 out/standalone/home.html（把 CSS 内联的单文件首页，可以直接拷到桌面打开）。
"""
import html, json, os, re, shutil, sys
from collections import Counter, defaultdict
from datetime import date as Date, datetime
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa
import fetch  # noqa  用它的 write_pending

DOCS = os.path.join(ROOT, "docs")
OUT = os.path.join(ROOT, "out", "standalone")
CFG = load_json(CONFIG, {})
NAME, NAME_EN = CFG.get("name", "生土观察"), CFG.get("name_en", "Earth Building Watch")
E = lambda s: html.escape(str(s or ""), quote=True)


def cst_date(iso):
    if not iso:
        return ""
    d = datetime.fromisoformat(iso).astimezone(CST)
    return f"{d.month}月{d.day}日" + ("" if d.year == now_cst().year else f"（{d.year}）")


def week_of(ds):
    y, w, _ = Date.fromisoformat(ds).isocalendar()
    return f"{y}-W{w:02d}"


def week_range(wk):
    y, w = wk.split("-W")
    a = Date.fromisocalendar(int(y), int(w), 1)
    b = Date.fromisocalendar(int(y), int(w), 7)
    return f"{a.month}月{a.day}日到{b.month}月{b.day}日"


def page(title, body, active, depth=0, desc=""):
    up = "../" * depth
    nav = [("index.html", "今日", "home"), ("daily/index.html", "日报", "daily"), ("weekly/index.html", "周报", "weekly"),
           ("archive.html", "往期", "archive"), ("sources.html", "信源", "sources")]
    links = "".join(f'<a href="{up}{h}" class="{"is-active" if k == active else ""}">{t}</a>' for h, t, k in nav)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc or CFG.get('tagline',''))}">
<link rel="stylesheet" href="{up}assets/tokens.css">
<link rel="stylesheet" href="{up}assets/site.css">
<link rel="alternate" type="application/rss+xml" title="{E(NAME)}" href="{up}feed.xml">
</head>
<body class="fd">
<header class="ebw-top"><div class="ebw-top-in">
<a class="ebw-brand" href="{up}index.html">{E(NAME)} <small>{E(NAME_EN)}</small></a>
<nav class="ebw-nav">{links}</nav>
</div></header>
<main class="ebw-main">
{body}
</main>
<footer class="ebw-foot"><p>{E(NAME)}只放中文摘要和原文链接，版权归原作者。编辑流程借鉴开源项目 <a href="https://github.com/KKKKhazix/AIHOT">AIHOT</a>（MIT）的方法。<a href="{up}sources.html">信源与方法</a> · <a href="{up}feed.xml">RSS</a></p></footer>
<script>
document.querySelectorAll('.ebw-filters').forEach(function(bar){{
  bar.addEventListener('click', function(e){{
    var b = e.target.closest('button'); if(!b) return;
    bar.querySelectorAll('button').forEach(function(x){{x.classList.toggle('is-on', x===b);}});
    var c = b.dataset.cat;
    document.querySelectorAll('[data-cat]').forEach(function(el){{
      if (el.tagName === 'BUTTON') return;
      el.classList.toggle('ebw-hidden', c !== 'all' && el.dataset.cat !== c);
    }});
  }});
}});
</script>
</body>
</html>
"""


def enrich(ed, raw):
    out = []
    for it in ed.get("items", []):
        if it.get("decision") not in ("pick", "brief"):
            continue
        r = raw.get(it["id"], {})
        out.append({**it, "url": it.get("url_override") or r.get("url"), "orig_title": r.get("title"), "source_name": r.get("source_name"),
                    "publisher": r.get("publisher"), "tier": r.get("tier"), "published_at": r.get("published_at"),
                    "first_seen": r.get("first_seen"), "date": ed["date"]})
    out.sort(key=lambda x: (x["decision"] != "pick", -x.get("score", 0)))
    return out


def src_line(it):
    pub = it.get("publisher") or ""
    src = it.get("source_name") or ""
    who = pub if (pub and src.startswith("Google")) else src
    return f'{E(who)} · {E(TIER_LABEL.get(it.get("tier"), ""))} · {E(cst_date(it.get("published_at")))}'


def card(it):
    fy = f'<p class="ebw-foryou"><b>对你</b>{E(it["for_you"])}</p>' if it.get("for_you") else ""
    return f"""<article class="ebw-card" data-cat="{it['category']}">
<div class="ebw-meta"><span class="ebw-cat">{E(CAT_LABEL[it['category']])}</span><span>{src_line(it)}</span><span class="ebw-score" title="加权总分 0-100">{it.get('score','')}</span></div>
<h3><a href="{E(it['url'])}" target="_blank" rel="noopener">{E(it['title_zh'])}</a></h3>
<p class="ebw-sum">{E(it['summary_zh'])}</p>
{fy}
<p class="ebw-orig">原题：{E(it.get('orig_title'))}</p>
</article>"""


def brief_li(it):
    fy = f' 对你：{E(it["for_you"])}' if it.get("for_you") else ""
    return f"""<li data-cat="{it['category']}"><a class="ebw-bt" href="{E(it['url'])}" target="_blank" rel="noopener">{E(it['title_zh'])}</a>
<p>{E(it['summary_zh'])}{fy}</p>
<div class="ebw-meta"><span class="ebw-cat">{E(CAT_LABEL[it['category']])}</span><span>{src_line(it)}</span><span class="ebw-score">{it.get('score','')}</span></div></li>"""


def filters(items):
    cnt = Counter(i["category"] for i in items)
    bs = [f'<button class="is-on" data-cat="all">全部<span>{len(items)}</span></button>']
    bs += [f'<button data-cat="{k}">{l}<span>{cnt[k]}</span></button>' for k, l, _ in CATEGORIES if cnt[k]]
    return f'<div class="ebw-filters" role="toolbar" aria-label="按分类筛选">{"".join(bs)}</div>'


def dropped_summary(ed):
    c = Counter(it.get("drop_reason") for it in ed.get("items", []) if it.get("decision") == "drop")
    names = {"irrelevant": "和生土无关", "old": "旧文重推", "unverified": "无法核实", "noise": "垃圾信息", "low_score": "分数不够", "duplicate": "重复"}
    parts = [f"{names.get(k, k)} {v} 条" for k, v in c.most_common()]
    return "没收的：" + "，".join(parts) + "。" if parts else ""


def edition_body(ed, items, depth, home=False):
    picks = [i for i in items if i["decision"] == "pick"]
    briefs = [i for i in items if i["decision"] == "brief"]
    n_all = len(ed.get("items", []))
    d = Date.fromisoformat(ed["date"])
    up = "../" * depth
    head = f"""<section class="ebw-hero">
<p class="ebw-kicker">{d.year} 年 {d.month} 月 {d.day} 日 · {'今日精选' if home else '日报'}</p>
<h1>{E(picks[0]['title_zh']) if (home and picks) else E(f'{NAME}日报 · {d.month}月{d.day}日')}</h1>
<p class="ebw-lead">{E(ed.get('lead'))}</p>
<div class="ebw-stats"><span>精选 <b>{len(picks)}</b></span><span>简讯 <b>{len(briefs)}</b></span><span>今天审了 <b>{n_all}</b> 条</span>
<span><a href="{up}daily/{ed['date']}.html">看完整日报</a></span><span><a href="{up}weekly/{week_of(ed['date'])}.html">本周周报</a></span></div>
</section>"""
    acts = ""
    if ed.get("actions"):
        acts = '<section class="ebw-section"><h2>你可以做的事</h2><ul class="ebw-actions">' + "".join(f"<li>{E(a)}</li>" for a in ed["actions"]) + "</ul></section>"
    if home:
        body = head + filters(picks + briefs)
        body += f'<section class="ebw-section"><h2>精选</h2><p class="ebw-note">按加权分从高到低。点标题看原文。</p><div class="ebw-cards">{"".join(card(i) for i in picks)}</div></section>'
        if briefs:
            body += f'<section class="ebw-section"><h2>简讯</h2><p class="ebw-note">值得知道，但不用细读。</p><ul class="ebw-briefs">{"".join(brief_li(i) for i in briefs)}</ul></section>'
        return body + acts
    # 日报：按分类分节
    body = head
    by = defaultdict(list)
    for i in picks + briefs:
        by[i["category"]].append(i)
    secs = []
    for k, l, _ in CATEGORIES:
        if not by[k]:
            continue
        ps = [i for i in by[k] if i["decision"] == "pick"]
        bs = [i for i in by[k] if i["decision"] == "brief"]
        inner = "".join(card(i) for i in ps)
        inner = f'<div class="ebw-cards">{inner}</div>' if inner else ""
        if bs:
            inner += f'<ul class="ebw-briefs">{"".join(brief_li(i) for i in bs)}</ul>'
        secs.append(f'<div class="ebw-catblock"><h3>{l}</h3>{inner}</div>')
    body += f'<section class="ebw-section"><h2>分类看</h2><p class="ebw-note">{E(dropped_summary(ed))}</p>{"".join(secs)}</section>'
    return body + acts


def main():
    raw = load_json(RAW, {"items": {}})["items"]
    eds = [e for e in load_editions() if e.get("date")]
    eds.sort(key=lambda e: e["date"])
    if os.path.exists(DOCS):
        for n in os.listdir(DOCS):
            p = os.path.join(DOCS, n)
            if n in ("CNAME",):
                continue
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    for sub in ("assets", "daily", "weekly"):
        os.makedirs(os.path.join(DOCS, sub), exist_ok=True)
    for f in ("tokens.css", "site.css"):
        shutil.copy(os.path.join(ROOT, "assets", f), os.path.join(DOCS, "assets", f))
    open(os.path.join(DOCS, ".nojekyll"), "w").close()

    all_items = {e["date"]: enrich(e, raw) for e in eds}
    w = lambda rel, s: open(os.path.join(DOCS, rel), "w", encoding="utf-8").write(s)

    # 日报
    for e in eds:
        w(f"daily/{e['date']}.html", page(f"{NAME}日报 {e['date']}", edition_body(e, all_items[e["date"]], 1), "daily", 1, e.get("lead")))
    # 首页
    if eds:
        latest = eds[-1]
        home = edition_body(latest, all_items[latest["date"]], 0, home=True)
    else:
        latest = None
        home = '<section class="ebw-hero"><h1>还没有出刊</h1><p class="ebw-lead">第一期编好后会出现在这里。</p></section>'
    home_html = page(f"{NAME} {NAME_EN}", home, "home", 0)
    w("index.html", home_html)

    # 日报目录、周报
    def rows(list_):
        return "".join(f'<tr><td><a href="{h}">{E(t)}</a></td><td class="ebw-num">{p}</td><td class="ebw-num">{b}</td><td>{E(l)}</td></tr>' for h, t, p, b, l in list_)
    def cnt(e, k):
        return sum(1 for i in e.get("items", []) if i.get("decision") == k)
    drows = [(f"{e['date']}.html", e["date"], cnt(e, "pick"), cnt(e, "brief"), e.get("lead", "")[:60]) for e in reversed(eds)]
    tbl = lambda r, head1: f'<div class="ebw-table"><table><thead><tr><th>{head1}</th><th class="ebw-num">精选</th><th class="ebw-num">简讯</th><th>导语</th></tr></thead><tbody>{r}</tbody></table></div>'
    w("daily/index.html", page(f"日报 · {NAME}", f'<section class="ebw-hero"><h1>日报</h1><p class="ebw-lead">每天一期。一件事只写一条，按分类排。</p></section><section class="ebw-section">{tbl(rows(drows), "日期")}</section>', "daily", 1))

    weeks = defaultdict(list)
    for e in eds:
        weeks[week_of(e["date"])].append(e)
    wrows = []
    for wk in sorted(weeks, reverse=True):
        es = weeks[wk]
        items = [i for e in es for i in all_items[e["date"]]]
        picks = [i for i in items if i["decision"] == "pick"]
        briefs = [i for i in items if i["decision"] == "brief"]
        note = load_json(os.path.join(WEEKLY_DIR, f"{wk}.json"), {})
        lead = note.get("lead") or f"本周共 {len(es)} 期日报，精选 {len(picks)} 条，简讯 {len(briefs)} 条。"
        by = defaultdict(list)
        for i in picks + briefs:
            by[i["category"]].append(i)
        secs = []
        for k, l, _ in CATEGORIES:
            if by[k]:
                ps = sorted([i for i in by[k] if i["decision"] == "pick"], key=lambda x: -x["score"])
                bs = [i for i in by[k] if i["decision"] == "brief"]
                inner = (f'<div class="ebw-cards">{"".join(card(i) for i in ps)}</div>' if ps else "") + (f'<ul class="ebw-briefs">{"".join(brief_li(i) for i in bs)}</ul>' if bs else "")
                secs.append(f'<div class="ebw-catblock"><h3>{l}</h3>{inner}</div>')
        acts = note.get("actions") or []
        act_html = ('<section class="ebw-section"><h2>这周你可以做什么</h2><ul class="ebw-actions">' + "".join(f"<li>{E(a)}</li>" for a in acts) + "</ul></section>") if acts else ""
        days = " · ".join(f'<a href="../daily/{e["date"]}.html">{e["date"][5:]}</a>' for e in es)
        body = f"""<section class="ebw-hero"><p class="ebw-kicker">{wk} · {week_range(wk)}</p><h1>{E(NAME)}周报</h1>
<p class="ebw-lead">{E(lead)}</p><div class="ebw-stats"><span>精选 <b>{len(picks)}</b></span><span>简讯 <b>{len(briefs)}</b></span><span>本周日报：{days}</span></div></section>
{act_html}<section class="ebw-section"><h2>按分类</h2>{"".join(secs)}</section>"""
        w(f"weekly/{wk}.html", page(f"{NAME}周报 {wk}", body, "weekly", 1, lead))
        wrows.append((f"{wk}.html", f"{wk}（{week_range(wk)}）", len(picks), len(briefs), lead[:60]))
    w("weekly/index.html", page(f"周报 · {NAME}", f'<section class="ebw-hero"><h1>周报</h1><p class="ebw-lead">每周一汇总上一周的日报，并写这周可以做的事。</p></section><section class="ebw-section">{tbl(rows(wrows), "周")}</section>', "weekly", 1))

    # 往期
    arch = f'<section class="ebw-hero"><h1>往期</h1><p class="ebw-lead">所有日报和周报。</p></section>'
    arch += f'<section class="ebw-section"><h2>周报</h2>{tbl(rows([("weekly/" + a, b, c, d, e) for a, b, c, d, e in wrows]), "周")}</section>'
    arch += f'<section class="ebw-section"><h2>日报</h2>{tbl(rows([("daily/" + a, b, c, d, e) for a, b, c, d, e in drows]), "日期")}</section>'
    w("archive.html", page(f"往期 · {NAME}", arch, "archive", 0))

    # 信源
    state = load_json(STATE, {})
    srows = ""
    for s in load_sources():
        st = state.get(s["id"], {})
        ok = st.get("ok")
        stat = '<span class="ebw-ok">正常</span>' if ok else ('<span class="ebw-bad">失败</span>' if st else "未抓")
        last = st.get("last_ok") or "—"
        srows += f'<tr><td><a href="{E(s.get("home") or s.get("url"))}" target="_blank" rel="noopener">{E(s["name"])}</a></td><td>{TIER_LABEL[s["tier"]]}</td><td>{E(s["lang"])}</td><td>{E(s.get("aspect"))}</td><td>{"关键词过滤" if s.get("filter") else "全收"}</td><td>{stat}</td><td class="ebw-num">{st.get("total_collected", 0)}</td><td>{E(last[:16].replace("T", " "))}</td></tr>'
    th = "".join(f"<li><b>{l}</b>：份量 {w_[0]}、新信息 {w_[1]}、证据 {w_[2]}、和你相关 {w_[3]}、能马上用 {w_[4]}</li>" for k, l, w_ in CATEGORIES)
    last = state.get("_last_fetch", {})
    sbody = f"""<section class="ebw-hero"><h1>信源与方法</h1><p class="ebw-lead">{len(load_sources())} 个信源，覆盖英、中、法、德、西五种语言。每天抓两次，由编辑 Grok Bot 每天审一次。</p>
<div class="ebw-stats"><span>上次抓取 <b>{E((last.get('at') or '—')[:16].replace('T',' '))}</b></span><span>收录总数 <b>{len(raw)}</b></span></div></section>
<section class="ebw-section"><h2>信源</h2><p class="ebw-note">官方一手：机构、协会、企业官网。期刊论文：期刊和论文库。媒体聚合：建筑媒体和 Google 新闻搜索。</p>
<div class="ebw-table"><table><thead><tr><th>信源</th><th>分级</th><th>语言</th><th>方面</th><th>收法</th><th>状态</th><th class="ebw-num">收录</th><th>最近成功</th></tr></thead><tbody>{srows}</tbody></table></div></section>
<section class="ebw-section ebw-prose"><h2>怎么选稿</h2>
<p>脚本每天 07:00 和 19:00 抓取。第一次见到时已经发布超过 48 小时的资料只归档，不会再冒出来。</p>
<p>编辑逐条看。先剔除和生土无关、旧文重推、无法核实的。再按五个维度打 0 到 10 分，按分类加权，得到 0 到 100 的总分。</p>
<ul class="ebw-actions">{th}</ul>
<p>精选门槛：官方一手 {PICK_THRESHOLD['T1']} 分，期刊论文 {PICK_THRESHOLD['T1_5']} 分，媒体聚合 {PICK_THRESHOLD['T2']} 分。{BRIEF_THRESHOLD} 分以上进简讯。每天精选最多 {MAX_PICKS_PER_DAY} 条。</p>
<p>每条精选都写一句“对你”：它对做夯土、生土抹面、土坯的人意味着什么。</p>
<p>这套做法借鉴了开源项目 <a href="https://github.com/KKKKhazix/AIHOT">AIHOT</a>（MIT 许可）的信源分级、五维加权评分和“旧文不刷屏”规则。本站不是 AIHOT，也不使用它的名字和标志。</p></section>"""
    w("sources.html", page(f"信源与方法 · {NAME}", sbody, "sources", 0))

    # RSS 与 latest.json
    base = CFG.get("base_url", "").rstrip("/") + "/"
    feed_items = [i for d in sorted(all_items, reverse=True) for i in all_items[d] if i["decision"] == "pick"][:50]
    def rfc(ds):
        return datetime.fromisoformat(ds + "T08:00:00+08:00").strftime("%a, %d %b %Y %H:%M:%S +0800")
    rss = "".join(f"<item><title>{E(i['title_zh'])}</title><link>{E(i['url'])}</link><guid isPermaLink=\"false\">{i['id']}</guid><pubDate>{rfc(i['date'])}</pubDate><category>{E(CAT_LABEL[i['category']])}</category><description>{E(i['summary_zh'] + ' 对你：' + (i.get('for_you') or ''))}</description></item>" for i in feed_items)
    w("feed.xml", f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{E(NAME)}</title><link>{E(base)}</link><description>{E(CFG.get("tagline"))}</description><language>zh-CN</language>{rss}</channel></rss>')
    if latest:
        li = all_items[latest["date"]]
        save_json(os.path.join(DOCS, "latest.json"), {
            "date": latest["date"], "lead": latest.get("lead"), "actions": latest.get("actions", []),
            "site": base, "daily_url": f"{base}daily/{latest['date']}.html", "weekly_url": f"{base}weekly/{week_of(latest['date'])}.html",
            "counts": {k: sum(1 for i in latest["items"] if i.get("decision") == k) for k in ("pick", "brief", "drop", "merged")},
            "picks": [{"title": i["title_zh"], "category": CAT_LABEL[i["category"]], "score": i["score"], "for_you": i.get("for_you"), "url": i["url"], "source": i.get("publisher") or i.get("source_name")} for i in li if i["decision"] == "pick"],
            "briefs": [{"title": i["title_zh"], "url": i["url"]} for i in li if i["decision"] == "brief"]})

    # 单文件首页（CSS 内联；站内链接指向线上地址，未发布时去掉站内链接）
    os.makedirs(OUT, exist_ok=True)
    css = open(os.path.join(ROOT, "assets", "tokens.css"), encoding="utf-8").read() + "\n" + open(os.path.join(ROOT, "assets", "site.css"), encoding="utf-8").read()
    sa = home_html.replace('<link rel="stylesheet" href="assets/tokens.css">\n<link rel="stylesheet" href="assets/site.css">', f"<style>\n{css}\n</style>")
    if CFG.get("published"):
        sa = re.sub(r'href="(?!https?:|#)([^"]+)"', lambda m: f'href="{base}{m.group(1)}"', sa)
    else:
        sa = re.sub(r'<a href="(?!https?:)[^"]*"( class="[^"]*")?>(.*?)</a>', r'<span\1>\2</span>', sa)
        sa = re.sub(r'<a class="([^"]*)" href="(?!https?:)[^"]*">(.*?)</a>', r'<span class="\1">\2</span>', sa)
        sa = re.sub(r'<link rel="alternate"[^>]*>', "", sa)
    open(os.path.join(OUT, "home.html"), "w", encoding="utf-8").write(sa)

    fetch.write_pending()
    print(f"已生成 {len(eds)} 期日报、{len(weeks)} 期周报 → docs/；单文件首页 → out/standalone/home.html")


if __name__ == "__main__":
    main()
