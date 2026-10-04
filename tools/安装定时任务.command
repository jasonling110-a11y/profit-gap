#!/bin/zsh
# ============================================================
# 利润断层 · 一键安装「macOS 原生定时任务」（launchd）
#
# 用法：双击本文件即可（或在终端执行 zsh 本文件）。
# 作用：把 tools/com.profit-gap.workbench.daily.plist 安装到
#      ~/Library/LaunchAgents/ 并立即加载，之后每周一~周五 22:00
#      由 macOS 自己触发扫描，**不再需要 WorkBuddy 在线**。
#
# 卸载：双击同目录的「卸载定时任务.command」，或在终端执行
#      launchctl bootout gui/$(id -u)/com.profit-gap.workbench.daily
# ============================================================
set -u

DIR="/Users/jason/Desktop/利润断层"
SRC="$DIR/tools/com.profit-gap.workbench.daily.plist"
DST="$HOME/Library/LaunchAgents/com.profit-gap.workbench.daily.plist"
LABEL="com.profit-gap.workbench.daily"
UIDN="$(id -u)"

echo "============================================"
echo " 利润断层 · 安装 macOS 原生定时任务"
echo "============================================"
echo

if [ ! -f "$SRC" ]; then
  echo "✗ 找不到 plist 源文件：$SRC"
  echo "  请确认项目目录仍在 $DIR"
  echo
  read -r "?按回车键关闭…"
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"
cp -f "$SRC" "$DST" || { echo "✗ 复制 plist 失败"; read -r "?按回车键关闭…"; exit 1; }
chmod 644 "$DST"

if ! plutil -lint "$DST"; then
  echo "✗ plist 语法校验不通过，已中止"
  read -r "?按回车键关闭…"
  exit 1
fi

# 先卸掉旧版本（不存在也无所谓）
launchctl bootout "gui/$UIDN/$LABEL" 2>/dev/null
launchctl bootout "gui/$UIDN" "$DST" 2>/dev/null

echo "→ 正在加载…"
if launchctl bootstrap "gui/$UIDN" "$DST" 2>&1; then
  echo "✔ bootstrap 成功"
else
  echo "… bootstrap 未成功，改用传统 load 方式重试"
  if launchctl load -w "$DST" 2>&1; then
    echo "✔ load 成功"
  else
    echo "✗ 两种方式都失败。"
    echo "  提示：把下面这行贴到「终端」里手动执行，通常就能成功——"
    echo "    launchctl bootstrap gui/$UIDN $DST"
  fi
fi

echo
echo "---------- 当前状态 ----------"
if launchctl print "gui/$UIDN/$LABEL" >/dev/null 2>&1; then
  launchctl print "gui/$UIDN/$LABEL" | grep -E "state|program =|runs =|last exit code|path =" | head -8
  echo
  echo "✔ 定时任务已生效：每周一~周五 22:00 自动扫描"
  echo "  · Mac 睡眠错过 → 唤醒后自动补跑"
  echo "  · 开机/登录 → 自动检查，数据过期才补跑"
  echo "  · 盘中（09:15~15:30）不跑，避免用未收盘的半截日 K"
  echo "  · 日志：$DIR/data/logs/scheduler.log"
else
  echo "✗ 未能在 launchd 中查到该任务"
fi
echo
echo "============================================"
read -r "?按回车键关闭…"
