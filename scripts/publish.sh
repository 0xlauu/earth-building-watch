#!/usr/bin/env bash
# 发布：重新生成网站，提交并推送到 GitHub（Pages 从 main 分支的 /docs 发布）。
# 用法：bash scripts/publish.sh ["提交说明"]
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/build.py
if ! git remote get-url origin >/dev/null 2>&1; then
  echo "还没有配置 GitHub 远程仓库（origin），只在本地生成了 docs/。"; exit 2
fi
git add -A
if git diff --cached --quiet; then echo "没有变化，不用推送"; exit 0; fi
git commit -q -m "${1:-生土观察 $(date +%F) 更新}"
git push -q origin HEAD:main
echo "已推送。网站几分钟后更新：$(python3 -c "import json;print(json.load(open('site.config.json'))['base_url'])")"
