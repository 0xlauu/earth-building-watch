#!/usr/bin/env python3
"""检查编辑写的 data/edited/YYYY-MM-DD.json 是否符合 EDITOR.md 的约定。

用法：python3 scripts/validate_edit.py data/edited/2026-10-07.json [--allow-partial]
不通过时退出码为 1，并列出每个问题。通过后才能 build。
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa

DROP_REASONS = {"irrelevant", "old", "unverified", "noise", "low_score", "duplicate"}
LIMITS = {"title_zh": 36, "summary_pick": 140, "summary_brief": 100, "for_you": 60, "lead": 120, "action": 50,
          "body_min": 200, "body_max": 700, "key_fact_k": 12, "key_fact_v": 40, "quote": 80}
SOURCE_READ = {"full", "abstract", "snippet"}
# 2026-10-20 起的新期次：精选缺 body_zh 先警告（过渡两周），旧期次不检查
BODY_FROM = "2026-10-21"


def check_body(it, tag, dec, date, errs, warns):
    """body_zh / key_facts / quotes / source_read。全部可选；有就必须合规。"""
    body = it.get("body_zh")
    sr = it.get("source_read")
    if sr is not None and sr not in SOURCE_READ:
        errs.append(f"{tag} source_read 只能是 {sorted(SOURCE_READ)}")
    if body is None:
        if dec == "pick" and date >= BODY_FROM and sr != "snippet":
            warns.append(f"{tag} 精选建议写 body_zh（打不开原文就写 source_read: \"snippet\"）")
    else:
        if not isinstance(body, str):
            errs.append(f"{tag} body_zh 必须是字符串")
        else:
            n = len(re.sub(r"\s", "", body))
            if not LIMITS["body_min"] <= n <= LIMITS["body_max"]:
                errs.append(f"{tag} body_zh {LIMITS['body_min']}-{LIMITS['body_max']} 字（现在 {n}）")
            ps = [x for x in re.split(r"\n\s*\n", body) if x.strip()]
            if len(ps) < 2:
                errs.append(f"{tag} body_zh 至少 2 段，段间空一行")
            if sr is None:
                errs.append(f"{tag} 写了 body_zh 就必须写 source_read（full/abstract）")
            elif sr == "snippet":
                errs.append(f"{tag} 只看到片段（snippet）不许写 body_zh，只写 summary_zh")
            sents = {x.strip() for x in re.split(r"[。！？]", it.get("summary_zh", "")) if len(x.strip()) >= 12}
            dup = [x for x in sents if x in body]
            if dup:
                errs.append(f"{tag} body_zh 和 summary_zh 有整句重复：{dup[0][:20]}…")
    kf = it.get("key_facts")
    if kf is not None:
        if not isinstance(kf, list) or len(kf) > 6 or any(not isinstance(f, dict) or not f.get("k") or not f.get("v") for f in kf):
            errs.append(f"{tag} key_facts 是最多 6 项的 [{{k, v}}] 列表")
        else:
            for f in kf:
                if len(str(f["k"])) > LIMITS["key_fact_k"] or len(str(f["v"])) > LIMITS["key_fact_v"]:
                    errs.append(f"{tag} key_facts 每项 k ≤{LIMITS['key_fact_k']} 字，v ≤{LIMITS['key_fact_v']} 字：{str(f['k'])[:10]}")
    qs = it.get("quotes")
    if qs is not None:
        if not isinstance(qs, list) or len(qs) > 2 or any(not isinstance(q, dict) or not q.get("text") for q in qs):
            errs.append(f"{tag} quotes 最多 2 条，每条 {{text, lang}}")
        else:
            for q in qs:
                if len(q["text"]) > LIMITS["quote"]:
                    errs.append(f"{tag} 引文每句 ≤{LIMITS['quote']} 字符（现在 {len(q['text'])}）")


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    path = sys.argv[1]
    allow_partial = "--allow-partial" in sys.argv
    ed = load_json(path, None)
    errs, warns = [], []
    if ed is None:
        print("文件不存在"); sys.exit(1)
    raw = load_json(RAW, {"items": {}})["items"]
    date = ed.get("date", "")
    if not re.fullmatch(r"\d{4}-\d\d-\d\d", date) or os.path.basename(path) != f"{date}.json":
        errs.append("date 必须是 YYYY-MM-DD，且和文件名一致")
    if not ed.get("lead") or len(ed["lead"]) > LIMITS["lead"]:
        errs.append(f"lead 必填，不超过 {LIMITS['lead']} 字")
    for a in ed.get("actions", []):
        if len(a) > LIMITS["action"]:
            errs.append(f"actions 每条不超过 {LIMITS['action']} 字：{a[:20]}…")
    items = ed.get("items", [])
    ids = [it.get("id") for it in items]
    if len(ids) != len(set(ids)):
        errs.append("items 里有重复的 id")
    kept = {it["id"] for it in items if it.get("decision") in ("pick", "brief")}
    picks = 0
    for it in items:
        iid = it.get("id")
        tag = f"[{iid}]"
        if iid not in raw:
            errs.append(f"{tag} 不在原始库里（不许编造条目）"); continue
        tier = raw[iid]["tier"]
        dec = it.get("decision")
        if dec not in ("pick", "brief", "drop", "merged"):
            errs.append(f"{tag} decision 只能是 pick/brief/drop/merged"); continue
        if dec == "merged":
            if it.get("merged_into") not in kept:
                errs.append(f"{tag} merged_into 必须指向本文件里的 pick 或 brief")
            continue
        sc = it.get("scores")
        need_scores = dec in ("pick", "brief") or it.get("drop_reason") == "low_score"
        if dec == "drop" and it.get("drop_reason") not in DROP_REASONS:
            errs.append(f"{tag} drop 需要 drop_reason：{sorted(DROP_REASONS)}")
        if need_scores:
            cat = it.get("category")
            if cat not in CAT_WEIGHTS:
                errs.append(f"{tag} category 必须是 {list(CAT_WEIGHTS)}"); continue
            if not isinstance(sc, dict) or any(not isinstance(sc.get(d), int) or not 0 <= sc[d] <= 10 for d in DIMS):
                errs.append(f"{tag} scores 需要 {DIMS} 五项 0-10 整数"); continue
            real = compute_score(cat, sc)
            if it.get("score") != real:
                errs.append(f"{tag} score 应为 {real}（按 {cat} 权重算），写的是 {it.get('score')}")
            should = decision_for(real, tier)
            if dec == "pick" and should != "pick":
                errs.append(f"{tag} {real} 分没到 {tier} 精选门槛 {PICK_THRESHOLD[tier]}")
            if dec == "brief" and should == "drop":
                errs.append(f"{tag} {real} 分低于简讯门槛 {BRIEF_THRESHOLD}")
            if dec == "brief" and should == "pick" and it.get("demoted") != "cap":
                errs.append(f"{tag} {real} 分够精选；要降为简讯，写 demoted: \"cap\"")
            if dec == "drop" and should != "drop":
                errs.append(f"{tag} {real} 分不该是 low_score 丢弃")
        if dec in ("pick", "brief"):
            t = it.get("title_zh", "")
            s = it.get("summary_zh", "")
            if not t or len(t) > LIMITS["title_zh"]:
                errs.append(f"{tag} title_zh 必填，不超过 {LIMITS['title_zh']} 字（现在 {len(t)}）")
            lim = LIMITS["summary_pick"] if dec == "pick" else LIMITS["summary_brief"]
            if not s or len(s) > lim:
                errs.append(f"{tag} summary_zh 必填，不超过 {lim} 字（现在 {len(s)}）")
            fy = it.get("for_you", "")
            if dec == "pick" and not fy:
                errs.append(f"{tag} 精选必须写 for_you")
            if fy and len(fy) > LIMITS["for_you"]:
                errs.append(f"{tag} for_you 不超过 {LIMITS['for_you']} 字（现在 {len(fy)}）")
            uo = it.get("url_override")
            if uo is not None and not str(uo).startswith(("http://", "https://")):
                errs.append(f"{tag} url_override 必须是 http(s) 网址")
            for m in it.get("merged_ids", []):
                if m not in raw:
                    errs.append(f"{tag} merged_ids 里的 {m} 不在原始库")
            check_body(it, tag, dec, date, errs, warns)
        if dec == "pick":
            picks += 1
    if picks > MAX_PICKS_PER_DAY:
        errs.append(f"精选 {picks} 条，超过每天上限 {MAX_PICKS_PER_DAY}，把分低的降为简讯（demoted: cap）")
    pend = {r["id"] for r in load_json(PENDING, {"items": []})["items"]}
    covered = set(ids) | {m for it in items for m in it.get("merged_ids", [])}
    missing = pend - covered
    # 同一天的其他编辑文件已经处理过的不算漏
    if missing and not allow_partial:
        errs.append(f"还有 {len(missing)} 条待审没处理：{sorted(missing)[:8]}…（每条都要给 decision）")
    for e in errs:
        print("✗", e)
    for w in warns:
        print("!", w)
    n = {k: sum(1 for it in items if it.get("decision") == k) for k in ("pick", "brief", "drop", "merged")}
    print(f"{'通过' if not errs else '没通过'}：精选 {n['pick']}，简讯 {n['brief']}，丢弃 {n['drop']}，合并 {n['merged']}")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
