#!/usr/bin/env python3
"""利润断层 · 定时扫描前置守卫。

由 tools/run_scheduled.sh 调用（macOS launchd 定时任务）。
只负责回答「这一次触发要不要真的跑」，**不做任何写操作**。

输出一行：
  RUN              正常执行
  SKIP <原因>       跳过（正常情况，退出码仍是 0）

三道闸门（任一命中即 SKIP）：
  1. 盘中不跑   —— 09:15~15:30 之间日 K 还没收盘，用它判跳空会失真；
                   launchd 的「睡醒补跑」很可能正好落在这个区间。
  2. 数据已最新 —— 上次扫描覆盖到的交易日 >= 最近一个已收盘交易日。
                   这一条同时把周末、长假、重复触发全都覆盖了。
                   ⚠️ 但仅当上次扫描**完整通过**时才认；上次有问题（audit.problems 非空）
                      就一律放行，让本次去重试，绝不让一次失败的扫描变成「永久跳过」。
  3. 刚刚跑过   —— 距上次成功扫描不足 RECENT_MINUTES 分钟，判定为重复触发
                   （防与 WorkBuddy 23:00 那条定时任务撞车）。

环境变量 PGB_FORCE=1 可强制放行（仅用于人工验证链路）。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
DATA = os.path.join(ROOT, "data")

RECENT_MINUTES = 30
INTRADAY_FROM = 9 * 60 + 15      # 09:15
INTRADAY_TO = 15 * 60 + 30       # 15:30


def _trading_days() -> list:
    """交易日列表（读引擎的 trade_dates 缓存；读不到时退化为「工作日」）。"""
    try:
        import profit_gap as pg
        s = sorted(pg._trade_day_set())
        if s:
            return s
    except Exception:
        pass
    today = dt.date.today()
    return [today - dt.timedelta(days=i) for i in range(60)
            if (today - dt.timedelta(days=i)).weekday() < 5]


def _read_last() -> tuple:
    """返回 (last_td, generated_at, problems)。任何缺失都返回 None。"""
    try:
        p = json.load(open(os.path.join(DATA, "scan_latest.json"), encoding="utf-8"))
    except Exception:
        return None, None, None
    a = p.get("audit") or {}
    last_td = gen_at = None
    try:
        if a.get("last_trade_date"):
            last_td = dt.date.fromisoformat(a["last_trade_date"])
    except Exception:
        pass
    try:
        if a.get("generated_at"):
            gen_at = dt.datetime.strptime(a["generated_at"], "%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return last_td, gen_at, a.get("problems")


def main() -> int:
    if os.environ.get("PGB_FORCE") == "1":
        print("RUN PGB_FORCE=1 强制放行")
        return 0

    now = dt.datetime.now()
    today = now.date()
    mins = now.hour * 60 + now.minute

    tdays = _trading_days()
    is_td = today in tdays
    last_td, gen_at, problems = _read_last()
    ok_last = (last_td is not None) and not problems

    # ---- 闸门 1：盘中不跑 ----
    if is_td and INTRADAY_FROM <= mins <= INTRADAY_TO:
        print(f"SKIP 当前处于盘中交易时段（{now:%H:%M}），"
              "避免用未收盘的半截日 K 判定跳空；收盘后会自动补跑")
        return 0

    # ---- 闸门 2：数据已最新（上次扫描必须是「完整通过」才算数）----
    completed = [d for d in tdays if d < today or (d == today and mins > INTRADAY_TO)]
    if completed:
        latest = max(completed)
        if ok_last and last_td >= latest:
            print(f"SKIP 数据已是最新（上次扫描已覆盖到 {last_td}，最近已收盘交易日 {latest}）")
            return 0
        if not ok_last and problems:
            print(f"NOTE 上次扫描未通过完整性检查（{'; '.join(problems)[:120]}），"
                  "本次放行以重试")

    # ---- 闸门 3：刚刚跑过 ----
    if gen_at is not None:
        delta = (now - gen_at).total_seconds() / 60
        if 0 <= delta < RECENT_MINUTES:
            print(f"SKIP 距上次成功扫描仅 {delta:.0f} 分钟（< {RECENT_MINUTES} 分钟），判定为重复触发")
            return 0

    print("RUN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
