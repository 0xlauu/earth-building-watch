#!/usr/bin/env bash
# 定时抓取（crontab 每天 07:00、19:00 调用）。只抓取、写待审队列，不调模型、不发布。
set -u
cd "$(dirname "$0")/.." || exit 1
mkdir -p logs
exec 9>logs/fetch.lock
flock -n 9 || { echo "$(date -Is) 上一次抓取还没结束，跳过" >> logs/fetch.log; exit 0; }
{
  echo "===== $(date -Is) 开始抓取"
  /usr/bin/python3 scripts/fetch.py
  echo "===== $(date -Is) 结束，退出码 $?"
} >> logs/fetch.log 2>&1
# 日志只留最后 5000 行
tail -n 5000 logs/fetch.log > logs/fetch.log.tmp && mv logs/fetch.log.tmp logs/fetch.log
