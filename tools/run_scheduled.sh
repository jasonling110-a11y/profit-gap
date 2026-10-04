#!/bin/sh
# 利润断层 · 定时扫描包装脚本（供 macOS launchd 调用）
#
# 目的：让扫描**不再依赖 WorkBuddy 是否在线**。只要 Mac 开机且已登录，
#       launchd 就会在 22:00 触发；睡眠错过会在唤醒后补跑；开机也会补跑一次。
#
# 为什么用 /bin/sh 而不是 zsh：
#   launchd 不会加载 ~/.zshrc（非交互环境），PATH / 别名 / 插件全都没有。
#   本脚本因此不依赖任何 shell 配置，所有命令走绝对路径。
#
# 幂等与防抖：真正的判断在 tools/sched_guard.py 里（盘中不跑 / 数据已最新 / 刚刚跑过）。
# 退出码：0 = 正常（含「跳过」）；非 0 = 扫描侧问题，会写进日志。
set -u

DIR="/Users/jason/Desktop/利润断层"
PY="/Users/jason/.workbuddy/binaries/python/envs/default/bin/python"
LOGDIR="$DIR/data/logs"
LOG="$LOGDIR/scheduler.log"
LOCK="$DIR/data/.scheduler.lock"

# launchd 环境极简，显式补一个可用 PATH（脚本内仍全部用绝对路径）
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin"

mkdir -p "$LOGDIR" || exit 1

ts() { date "+%Y-%m-%d %H:%M:%S"; }
say() { printf "%s  %s\n" "$(ts)" "$*" >> "$LOG"; }

say "---- 触发（launchd）----"

# ---------- 防重入：同一时刻只允许一个实例 ----------
if [ -d "$LOCK" ]; then
  say "已有实例在运行（$LOCK 存在），本次跳过"
  exit 0
fi
mkdir "$LOCK" 2>/dev/null || { say "建锁失败，本次跳过"; exit 0; }
trap 'rmdir "$LOCK" 2>/dev/null' EXIT HUP INT TERM

# ---------- 前置守卫 ----------
GUARD="$("$PY" "$DIR/tools/sched_guard.py" 2>>"$LOG")"
GRC=$?
if [ "$GRC" -ne 0 ]; then
  say "守卫脚本异常（退出码 $GRC），保守起见本次跳过"
  exit 0
fi
say "守卫：$GUARD"
case "$GUARD" in
  RUN*) : ;;
  *)    say "本次不执行"; exit 0 ;;
esac

# ---------- 执行 ----------
cd "$DIR" || { say "无法进入项目目录 $DIR"; exit 1; }
say "开始扫描：./run_daily.sh"
./run_daily.sh >> "$LOG" 2>&1
rc=$?
say "扫描结束，退出码 $rc"

# 失败重试一次（网络抖动 / 数据源瞬时不可用）
if [ "$rc" -ne 0 ]; then
  say "退出码 $rc ≠ 0，5 分钟后重试一次"
  sleep 300
  ./run_daily.sh >> "$LOG" 2>&1
  rc=$?
  say "重试结束，退出码 $rc"
fi

if [ "$rc" -eq 0 ]; then
  say "✔ 本次完成"
else
  say "⚠ 本次未通过（退出码 $rc）——请查看 $LOG"
fi
exit "$rc"
