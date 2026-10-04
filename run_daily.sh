#!/bin/zsh
# 利润断层工作台 · 每日扫描一键脚本
# 用法：
#   ./run_daily.sh              # 默认「按报告期覆盖」窗口（各期用自己的法定披露季）
#   DAYS=30 ./run_daily.sh      # 退回滚动窗口：只扫最近 30 天的公告
#   ./run_daily.sh --min-yoy 30 # 透传参数给扫描引擎
#   SKIP_AUDIT=1 ./run_daily.sh # 跳过数据完整性审计
#
# 注意 1：默认不再传 --days。滚动窗口会把同一个报告期的披露季从中间切断，
#         落在边界前一天的个股会静默掉出（药明康德 603259 / 公告日 2026-08-04 就是这样丢的）。
# 注意 2：财报缓存默认**不复用**（窗口内报告期每次强制重抓）。这是必须的 —— A 股公告绝大多数
#         在盘后 16:00~21:00 发布，若复用当天上午的快照，22:00 的任务会把当天全部盘后公告漏掉。
# 注意 3：扫描发现问题（整期失败 / 候选截断 / 抓取失败率超 1%）时会**以非 0 退出码结束**；
#         本脚本仍会继续重建看板并跑审计，最后把最严重的退出码透传出去，便于定时任务报警。
#         退出码：0 = 全通过；3 = 扫描侧完整性问题；其它 = 脚本自身失败。
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
PY="/Users/jason/.workbuddy/binaries/python/envs/default/bin/python"

cd "$DIR" || exit 1
rc=0

if [ -n "${DAYS:-}" ]; then
  echo "▶ 利润断层扫描（滚动窗口：最近 ${DAYS} 天）"
  "$PY" src/profit_gap.py --days "$DAYS" --workers 5 "$@"
else
  echo "▶ 利润断层扫描（按报告期覆盖，各期按法定披露季）"
  "$PY" src/profit_gap.py --workers 5 "$@"
fi
c=$?; [ "$c" -ne 0 ] && [ "$rc" -eq 0 ] && rc=$c

echo "▶ 刷新工作台看板"
"$PY" src/build_workbench.py
c=$?; [ "$c" -ne 0 ] && [ "$rc" -eq 0 ] && rc=$c

if [ -z "${SKIP_AUDIT:-}" ]; then
  echo "▶ 数据完整性审计"
  "$PY" tools/audit_pipeline.py
  c=$?; [ "$c" -ne 0 ] && [ "$rc" -eq 0 ] && rc=$c
fi

# 聚合页「个人投资工作台」（投资日历 + 利润断层选股平台）。
# 与主看板解耦：日历抓取失败也照样重建页面（问题会显示在页面上的提示条里），
# 不会因为一个可选数据源挂掉就整天不产出首页。
echo "▶ 抓取投资日历事件"
"$PY" src/calendar_events.py
c=$?; [ "$c" -ne 0 ] && [ "$rc" -eq 0 ] && rc=$c

echo "▶ 生成聚合页（个人投资工作台）"
"$PY" src/build_home.py
c=$?; [ "$c" -ne 0 ] && [ "$rc" -eq 0 ] && rc=$c

# 站点入口：首页 = 聚合页，完整看板另存 ASCII 别名。与云端 workflow 保持一致。
cp -f 个人投资工作台.html index.html 2>/dev/null
cp -f 利润断层工作台.html dashboard.html 2>/dev/null

# 产物校验：退出码为 0 不等于页面有内容（数据源整批为空也能「成功」产出空页）
echo "▶ 产物校验"
"$PY" tools/verify_outputs.py
c=$?; [ "$c" -ne 0 ] && [ "$rc" -eq 0 ] && rc=$c

if [ "$rc" -ne 0 ]; then
  echo "⚠ 完成但存在完整性问题：$DIR/个人投资工作台.html（退出码 $rc）"
else
  echo "✔ 完成：$DIR/利润断层工作台.html"
  echo "✔ 完成：$DIR/个人投资工作台.html（站点首页 index.html）"
fi
exit $rc
