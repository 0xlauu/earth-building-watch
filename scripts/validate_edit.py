#!/usr/bin/env python3
"""检查编辑写的 data/edited/YYYY-MM-DD.json 是否符合 EDITOR.md 的约定。

用法：python3 scripts/validate_edit.py data/edited/2026-10-07.json [--allow-partial]
不通过时退出码为 1，并列出每个问题。通过后才能 build。
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa

DROP_REASONS = {"irrelevant", "old", "unverified", "noise", "low_score", "duplicate"}
LIMITS = {"title_zh": 36, "summary_pick": 140, "summary_brief": 100, "for_you": 60, "lead": 120, "action": 50}


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
