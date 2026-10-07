#!/usr/bin/env bash
# 确认定时抓取还活着：box 重启后 cron 不会自己起来，这个脚本负责拉起。
# 1) cron 没在跑就用 sudo 启动；2) crontab 里没有抓取任务就补上；3) 上次抓取超过 13 小时就马上补抓一次。
set -u
cd "$(dirname "$0")/.." || exit 1
ROOT="$PWD"
LINE="0 7,19 * * * $ROOT/scripts/cron-fetch.sh"
if ! command -v crontab >/dev/null; then
  echo "没有 cron，正在安装"; sudo apt-get install -y -qq cron >/dev/null 2>&1 || { echo "安装 cron 失败"; exit 1; }
fi
pgrep -x cron >/dev/null || { sudo /usr/sbin/cron && echo "已启动 cron"; }
if ! crontab -l 2>/dev/null | grep -qF "$ROOT/scripts/cron-fetch.sh"; then
  (crontab -l 2>/dev/null; echo "CRON_TZ=Asia/Shanghai"; echo "$LINE") | crontab - && echo "已写入 crontab"
fi
LAST=$(python3 -c "import json;print(json.load(open('data/fetch-state.json')).get('_last_fetch',{}).get('at',''))" 2>/dev/null)
AGE=$(python3 - "$LAST" <<'PY'
import sys
from datetime import datetime, timezone
s = sys.argv[1]
print(int((datetime.now(timezone.utc) - datetime.fromisoformat(s)).total_seconds() // 3600) if s else 999)
PY
)
if [ "$AGE" -ge 13 ]; then echo "上次抓取在 $AGE 小时前，现在补抓"; bash scripts/cron-fetch.sh; fi
echo "cron: $(pgrep -x cron >/dev/null && echo 运行中 || echo 未运行) · 上次抓取: ${LAST:-无} · 待审: $(python3 -c "import json;print(json.load(open('data/pending.json'))['count'])")"
