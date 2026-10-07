"""生土观察：共用的路径、时间和读写工具。"""
import json, os, glob
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(DATA, "raw", "items.json")
STATE = os.path.join(DATA, "fetch-state.json")
PENDING = os.path.join(DATA, "pending.json")
EDITED_DIR = os.path.join(DATA, "edited")
WEEKLY_DIR = os.path.join(DATA, "weekly")
SOURCES = os.path.join(ROOT, "sources.json")
CONFIG = os.path.join(ROOT, "site.config.json")
CST = timezone(timedelta(hours=8))  # Asia/Shanghai

CATEGORIES = [
    # key, 中文名, 权重 (sig, nov, cred, reson, act)，每行和为 10
    ("research", "研究论文", (3, 3, 2, 1, 1)),
    ("project", "项目案例", (2, 2, 1, 3, 2)),
    ("product", "产品与企业", (2, 2, 2, 3, 1)),
    ("standard", "标准与政策", (4, 1, 2, 2, 1)),
    ("event", "活动与赛事", (2, 1, 2, 2, 3)),
    ("market", "行业与市场", (3, 1, 2, 3, 1)),
    ("technique", "工艺与教程", (1, 2, 1, 2, 4)),
    ("heritage", "遗产保护", (3, 2, 2, 2, 1)),
]
CAT_LABEL = {k: l for k, l, _ in CATEGORIES}
CAT_WEIGHTS = {k: w for k, _, w in CATEGORIES}
DIMS = ("sig", "nov", "cred", "reson", "act")
# 精选门槛（加权总分 0-100）。简讯门槛对所有分级相同。
PICK_THRESHOLD = {"T1": 55, "T1_5": 60, "T2": 65}
BRIEF_THRESHOLD = 40
MAX_PICKS_PER_DAY = 12
TIER_LABEL = {"T1": "官方一手", "T1_5": "期刊论文", "T2": "媒体聚合"}


def now_cst():
    return datetime.now(CST)


def today_cst():
    return now_cst().strftime("%Y-%m-%d")


def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, path)


def load_sources():
    return load_json(SOURCES, {"sources": []})["sources"]


def load_editions():
    eds = []
    for p in sorted(glob.glob(os.path.join(EDITED_DIR, "*.json"))):
        eds.append(load_json(p, {}))
    return eds


def edited_ids():
    ids = set()
    for ed in load_editions():
        for it in ed.get("items", []):
            ids.add(it["id"])
            ids.update(it.get("merged_ids", []))
    return ids


def compute_score(cat, scores):
    w = CAT_WEIGHTS[cat]
    return int(sum(int(scores[d]) * w[i] for i, d in enumerate(DIMS)))


def decision_for(score, tier):
    if score >= PICK_THRESHOLD.get(tier, 65):
        return "pick"
    if score >= BRIEF_THRESHOLD:
        return "brief"
    return "drop"
