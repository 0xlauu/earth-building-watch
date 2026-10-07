# 生土观察 · 编辑手册（EDITOR.md）

编辑 = 云端电脑上的 Grok Bot。不调外部模型 API。
每天做一次，北京时间 20:00 之后做（19:00 那次抓取已经结束）。
一条规则压过所有规则：**只写原文里有的事实。不编造条目、数字、日期、人名。查不到就丢弃（unverified）。**

---

## 0. 文件约定

| 文件 | 谁写 | 内容 |
|---|---|---|
| `sources.json` | 人 | 自动信源、分级（T1 / T1_5 / T2）、分组 group、关键词过滤。一个信源可有多个地址（urls） |
| `sources_x.json` | 人 | X 账号（已核实）和 4 组搜索。由编辑机器人通过 X 连接器抓 |
| `sources_manual.json` | 人 | 不能自动抓的平台（Instagram、LinkedIn、小红书、公众号、Reddit、Bluesky），靠 Lau 转发 |
| `data/x/inbox/YYYY-MM-DD/*.json` | 编辑 | X 连接器的原样返回（不进 GitHub） |
| `data/raw/items.json` | `fetch.py` | 原始库。每条有 id、首次见到时间 first_seen、状态。去重，旧条目不会再进待审 |
| `data/fetch-state.json` | `fetch.py` | 每个信源上次成功时间、错误、累计条数 |
| `data/pending.json` | `fetch.py` / `build.py` | **编辑读这个**。状态为 pending 且还没被任何编辑文件处理过的条目 |
| `data/edited/YYYY-MM-DD.json` | **编辑写这个** | 当天的审稿结果。日期 = 编辑当天（北京时间） |
| `data/weekly/YYYY-Www.json` | 编辑（每周一） | 周报导语和 3 条行动建议（可选，没有也能生成周报） |
| `docs/` | `build.py` | 网站成品，GitHub Pages 从这里发布。不要手改 |
| `docs/latest.json` | `build.py` | 最新一期的机器可读摘要，汇报机器人读这个 |

原始库里的 url、来源、分级、日期，build 会按 id 自动拼进去。编辑文件只写判断和中文。

## 1. 每日步骤（按顺序，复制粘贴即可）

```bash
cd /workspace/earth-news
bash scripts/ensure-scheduler.sh          # ① 确认 cron 活着；超过 13 小时没抓就先补抓
python3 scripts/fetch.py --pending-only    # ② 刷新待审队列（不联网）
python3 -c "import json;d=json.load(open('data/pending.json'));print(d['count'])"   # ③ 看有几条
```

### 1b. X（每天一次，在 ③ 之后、④ 之前）

定时脚本没有 X 权限，这一步由编辑机器人做。最多 4 次调用，每次最多 10 条，约 0.2 美元/天。

```bash
python3 scripts/x_ingest.py --plan     # 打印今天 4 次调用的完整参数和要存的文件名
```

对 `--plan` 打印的每一组：
1. 调用 X 连接器：namespace `user-X`，工具 `search_posts_all`，参数**原样**用打印出的那行 JSON（不要改 query，不要加大 max_results，不要翻页）。
2. 把返回的 JSON **原样**写进它后面写的文件，例如 `data/x/inbox/2026-10-08/x-people.json`。返回 `{"meta":{"result_count":0}}` 也要存。
3. 某次调用报错：跳过这一组，汇报里写一句“X 第几组失败”。不要重试超过 1 次。

四组都存好后：

```bash
python3 scripts/x_ingest.py "data/x/inbox/$(date +%F)/*.json"   # 导入；自动去重、过滤、写 pending.json
```

不要每天先查 `get_usage_credits`；每周一查一次余额，写进周报汇报。余额低于 2 美元时，只跑 x-people 和 x-platforms 两组。

### 1c. Lau 转发的内容（有就做）

Lau 转发了链接或截图（Instagram、LinkedIn、小红书、公众号等）：
- 打开链接核实内容。打不开、看不到原文，就不收。
- 收的话，在今天的编辑文件里**不能**直接写这条（原始库里没有 id 会被拒）。先追加到原始库：

```bash
python3 scripts/add_manual.py --url "原文链接" --title "原标题" --source "Instagram · @账号" --published 2026-10-08 --snippet "原文要点（照抄，不编）"
```

  它会生成 id，并放进待审队列，然后正常编辑。

④ 读 `data/pending.json` 的每一条（title、snippet、url、source_name、tier、published_at）。
   按第 2-4 节给每一条写一个决定。**每一条都要有决定**，不能漏。
⑤ 写 `data/edited/今天日期.json`（格式见第 5 节）。如果今天的文件已经存在，就把新条目追加进去。
⑥ 检查，再生成网站：

```bash
python3 scripts/validate_edit.py data/edited/$(date +%F).json   # 必须显示“通过”
python3 scripts/build.py                                         # 生成 docs/，并把 pending 清零
bash scripts/publish.sh                                          # 推送到 GitHub（还没配好远程就只在本地生成）
python3 scripts/status.py                                        # 打印给汇报机器人用的摘要
```

待审为 0 时：不写编辑文件，不发新一期。汇报“今天没有新内容”。

## 2. 先筛：丢弃的 6 种理由（drop_reason）

按这个顺序判断。命中就丢弃，写一句 `note` 说明。

1. `irrelevant`：和生土建筑、生土材料无关。例：西班牙语 tapial 指“围墙”的社会新闻；中文旅游软文里顺带一句“夯土墙”；灌溉土渠。
2. `old`：原文是旧闻。**Google 新闻会把几年前的 ArchDaily 等旧文章换上新日期推送。** 凡是 T2 的 Google 新闻条目，标题眼熟、或像项目介绍，都要搜一下原文日期（WebSearch 标题）。原文早于 30 天就丢弃，note 写原年份。
3. `duplicate`：同一件事已经在库里或今天有更好的一条。能合并就用 `merged`（第 4 节），不能合并才丢弃。
4. `unverified`：链接打不开、内容只有标题、查不到原文，事实无法确认。
5. `noise`：广告、招聘、目录页、纯转载没有新信息、活动早已结束的回顾。
6. `low_score`：相关但打分低于 40。必须写 scores 和 score。

**社交媒体条目（X、YouTube、Mastodon）注意：**
- 默认可信度 `cred` 不超过 5。帖子只是线索：能找到正式出处（官网、媒体、论文）才给高分，并用 `url_override` 换成正式出处。
- X 关键词搜索噪音大：诗句、旅游照、“on earth. Building…”这类拼接，一律 `irrelevant`。
- YouTube #shorts、品牌花絮、同一账号重复发的同一项目，用 `noise`。
- 無止橋 Wu Zhi Qiao 的视频有时讲乡村实践而不是生土，看内容再判断。
- 同一件事网站和 X 都有：保留网站那条，X 那条 `merged`。

**Crossref 注意：** 它按 DOI 注册时间取，会带出旧论文（例如 2023 年会议论文今年才登记）。不算 old，可以保留，但 summary 里写明原始年份。

## 3. 再打分：5 个维度，每项 0-10 整数

| 维度 | 键 | 问自己 |
|---|---|---|
| 重要性 | `sig` | 对生土行业影响多大？标准、政策、大项目、大企业动作给高分 |
| 新颖度 | `nov` | 是不是第一次出现的做法、材料、数据？老生常谈给低分 |
| 可信度 | `cred` | 一手来源（企业官网、学会、期刊）高；转述、软文低 |
| 相关度 | `reson` | 和做夯土、生土抹面、土坯的材料生意有多近？抹面、夯土、土砖直接相关给 8-10 |
| 可行动 | `act` | 读完能做什么？有日期的展会、能买到的产品、可复制的工艺给高分 |

打分锚点：5 = 普通；7 = 明显好于平均；9-10 = 一年少见。不要全给 6-7，要拉开。

### 8 个分类和权重（sig, nov, cred, reson, act，合计 10）

| 键 | 中文 | 权重 | 放什么 |
|---|---|---|---|
| `research` | 研究论文 | 3,3,2,1,1 | 期刊、会议论文、实验数据 |
| `project` | 项目案例 | 2,2,1,3,2 | 建成或在建的生土建筑 |
| `product` | 产品与企业 | 2,2,2,3,1 | 品牌新品、企业案例、产品应用 |
| `standard` | 标准与政策 | 4,1,2,2,1 | 规范、认证、法规、政府计划 |
| `event` | 活动与赛事 | 2,1,2,2,3 | 展会、讲座、竞赛、会议 |
| `market` | 行业与市场 | 3,1,2,3,1 | 公共采购、融资、行业数据、书籍和舆论 |
| `technique` | 工艺与教程 | 1,2,1,2,4 | 工法、培训、教程 |
| `heritage` | 遗产保护 | 3,2,2,2,1 | 生土遗产修缮、世界遗产、灾损 |

`score = Σ 维度分 × 权重`，满分 100。脚本会复算，写错不通过。

## 4. 决定和门槛

| 分级 | 精选 pick | 简讯 brief | 丢弃 |
|---|---|---|---|
| T1 官方一手 | ≥ 55 | 40-54 | < 40 |
| T1_5 期刊论文 | ≥ 60 | 40-59 | < 40 |
| T2 媒体聚合 | ≥ 65 | 40-64 | < 40 |

- 每天精选最多 **12** 条。超过时，分低的降为简讯，写 `"demoted": "cap"`。
- 按 50-100 条待审调过：正常一天精选 6-12 条（约 10-15%），简讯 15-30 条，其余丢弃。首期 57 条得到精选 8、简讯 17。
- 精选少于 3 条也没关系，**不为凑数抬分**。
- 合并：同一件事有多条报道，选信息最全的一条做主条，`merged_ids` 列出其他 id；其他条各写一条 `{"id":…, "decision":"merged", "merged_into": 主条 id}`。

## 5. 编辑文件格式

```json
{
  "date": "2026-10-07",
  "editor": "Grok Bot",
  "edited_at": "2026-10-07T22:50:50+08:00",
  "lead": "导语，≤120 字。说今天最重要的 2-3 件事。",
  "actions": ["≤50 字的可做事项，1-3 条，要具体到时间或对象"],
  "items": [
    {"id": "bb038d5401c7", "decision": "pick", "category": "event",
     "scores": {"sig": 6, "nov": 6, "cred": 9, "reson": 8, "act": 8}, "score": 76,
     "title_zh": "≤36 字", "summary_zh": "精选 ≤140 字，简讯 ≤100 字",
     "for_you": "≤60 字，精选必填：对做生土材料的你意味着什么",
     "url_override": "可选：核实过的原文网址，替换 Google 新闻跳转链接"},
    {"id": "…", "decision": "brief", "category": "market", "scores": {…}, "score": 62,
     "title_zh": "…", "summary_zh": "…", "merged_ids": ["…"]},
    {"id": "…", "decision": "merged", "merged_into": "…"},
    {"id": "…", "decision": "drop", "drop_reason": "old", "note": "原文 2016 年"}
  ]
}
```

## 6. 中文写法（全局规则）

- 短句。一句一个意思。主动语态。少用形容词。
- 标题写“谁做了什么”。不用“重磅”“震撼”等词。
- 摘要只写原文事实：谁、在哪、做了什么、数字、日期。原文没有的不写。
- 人名、品牌、地名保留原文拼写；第一次出现可加中文说明，如“德国生土建材商 Claytec”。
- `for_you` 从做夯土、生土抹面、土坯材料的角度写一句：能学什么、能卖给谁、要防什么。
- 论文标题前加“论文：”。

## 7. 每周一

- 写 `data/weekly/上周的 ISO 周号.json`：`{"week":"2026-W41","lead":"≤120 字","actions":["…","…","…"]}`。
- ISO 周号：`date -d "7 days ago" +%G-W%V`（周一当天运行）。
- 周报页面由 build 自动汇总当周各期精选。

## 8. 维护

- 某信源连续失败：`python3 scripts/status.py` 会列出来。查 `logs/fetch.log`，修 `sources.json`。
- 新增信源：在 `sources.json` 加一条。第一次只收最近 48 小时的内容，不会灌入旧文。
- 噪音太多：改该信源的 `query`，或打开 `filter: true`（用生土关键词过滤），或加 `exclude_title`（标题正则，命中就不收）。多地址信源可以对单个地址设 `filter`。
- 加 X 账号：先用 X 连接器 `get_users_by_usernames` 核实（看简介、发帖数），再写进 `sources_x.json` 的 accounts，并把它加进 x-people 的 query。不核实不加。
- YouTube 频道：用频道 id 拼 `https://www.youtube.com/feeds/videos.xml?channel_id=UC…`，先抓一次确认有内容。
