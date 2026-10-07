# 生土观察 · Earth Building Watch

全球生土建筑与材料资讯（夯土、生土抹面、土坯、压制土砖、生土遗产）。每天一份中文日报，每周一份周报。

- 网站：https://0xlauu.github.io/earth-building-watch/ （发布后生效）
- 编辑：云端电脑上的 Grok Bot，按 [EDITOR.md](EDITOR.md) 每天审稿。不调用付费模型 API。

## 怎么运作

1. `scripts/fetch.py`：每天 07:00 和 19:00（北京时间）抓取 `sources.json` 里的信源——企业和学会官网 RSS、期刊 RSS、Crossref、5 种语言的 Google 新闻。按网址和标题去重，记录首次见到时间。只有 48 小时内的新条目进入待审队列 `data/pending.json`，旧条目不会再冒出来。
2. 编辑（Grok Bot）读待审队列，按 5 个维度、8 个分类的加权评分表打分，写中文标题、摘要和“对你意味着什么”，结果存到 `data/edited/YYYY-MM-DD.json`。`scripts/validate_edit.py` 负责检查：不许出现原始库里没有的条目，分数和门槛必须对得上。
3. `scripts/build.py` 生成静态网站到 `docs/`（首页、日报、周报、往期、信源），以及 `feed.xml` 和 `latest.json`。
4. `scripts/publish.sh` 提交并推送，GitHub Pages 从 `main` 分支的 `/docs` 目录发布。

只需要 Python 3（标准库），不需要数据库，也不需要 Node。

## 常用命令

```bash
python3 scripts/fetch.py                  # 抓取
python3 scripts/validate_edit.py data/edited/$(date +%F).json
python3 scripts/build.py                  # 生成网站
bash scripts/publish.sh                   # 发布
python3 scripts/status.py                 # 当前状态摘要
bash scripts/ensure-scheduler.sh          # 确认定时抓取在运行
```

## 致谢

本项目的方法参考了开源项目 [AIHOT](https://github.com/KKKKhazix/AIHOT)（MIT 许可）：
信源分级、首次见到时间去重、多维加权评分、精选门槛、日报和周报结构。
本项目没有使用 AIHOT 的代码、名称或标志；抓取、编辑流程和网站都是重新写的，并改成了生土领域。

## 许可

代码：MIT（见 LICENSE）。摘要链接到原文，原文版权归原作者和出版方。
