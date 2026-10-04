#!/bin/zsh
# ============================================================
# 利润断层 · 卸载「macOS 原生定时任务」（launchd）
# 用法：双击本文件即可（或在终端执行 zsh 本文件）。
# 卸载后不再由 macOS 自动扫描；WorkBuddy 那条定时任务不受影响。
# ============================================================
set -u

LABEL="com.profit-gap.workbench.daily"
DST="$HOME/Library/LaunchAgents/$LABEL.plist"
UIDN="$(id -u)"

echo "============================================"
echo " 利润断层 · 卸载 macOS 原生定时任务"
echo "============================================"
echo

launchctl bootout "gui/$UIDN/$LABEL" 2>/dev/null && echo "✔ 已从 launchd 卸载" || echo "… 该任务当前未加载"
rm -f "$DST" && echo "✔ 已删除 $DST"

if launchctl print "gui/$UIDN/$LABEL" >/dev/null 2>&1; then
  echo "⚠ 仍能在 launchd 中查到该任务，可能需注销后重新登录才彻底生效"
else
  echo "✔ 确认已移除"
fi
echo
read -r "?按回车键关闭…"
