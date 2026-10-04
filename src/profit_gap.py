#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
利润断层扫描引擎
=================
在业绩预告 / 业绩快报 / 正式财报披露期内，每个交易日扫描同时（或单独）出现
「利润断层」（净利润增速断层式跳升）与「价格断层」（公告后跳空缺口）的 A 股个股。

数据源：akshare（东方财富数据中心：预告/快报/报表；新浪：日线行情）
输出：data/scan_YYYYMMDD.json + data/scan_YYYYMMDD.csv + data/历史信号.csv + data/简报_YYYYMMDD.md

用法：
  python3 profit_gap.py                    # 自动报告期 + **按报告期覆盖**的公告窗口（默认）
  python3 profit_gap.py --days 30          # 退回滚动窗口：只扫最近 30 天的公告
  python3 profit_gap.py --period 20260630  # 只扫指定报告期
  python3 profit_gap.py --min-yoy 30       # 放宽增速门槛到 30%
  python3 profit_gap.py --track            # 附带历史信号后续表现跟踪
"""
from __future__ import annotations

import argparse
import csv
import functools
import json
import os
import re
import sys
import time
import datetime as dt
import warnings

warnings.filterwarnings("ignore")

import pandas as pd

try:
    import akshare as ak
except Exception as e:  # pragma: no cover
    print(f"[FATAL] 需要 akshare：{e}")
    sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
for d in (DATA_DIR, CACHE_DIR):
    os.makedirs(d, exist_ok=True)

# ---------------------------------------------------------------- 默认参数
DEFAULTS = dict(
    days=None,            # 公告窗口：None = 按报告期覆盖（v1.14 默认）；给数字则退回滚动 N 天
    min_yoy=None,         # 净利润增速门槛（%）；None = 不设门槛
    min_accel=None,       # 增速加速度门槛（百分点）；None = 不设门槛
                          #   v1.12 起默认 None —— 用户 2026-10-04 明确「不需要这个门槛，
                          #   只要形成断层都列出来」。恢复旧行为传 --min-accel 20。
                          #   注意：利润侧两道门槛都关掉后 profit_gap 恒为 True，
                          #   清单实际由「价格断层」（≥min_gap 且未回补）单独决定。
    min_gap=2.0,          # 跳空高开门槛（%）：公告后首日开盘相对前收
    require_price_gap=True,  # 只保留真正形成有效跳空（≥min_gap）的个股；未跳空的一律剔除
    min_score=0.0,        # 输出评分下限
    boards="主板,创业板,科创板",   # 板块过滤
    exclude_st=True,      # 剔除 ST / *ST
    max_candidates=9000,  # 安全阀：超过此数不做缺口检测（会漏扫，触发时打 [WARN]）
    streak_max=6,         # 「连续断层期数」最多回看的报告期数
    streak_yoy=20.0,      # 判定单期为「断层期」的单季同比门槛（%）
    hist_days=120,        # 阶段一：缺口判定窗口（全部候选都要抓，别调太大）
    kline_days=300,       # 阶段二：K 线最低回溯交易日数（只对最终保留的个股抓）
    hist_days_max=1200,   # K 线回溯上限：连续断层越多的个股最多回溯到这里（约 5 年）
)

# 门槛参数里代表「不设门槛」的写法
GATE_OFF = ("", "off", "none", "no", "-", "不设", "不限", "all", "false")


def parse_gate(v):
    """门槛解析：off/none/不设/不限/- → None（不设门槛）；否则转 float。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().lower()
    if s in GATE_OFF:
        return None
    return float(s)


def gate_text(value, unit: str) -> str:
    """门槛的中文描述，用于页面与简报文案。"""
    return "不设门槛" if value is None else f"≥{value}{unit}"

# 「增速加速」标签的阈值（百分点）。与 min_accel 门槛**故意解耦**：门槛默认已关，
# 但标签要表达「这只确实在加速」这一强信号，不能被稀释成「accel ≥ 0 就贴」。
ACCEL_TAG_PCT = 20.0

ND_KEYWORDS = [
    "投资收益", "处置", "出售", "股权转让", "资产处置", "政府补助", "补助",
    "非经常性", "债务重组", "公允价值", "诉讼", "退税", "坏账", "转回",
    "汇兑", "拆迁", "补偿款", "债务豁免",
]


# ================================================================ 基础工具
def log(msg: str) -> None:
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def board_of(code: str) -> str:
    c = str(code).zfill(6)
    if c.startswith(("600", "601", "603", "605")):
        return "主板"
    if c.startswith(("000", "001", "002", "003")):
        return "主板"
    if c.startswith(("300", "301")):
        return "创业板"
    if c.startswith(("688", "689")):
        return "科创板"
    if c.startswith(("8", "4", "9")):
        return "北交所"
    return "其他"


def sina_symbol(code: str) -> str:
    c = str(code).zfill(6)
    return ("sh" if c.startswith(("6", "9")) else "sz") + c


def to_num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        try:
            if pd.isna(v):
                return None
        except Exception:
            pass
        return float(v)
    s = str(v).strip().replace(",", "").replace("%", "")
    if s in ("", "-", "--", "nan", "None"):
        return None
    try:
        return float(s)
    except Exception:
        return None


# ================================================================ 交易日历
class TradeCalendar:
    def __init__(self):
        self.days: list[dt.date] = []
        path = os.path.join(CACHE_DIR, "trade_dates.csv")
        fresh = False
        if os.path.exists(path):
            age = time.time() - os.path.getmtime(path)
            fresh = age < 7 * 86400
        if fresh:
            try:
                self.days = [dt.date.fromisoformat(x) for x in pd.read_csv(path)["d"]]
            except Exception:
                self.days = []
        if not self.days:
            try:
                df = ak.tool_trade_date_hist_sina()
                self.days = sorted(pd.to_datetime(df["trade_date"]).dt.date.tolist())
                pd.DataFrame({"d": [d.isoformat() for d in self.days]}).to_csv(path, index=False)
            except Exception as e:
                log(f"[WARN] 交易日历获取失败（{e}），退化为工作日近似")
                start = dt.date.today() - dt.timedelta(days=400)
                self.days = []
                d = start
                while d <= dt.date.today() + dt.timedelta(days=30):
                    if d.weekday() < 5:
                        self.days.append(d)
                    d += dt.timedelta(days=1)

    def is_trading(self, d: dt.date) -> bool:
        return d in set(self.days)

    def last_trading_day(self, ref: dt.date | None = None) -> dt.date:
        ref = ref or dt.date.today()
        prior = [d for d in self.days if d <= ref]
        return prior[-1] if prior else ref

    def next_trading_days(self, ref: dt.date, n: int = 5) -> list[dt.date]:
        later = [d for d in self.days if d > ref]
        return later[:n]

    def between(self, a: dt.date, b: dt.date) -> list[dt.date]:
        return [d for d in self.days if a <= d <= b]


# ================================================================ 公告窗口
# 「报告期覆盖」模式（v1.14 默认）：每个报告期用它自己的**法定披露季**做窗口，
# 而不是「今天往前 N 天」。理由见 period_window() 的注释。
_LEGAL_OFFSET = {3: 30, 6: 62, 9: 31, 12: 120}   # 期末 → 法定披露截止：04-30 / 08-31 / 10-31 / 次年04-30

# 公告日「刷新宽限期」（天）。
# 东财业绩报表里的「最新公告日期」会被该公司**后续任何一次公告**刷新，不是该期财报的披露日。
# 实测 yjbb_20260630 有 122 行落在 09-01~09-30（半年报法定截止是 08-31），其中 20 只在主板/创业板。
# 如果拿「公告日 ≤ 法定截止」做硬过滤，这些行会被整个丢掉 —— 不计数、不报错、页面上看不出来。
# 所以在法定截止之后留 45 天宽限：窗口上界 = min(今天, 法定截止 + 45 天)。
# 45 天既覆盖了「8 月底披露、9 月发更正公告」的常见情形，又不会让早已过期的报告期重新变大
# （period_window 的 period 永远是「当前时点相关的最近报告期」，deadline+45 不会跑到很久以后）。
REFRESH_GRACE_DAYS = 45

# 报告期进入「披露季」的起算：期末 + 15 天起，正式财报（强制披露）数据应已开始出现。
# 用于拦截「某个来源整批失败、却被 fetch_* 吞成空表」的静默漏票。
SOURCE_OPEN_DAYS = 15

# 接口级失败登记（fetch_forecast / fetch_flash / fetch_report 在异常时写入）。
# scan() 每轮开始时清空，结束时据此判断「来源整批缺失」。
SOURCE_ERRORS: list[dict] = []


def legal_deadline(period: str) -> dt.date:
    """该报告期的法定披露截止日。"""
    e = _period_end(period)
    return e + dt.timedelta(days=_LEGAL_OFFSET[e.month])


def _window_label(mode: str, days, windows: dict, periods: list[str],
                  grace: int = 0) -> str:
    """给页面/简报用的一句话窗口描述。两边共用，避免各自拼装后口径漂移。

    当某期窗口被刷新宽限延长时如实标出，否则用户看到「半年报 06-10~10-04」会以为是抓错了。
    """
    if mode == "days":
        start = min(a for a, _ in windows.values())
        return f"最近 {days} 天（{start.isoformat()} 起）"
    parts = []
    for p in periods:
        a, b = windows[p]
        dl = legal_deadline(p)
        if grace and b > dl:
            parts.append(f"{period_label(p)} {a.isoformat()}~{dl.isoformat()}"
                         f"（+{grace}天公告日刷新宽限至 {b.isoformat()}）")
        else:
            parts.append(f"{period_label(p)} {a.isoformat()}~{b.isoformat()}")
    return "按报告期覆盖 · " + "；".join(parts)


# 公告窗口下界：默认 = **上一报告期结束日**（back=None），语义是「本期披露季的起点」。
# 也可以用 --window-back N 显式指定「期末 − N 天」。
# ⚠️ 这里曾经硬编码为「期末 − 20 天」，是个静默漏票口：实测 2026 三季报有 8 只主板/创业板
# 个股的三季报预告公告日在 08-25~09-04（早于 期末−20 = 09-10）而被整个丢掉。虽然它们恰好
# 也从半年报窗口进来了（所以当天没造成实际损失），但「恰好」不是保证 —— 改为按上一期末取，
# 不再依赖某个拍出来的常数。
WINDOW_BACK_DAYS = 20        # 仅在显式传 --window-back N 时作为回落默认值


def period_window(period: str, today: dt.date,
                  grace: int = REFRESH_GRACE_DAYS,
                  back: int | None = None) -> tuple[dt.date, dt.date]:
    """报告期覆盖模式的公告窗口 = [期末 − back 天, min(今天, 法定披露截止日 + grace)]。
    back=None（默认）时下界取**上一报告期结束日**，即「本期披露季的起点」。

    **为什么不能用滚动 N 天**：滚动窗口 `today − N` 会把同一个报告期的披露季
    从中间切断，落在边界前一天的个股会**静默掉出**——不计数、不报错、也不进
    任何 dropped 统计，页面上完全看不出来。实测：药明康德 603259 的 2026 半年报
    公告日为 2026-08-04，`--days 60` 在 10-03 还包含它（window_start=08-04），
    10-04 就掉出（window_start=08-05）；而按报告期覆盖时窗口是 [06-10, 08-31]，
    不受「今天是几号」影响。

    上界取 min(今天, 法定截止 + grace)：
      · 不放进未来；
      · grace 用来吸收「最新公告日期被后续公告刷新」——否则 8 月底披露、9 月发过
        更正公告的个股会被判成「公告日在窗口外」而静默丢出（见 REFRESH_GRACE_DAYS）。
    """
    e = _period_end(period)
    if back is None:
        lo = _period_end(prev_period(period))      # 上一报告期结束日
    else:
        lo = e - dt.timedelta(days=max(0, int(back)))
    hi = legal_deadline(period) + dt.timedelta(days=max(0, int(grace or 0)))
    return lo, min(today, hi)


# ================================================================ 报告期推断
def quarter_ends(ref: dt.date) -> list[str]:
    """返回与当前时点相关的最近报告期（YYYYMMDD），最多 3 个。"""
    y, m = ref.year, ref.month
    cands: list[dt.date] = []
    if m <= 3:
        cands = [dt.date(y - 1, 12, 31), dt.date(y - 1, 9, 30)]
    elif m == 4:
        cands = [dt.date(y, 3, 31), dt.date(y - 1, 12, 31)]
    elif m <= 6:
        cands = [dt.date(y, 3, 31), dt.date(y - 1, 12, 31)]
    elif m <= 8:
        cands = [dt.date(y, 6, 30), dt.date(y, 3, 31)]
    elif m <= 10:
        cands = [dt.date(y, 9, 30), dt.date(y, 6, 30)]
    else:
        cands = [dt.date(y, 9, 30), dt.date(y, 12, 31)]
    return [d.strftime("%Y%m%d") for d in cands]


def prev_quarter_end(period: str) -> str | None:
    d = dt.datetime.strptime(period, "%Y%m%d").date()
    q = {3: 31, 6: 30, 9: 30, 12: 31}
    if d.month == 3:
        return None
    return {"6": dt.date(d.year, 3, 31), "9": dt.date(d.year, 6, 30), "12": dt.date(d.year, 9, 30)}[
        str(d.month)
    ].strftime("%Y%m%d")


def year_ago(period: str) -> str:
    d = dt.datetime.strptime(period, "%Y%m%d").date()
    return d.replace(year=d.year - 1).strftime("%Y%m%d")


def prev_period(period: str) -> str:
    """上一个报告期（Q1 的上一期 = 上一年年报）。与 prev_quarter_end 不同，
    本函数对 Q1 也返回一个真实报告期，用于连续期数回溯。"""
    d = dt.datetime.strptime(period, "%Y%m%d").date()
    nxt = {6: (d.year, 3, 31), 9: (d.year, 6, 30), 12: (d.year, 9, 30)}.get(d.month)
    if nxt is None:                      # month == 3 → 上一年 12 月 31 日
        nxt = (d.year - 1, 12, 31)
    return dt.date(*nxt).strftime("%Y%m%d")


def streak_periods(period: str, n: int) -> list[str]:
    """从 period 起往前 n 个报告期（最近在前）。"""
    out = [period]
    for _ in range(max(0, int(n) - 1)):
        out.append(prev_period(out[-1]))
    return out


def streak_needed_periods(period: str, n: int) -> set[str]:
    """算 streak_periods 里每一期的单季同比所需的累计口径报告期。"""
    need: set[str] = set()
    for p in streak_periods(period, n):
        need.add(p)
        pq = prev_quarter_end(p)
        if pq:
            need.add(pq)
        ya = year_ago(p)
        need.add(ya)
        ypq = prev_quarter_end(ya)
        if ypq:
            need.add(ypq)
    return need


def period_label(period: str) -> str:
    d = dt.datetime.strptime(period, "%Y%m%d").date()
    return {3: f"{d.year}年一季报", 6: f"{d.year}年半年报", 9: f"{d.year}年三季报", 12: f"{d.year}年年报"}[d.month]


# ================================================================ 财务数据
# 强制刷新（force=True）时缓存的最短复用时间：约 29 分钟。
# 作用：同一次盘后任务里被重复调用的报告期不会反复打接口，但只要隔了半小时以上就必然重抓。
# 这对「隔夜/隔半天」的场景完全无影响 —— 22:00 的任务绝不会复用当天 10:52 的快照。
FORCE_TTL_DAYS = 0.02


@functools.lru_cache(maxsize=1)
def _trade_day_set() -> frozenset:
    """交易日集合（读 cache/trade_dates.csv，读不到时退化为「工作日」）。

    只为缓存新鲜度判断服务，因此刻意做得极轻：不联网、不构造 TradeCalendar。
    """
    path = os.path.join(CACHE_DIR, "trade_dates.csv")
    try:
        return frozenset(pd.to_datetime(pd.read_csv(path)["d"]).dt.date.tolist())
    except Exception:
        return frozenset()


def _is_trading_day(d: dt.date) -> bool:
    ts = _trade_day_set()
    if ts:
        return d in ts
    return d.weekday() < 5          # 退化：工作日近似（周末必然不是交易日，够用）


def _cache_fresh(path: str, ttl_days: float, same_day: bool = False,
                 after_close: bool = False) -> bool:
    """缓存是否还能用。任一判据不满足即视为过期，强制重抓。

    · ttl_days    —— 常规时效；
    · same_day    —— 必须写于今天，跨日即失效（通用能力，当前财报缓存**未启用**：
                     窗口内报告期的时效性由 `force=True` 保证，历史期数据不会变，
                     强制每日重抓 5 个历史报告期会白花约 55 秒）；
    · after_close —— 行情专用：**仅在今天是交易日时**生效。若缓存写于今天且早于 15:00，
                     那是盘中半成品（当日 K 线未收盘），用它算出的收盘价、跳空、回补全错。
                     非交易日不存在「今日未收盘的 K 线」，此时不应作废缓存（否则每个周末
                     都会白白重抓全市场行情）。
    """
    if not os.path.exists(path):
        return False
    mtime = dt.datetime.fromtimestamp(os.path.getmtime(path))
    now = dt.datetime.now()
    if same_day and mtime.date() != now.date():
        return False
    if (after_close and mtime.date() == now.date() and mtime.hour < 15
            and _is_trading_day(mtime.date())):
        return False
    return (now - mtime).total_seconds() / 86400 < ttl_days


def _cached_df(name: str, loader, ttl_days: float = 1.0, *,
               force: bool = False, same_day: bool = False,
               after_close: bool = False) -> pd.DataFrame:
    path = os.path.join(CACHE_DIR, f"{name}.csv")
    eff_ttl = min(ttl_days, FORCE_TTL_DAYS) if force else ttl_days
    if _cache_fresh(path, eff_ttl, same_day, after_close):
        try:
            return pd.read_csv(path, dtype={"股票代码": str})
        except Exception:
            pass
    df = loader()
    if df is not None and len(df):
        try:
            df.to_csv(path, index=False)
        except Exception:
            pass
    return df


def fetch_forecast(period: str, force: bool = False) -> pd.DataFrame:
    """业绩预告（东财）"""
    try:
        return _cached_df(f"yjyg_{period}", lambda: ak.stock_yjyg_em(date=period),
                          ttl_days=0.5, force=force)
    except Exception as e:
        SOURCE_ERRORS.append({"source": "业绩预告", "period": period, "error": str(e)[:200]})
        log(f"[WARN] 业绩预告 {period} 获取失败：{e}")
        return pd.DataFrame()


def fetch_flash(period: str, force: bool = False) -> pd.DataFrame:
    """业绩快报（东财）"""
    try:
        return _cached_df(f"yjkb_{period}", lambda: ak.stock_yjkb_em(date=period),
                          ttl_days=0.5, force=force)
    except Exception as e:
        SOURCE_ERRORS.append({"source": "业绩快报", "period": period, "error": str(e)[:200]})
        log(f"[WARN] 业绩快报 {period} 获取失败：{e}")
        return pd.DataFrame()


def fetch_report(period: str, force: bool = False) -> pd.DataFrame:
    """业绩报表（正式财报，累计口径）"""
    try:
        return _cached_df(f"yjbb_{period}", lambda: ak.stock_yjbb_em(date=period),
                          ttl_days=0.5, force=force)
    except Exception as e:
        SOURCE_ERRORS.append({"source": "正式财报", "period": period, "error": str(e)[:200]})
        log(f"[WARN] 业绩报表 {period} 获取失败：{e}")
        return pd.DataFrame()


def safe_text(v) -> str:
    """pandas 缺失值（NaN / None / NaT）统一转成空串。

    直接 str(NaN) 会写出字面量 "nan"（而且 `nan or ""` 仍然是 nan，因为 nan 是「真值」），
    预告的「业绩变动原因」字段经常为空，不处理就会把 nan 一路带到 CSV / 页面 / 简报里。
    """
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    return str(v).strip()


def cum_profit_map(period: str, force: bool = False) -> dict:
    """{code: {'np': 累计净利润, 'yoy': 累计同比, 'ann': 公告日}}"""
    df = fetch_report(period, force=force)
    out = {}
    if df is None or not len(df):
        return out
    npc = next((c for c in df.columns if c.startswith("净利润-净利润") or c == "净利润-净利润"), None)
    yc = next((c for c in df.columns if c.startswith("净利润-同比增长")), None)
    ac = next((c for c in df.columns if "公告日期" in c), None)
    for _, r in df.iterrows():
        code = str(r.get("股票代码", "")).zfill(6)
        if not code.isdigit():
            continue
        out[code] = {
            "np": to_num(r.get(npc)) if npc else None,
            "yoy": to_num(r.get(yc)) if yc else None,
            "ann": safe_text(r.get(ac))[:10] or None,
            "name": safe_text(r.get("股票简称")),
            "industry": safe_text(r.get("所处行业")),
        }
    return out


def single_quarter(code: str, period: str, cmaps: dict) -> tuple[float | None, float | None, float | None]:
    """(单季净利润, 单季同比增速%, 上年同期单季净利)；数据不足返回 None"""
    def cum(p):
        return (cmaps.get(p, {}).get(code) or {}).get("np")

    pq = prev_quarter_end(period)
    cur = cum(period)
    if cur is None:
        return None, None, None
    prev = cum(pq) if pq else 0.0
    if prev is None:
        return None, None, None
    sq = cur - prev

    y_ago = year_ago(period)
    y_pq = prev_quarter_end(y_ago)
    y_cur = cum(y_ago)
    if y_cur is None:
        return sq, None, None
    y_prev = cum(y_pq) if y_pq else 0.0
    if y_prev is None:
        return sq, None, None
    y_sq = y_cur - y_prev
    if y_sq is None or y_sq <= 0:
        return sq, None, y_sq
    return sq, (sq / y_sq - 1) * 100, y_sq


def compute_streak(code: str, period: str, cmaps: dict, max_n: int, min_yoy: float):
    """连续断层期数：从最近报告期往前，单季同比 ≥ min_yoy 且单季盈利的连续期数。

    口径与页面「增速%」一致，均为单季同比（本季累计 − 上季累计，再与去年同期单季比）。
    取数规则：
      · 该期财报缺失（含上年同期单季为负、同比不可比）→ 不计数也不中断，但连续缺 2 期即停止回溯；
      · 该期单季同比 < min_yoy 或单季亏损 → 断层中断，停止回溯。
    返回 (连续期数, 明细列表, 起始期中文名)。明细最近在前，供页面悬浮/弹窗展示。
    """
    streak, series, missing_run = 0, [], 0
    for p in streak_periods(period, max_n):
        sq, yoy, _ = single_quarter(code, p, cmaps)
        if sq is None or yoy is None:
            missing_run += 1
            if missing_run >= 2:
                break
            continue
        missing_run = 0
        hit = bool(sq > 0 and yoy >= min_yoy)
        series.append({
            "period": p, "label": period_label(p),
            "yoy": round(yoy, 1), "np": round(sq, 0), "hit": hit,
            # 该期公告日（东财「最新公告日期」）—— K 线图上要按期标出历史上的断层
            "ann": (cmaps.get(p, {}).get(code) or {}).get("ann"),
        })
        if hit:
            streak += 1
        else:
            break
    return streak, series, (series[0]["label"] if series else None)


def kline_days_for(hit_periods: list[str], last_td: dt.date, base: int, cap: int) -> int:
    """按连续断层起点推算该股需要的 K 线回溯交易日数。

    连续断层期数越多，最早那一期的公告离现在越远，K 线就必须拉得越长，
    否则用户在弹窗里看不到断层是怎么起步的。做法：
      取最早命中报告期 → 后移 30 个自然日近似公告日 → 换算为交易日 →
      再加 90 个交易日的前置缓冲（用于观察跳空前的形态）。
    base 为下限（所有个股至少给这么多），cap 为上限（防止次新/长历史股票把 payload 撑爆）。
    """
    if not hit_periods:
        return base
    try:
        first = dt.datetime.strptime(min(hit_periods), "%Y%m%d").date()
    except Exception:
        return base
    anchor = first + dt.timedelta(days=30)
    natural = (last_td - anchor).days
    if natural <= 0:
        return base
    approx = int(natural / 1.45) + 90      # 1.45 ≈ 每年自然日/交易日之比
    return max(base, min(approx, cap))


# ================================================================ 行情与缺口
# 行情缺失的两种哨兵，**都不能与「没有跳空（None）」混用**：
#   · FETCH_FAILED —— 网络/接口异常，个股可能本有跳空却被漏掉 → 要重试、要告警；
#   · NO_QUOTE     —— 数据源明确没有该股行情（未上市 / 长期停牌）→ 不可交易，非漏票。
# v1.15 之前两者与「确实没跳空」共用同一个 None，于是抓取失败被静默计入
# 「已剔除未跳空」，真漏无痕。
FETCH_FAILED = {"__fetch_failed__": True}
NO_QUOTE = {"__no_quote__": True}


def _gap_worker(payload: tuple) -> dict:
    """阶段一子进程任务：批量抓行情 → 只检测「最新一次公告」的跳空缺口。

    items: [(code, ann_iso, period, ann_suspect), ...]
      ann_suspect=True 表示东财「最新公告日期」晚于该期法定披露截止日，几乎肯定被后续
      公告刷新过，不能直接当锚点 → 改在该期业绩季内按跳空反推（gap_anchor）。

    全部候选都要跑这一步（可达数千只），所以窗口固定为基准天数，不生成 K 线，
    尽量轻；真正给页面看的长历史 K 线由 `_kline_worker` 只对最终保留的个股补抓。
    进程隔离是硬要求：新浪接口底层 mini-racer(V8) 多线程会崩。
    """
    items, last_td, days, min_gap = payload
    out: dict[str, dict] = {}
    for code, ann_iso, period, suspect in items:
        try:
            ann = dt.date.fromisoformat(ann_iso)
            start = ann - dt.timedelta(days=60)
            if (last_td - start).days < days * 1.6:
                start = last_td - dt.timedelta(days=int(days * 1.6))
            df, reason = None, ""
            for attempt in range(3):        # 一次网络抖动不该让一只个股从清单里消失
                df, reason = fetch_daily_ex(code, start, last_td + dt.timedelta(days=1))
                if df is not None and len(df):
                    break
                if reason == "no_quote":
                    break                    # 数据源明确没有该股行情，重试无意义
                time.sleep(0.25 * (attempt + 1))
            if df is None or not len(df):
                out[code] = dict(NO_QUOTE if reason == "no_quote" else FETCH_FAILED)
                continue
            if suspect:
                anchor, inferred = gap_anchor(df, period, None, min_gap)
            else:
                anchor, inferred = ann, False
            g = detect_gap(df, anchor, last_td) if anchor else None
            if g is not None:
                g["anchor_date"] = anchor.isoformat()
                g["anchor_inferred"] = bool(inferred)
            out[code] = g
        except Exception:
            out[code] = dict(FETCH_FAILED)
    return out


# 各报告期的典型公告滞后（自然日）：既拿不到可信公告日、窗口内又没有有效跳空时的兜底锚点。
# 经验值贴近现实：年报次年 4 月中、一季报 4 月底、半年报 8 月下旬、三季报 10 月底。
_TYPICAL_LAG = {"1231": 105, "0331": 28, "0630": 55, "0930": 27}
# 反推锚点时的搜索窗口：以典型公告日为中心的前后偏移（自然日）。
# 前松后紧 —— 业绩预告 / 快报常常早于正式财报，而正式财报极少晚于典型日一个月。
_ANCHOR_BEFORE, _ANCHOR_AFTER = 45, 30


def _period_end(period: str) -> dt.date:
    p = str(period)
    return dt.date(int(p[:4]), int(p[4:6]), int(p[6:8]))


def _period_bounds(period: str) -> tuple[dt.date, dt.date]:
    """某报告期「公告日」的合理区间 [期末 − 20 天, 期末 + 200 天]。

    法定披露截止其实更紧（年报/一季报 4-30、半年报 8-31、三季报 10-31），
    这里故意放宽，以容纳次新股随招股书补披露历史报告期（例如 7 月上市时
    才第一次公开当年一季报）这类合法但滞后的情形。
    """
    e = _period_end(period)
    return e - dt.timedelta(days=20), e + dt.timedelta(days=200)


def ann_ok(period: str, ann) -> dt.date | None:
    """校验公告日是否可信，越界返回 None。

    东财「最新公告日期」会被该公司**后续**公告刷新：药明康德 2025 年半年报这一行
    的公告日显示为 2026-08-04（那是 2026 年半年报的日期），2025 年一季报显示为
    2026-04-28。若不校验，历史各期断层会被画到错误的日子上，甚至与最近一期重叠成一条线。
    """
    if not ann:
        return None
    try:
        d = dt.date.fromisoformat(str(ann)[:10])
    except Exception:
        return None
    lo, hi = _period_bounds(period)
    return d if lo <= d <= hi else None


def gap_anchor(df: pd.DataFrame, period: str, ann, min_gap: float) -> tuple[dt.date | None, bool]:
    """定位某报告期的锚点日，返回 (锚点日, 是否非源数据公告日)。

    优先级：可信公告日 → 该报告期「业绩季」内**最贴近典型公告日**且跳空 ≥ min_gap 的一天
    → 典型公告日兜底（该期视为未跳空）。

    第二档只取「离典型公告日最近」而不是「跳空最大」：同一个业绩季里往往夹着别的
    事件造成的跳空（例如药明康德 2025-03-18 是 2024 年报的跳空），取最大会把公告日
    张冠李戴。反推出的位置恰恰是用户想在图上看到的那根 K 线，所以用 ≈ 与确切公告日区分。
    """
    d = ann_ok(period, ann)
    if d is not None:
        return d, False
    lag = _TYPICAL_LAG.get(str(period)[4:], 45)
    expected = _period_end(period) + dt.timedelta(days=lag)
    lo, hi = _period_bounds(period)
    lo2 = max(lo, expected - dt.timedelta(days=_ANCHOR_BEFORE))
    hi2 = min(hi, expected + dt.timedelta(days=_ANCHOR_AFTER))
    dates = df["date"].tolist()
    op = df["open"].tolist()
    cl = df["close"].tolist()
    best_d, best_key = None, None
    for i in range(1, len(dates)):
        dd = dates[i]
        if dd < lo2 or dd > hi2:
            continue
        o, pc = op[i], cl[i - 1]
        if o is None or pc is None or pd.isna(o) or pd.isna(pc) or float(pc) <= 0:
            continue
        g = (float(o) / float(pc) - 1) * 100
        if g < min_gap:
            continue
        key = (abs((dd - expected).days), -g)      # 先比离典型公告日的距离，再比跳空幅度
        if best_key is None or key < best_key:
            best_key, best_d = key, dd
    if best_d is not None:
        return best_d, True
    return expected, True


def _kline_worker(payload: tuple) -> dict:
    """阶段二子进程任务：只对最终保留的个股抓长历史 → 紧凑 K 线 + 每一期断层的跳空。

    items: [(code, [(period, label, ann_iso), ...]), ...]，期次**最近在前**。
    一只个股只抓一次行情，然后用同一份 df 逐期定位锚点并检测跳空，因此历史各期的
    锚点必须落在这段窗口内 —— 起点取「最早一期合理区间起点」兜底比较稳妥。
    """
    items, last_td, gdates, days_map, min_gap = payload
    axis_len = len(gdates)
    out: dict[str, dict] = {}
    for code, periods in items:
        try:
            days = min(max(int(days_map.get(code) or axis_len), 1), axis_len)
            start = last_td - dt.timedelta(days=int(days * 1.6))
            if periods:
                earliest = _period_bounds(periods[-1][0])[0]      # 期次最近在前 → 末项最早
                if earliest < start:
                    start = earliest
            df = fetch_daily(code, start, last_td + dt.timedelta(days=1))
            if df is None or not len(df):
                out[code] = {"kline": None, "period_gaps": []}
                continue
            pg = []
            for period, label, ann_iso in periods:
                try:
                    anchor, inferred = gap_anchor(df, period, ann_iso, min_gap)
                except Exception:
                    anchor, inferred = None, False
                if anchor is None:
                    pg.append({
                        "period": period, "label": label, "ann": None,
                        "gap_date": None, "gap_pct": None,
                        "valid": False, "hole": False, "inferred": False,
                    })
                    continue
                try:
                    g = detect_gap(df, anchor, last_td)
                except Exception:
                    g = None
                if not g or not g.get("gap_date"):
                    pg.append({
                        "period": period, "label": label, "ann": anchor.isoformat(),
                        "gap_date": None, "gap_pct": None,
                        "valid": False, "hole": False, "inferred": inferred,
                    })
                    continue
                pct = g.get("gap_vs_close")
                pg.append({
                    "period": period, "label": label, "ann": anchor.isoformat(),
                    "gap_date": g.get("gap_date"),
                    "gap_pct": pct,
                    "valid": bool(pct is not None and pct >= min_gap),
                    "hole": bool(g.get("gap_vs_high", 0) > 0),
                    # 锚点不是源数据公告日（跳空反推 / 典型滞后兜底）→ 图上标「≈」，避免误读为确切公告日
                    "inferred": bool(inferred),
                })
            out[code] = {"kline": kline_compact(df, gdates), "period_gaps": pg}
        except Exception:
            out[code] = {"kline": None, "period_gaps": []}
    return out


def kline_compact(df: pd.DataFrame, gdates: list[str]) -> dict | None:
    """把日线对齐到全局交易日轴，压缩为 {"d0": 起始下标, "bars": [[o,h,l,c,vol手], ...]}。

    只从该股第一根 K 线开始返回（d0 = 该股在全局轴上的起始下标），
    这样次新股 / 短回溯窗口的个股不会在轴前端塞满 null 把 payload 撑大。
    前端用 KL_DATES.slice(d0, d0+bars.length) 即得该股自己的日期轴。
    """
    if df is None or not len(df):
        return None
    dmap = {}
    for _, r in df.iterrows():
        try:
            vol = float(r["volume"]) / 100.0 if pd.notna(r.get("volume")) else 0.0
            dmap[r["date"].isoformat()] = [
                round(float(r["open"]), 2), round(float(r["high"]), 2),
                round(float(r["low"]), 2), round(float(r["close"]), 2),
                int(vol),
            ]
        except Exception:
            continue
    rows = [dmap.get(d) for d in gdates]
    first = next((i for i, x in enumerate(rows) if x is not None), None)
    if first is None:
        return None
    last = max(i for i, x in enumerate(rows) if x is not None)
    return {"d0": first, "bars": rows[first:last + 1]}


def fetch_daily_ex(code: str, start: dt.date, end: dt.date) -> tuple[pd.DataFrame, str]:
    """抓日线，并区分「数据源明确没有该股行情」与「接口/网络异常」。

    这个区分很关键：
      · 'no_quote' —— 新浪抛 KeyError('date')、腾讯抛 IndexError，说明该代码**根本没有
        二级市场行情**（尚未上市、长期停牌、数据源里的预披露条目）。它不可交易，
        不属于「漏掉交易机会」，重试也没有意义；
      · 'network'  —— 超时、连接被拒等可恢复故障。这些个股**可能本有跳空**，
        必须重试并告警。
    混为一谈的话，真故障会淹没在「未上市」噪声里（v1.15 起分开统计）。
    """
    sym = sina_symbol(code)
    key = f"k_{sym}_{start:%Y%m%d}_{end:%Y%m%d}"
    net_err = noq = False
    df = None
    try:
        df = _cached_df(
            key,
            lambda: ak.stock_zh_a_daily(symbol=sym, start_date=start.strftime("%Y%m%d"),
                                        end_date=end.strftime("%Y%m%d"), adjust=""),
            ttl_days=0.3,
            # 盘中海抓的 K 线是半成品（当日未收盘），必须重抓，否则收盘价/跳空/回补全错
            after_close=True,
        )
    except KeyError:
        noq = True                 # 新浪对无行情代码抛 KeyError('date')
    except Exception:
        net_err = True
    # 注意：无论新浪是「无行情」还是「网络错」，**都要走腾讯兜底** —— 曾经写成
    # 「仅在没有任何失败标记时才兜底」，等于把新浪 KeyError 的个股直接判死，丢掉腾讯那一路数据。
    if (df is None or not len(df)) and not sym.startswith("bj"):
        try:
            df = ak.stock_zh_a_hist_tx(symbol=sym, start_date=start.strftime("%Y%m%d"),
                                       end_date=end.strftime("%Y%m%d"), adjust="")
        except IndexError:
            noq = True             # 腾讯对无行情代码抛 IndexError
        except Exception:
            net_err = True
    if df is None or not len(df):
        # 两个源都没数据：只要有一路是网络异常，就按「网络」上报（宁可告警，不可静默）
        return pd.DataFrame(), ("network" if net_err else "no_quote" if noq else "no_quote")
    df = df.copy()
    try:
        df["date"] = pd.to_datetime(df["date"]).dt.date
    except Exception:
        return pd.DataFrame(), "no_quote"
    return df.sort_values("date").reset_index(drop=True), ""


def fetch_daily(code: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    return fetch_daily_ex(code, start, end)[0]


def detect_gap(df: pd.DataFrame, announce: dt.date, last_td: dt.date) -> dict | None:
    """检测公告后首个交易日的跳空缺口及后续回补情况。"""
    if df is None or len(df) < 3:
        return None
    dates = df["date"].tolist()
    idx = [i for i, d in enumerate(dates) if d >= announce]
    if not idx:
        return None
    i0 = idx[0]
    # 公告日或其次日，取跳空更明显的一天（公告多在盘后发布）
    best = None
    for j in [i0, i0 + 1]:
        if j <= 0 or j >= len(df):
            continue
        r, p = df.iloc[j], df.iloc[j - 1]
        if r["open"] is None or p["close"] is None:
            continue
        gap_vs_close = (r["open"] / p["close"] - 1) * 100
        gap_vs_high = (r["open"] / p["high"] - 1) * 100
        score = gap_vs_close
        if best is None or score > best["_s"]:
            best = {
                "gap_date": r["date"].isoformat(),
                "open": float(r["open"]), "high": float(r["high"]),
                "low": float(r["low"]), "close": float(r["close"]),
                "prev_close": float(p["close"]), "prev_high": float(p["high"]),
                "gap_vs_close": round(gap_vs_close, 2),
                "gap_vs_high": round(gap_vs_high, 2),
                "day_chg": round((r["close"] / p["close"] - 1) * 100, 2),
                "amount": None, "_s": score, "_j": j, "_p": p,
            }
    if best is None:
        return None
    j, p = best.pop("_j"), best.pop("_p")
    best.pop("_s", None)
    try:
        best["amount"] = float(df.iloc[j].get("amount")) if pd.notna(df.iloc[j].get("amount")) else None
        best["turnover"] = round(float(df.iloc[j].get("turnover")) * 100, 2) if pd.notna(df.iloc[j].get("turnover")) else None
    except Exception:
        pass

    tail = df.iloc[j:]
    after = tail.iloc[1:]
    ref = best["prev_high"]
    # 缺口回补：此后任一日最低价 <= 昨日最高价
    filled = bool((after["low"] <= ref).any()) if len(after) else bool(tail.iloc[0]["low"] <= ref)
    fill_date = None
    if len(after):
        hit = after[after["low"] <= ref]
        if len(hit):
            fill_date = hit.iloc[0]["date"].isoformat()
    last_close = float(df.iloc[-1]["close"])
    best.update({
        "filled": filled,
        "fill_date": fill_date,
        "days_held": int(len(after)) + 1,
        "has_gap": bool(best["gap_vs_high"] > 0),
        "ret_since_gap": round((last_close / best["open"] - 1) * 100, 2),
        "last_close": last_close,
    })
    try:
        os_share = float(df.iloc[-1].get("outstanding_share"))
        if os_share > 0:
            best["mcap"] = round(os_share * last_close, 0)   # 流通市值（元）
    except Exception:
        pass
    return best


# ================================================================ 候选汇总
def collect_candidates(period: str, cal: TradeCalendar, win_start: dt.date, win_end: dt.date,
                       args, force_fin: bool = False) -> tuple[list[dict], dict, dict]:
    """把预告/快报/报表统一为候选列表，并计算断层强度。

    `win_start` / `win_end` 是闭区间的公告窗口，由 scan() 按窗口模式算好传进来
    （见 period_window()：默认按报告期覆盖，`--days N` 时退回滚动 N 天）。

    `force_fin=True` 时该期的财报接口绕过 12 小时缓存强制重抓 —— 窗口内的报告期
    正在持续新增公告，用旧快照会把当天盘后新披露的公司整批漏掉。

    返回 (候选列表, 累计口径表, 审计统计)。
    """
    cmaps: dict[str, dict] = {}
    # 只有**窗口内的报告期**需要强刷：它正在持续新增公告。辅助期（上季 / 去年同期）
    # 的数据早已定档不会再变，继续走缓存，避免把每次扫描都拖成几十次网络往返。
    cmaps[period] = cum_profit_map(period, force=force_fin)
    aux = {prev_quarter_end(period), year_ago(period),
           prev_quarter_end(year_ago(period)), *calendar_stub(period)} - {None}
    for p in sorted(aux):
        if p != period and p not in cmaps:
            cmaps[p] = cum_profit_map(p)
    rows: list[dict] = []
    raw = {"业绩预告": 0, "业绩快报": 0, "正式财报": 0}

    # ---------- 业绩预告 ----------
    fc = fetch_forecast(period, force=force_fin)
    if len(fc):
        raw["业绩预告"] = int(len(fc))
        fc = fc.copy()
        fc["股票代码"] = fc["股票代码"].astype(str).str.zfill(6)
        fc["预告类型"] = fc["预告类型"].astype(str)
        fc = fc[fc["预告类型"].str.contains("增|盈|扭亏|减亏", na=False)]
        pri = {"归属于上市公司股东的净利润": 0, "净利润": 1}
        fc["_pri"] = fc["预测指标"].map(lambda x: pri.get(str(x), 9))
        fc = fc[fc["_pri"] < 9].sort_values(["股票代码", "_pri"])
        fc = fc.drop_duplicates("股票代码")
        for _, r in fc.iterrows():
            rows.append({
                "code": r["股票代码"], "name": safe_text(r.get("股票简称")),
                "source": "业绩预告", "period": period,
                "announce": safe_text(r.get("公告日期"))[:10],
                "growth_cum": to_num(r.get("业绩变动幅度")),
                "forecast_type": safe_text(r.get("预告类型")),
                "reason": safe_text(r.get("业绩变动原因")),
                "np_cum": to_num(r.get("预测数值")), "np_prev_cum": to_num(r.get("上年同期值")),
            })

    # ---------- 业绩快报 ----------
    fb = fetch_flash(period, force=force_fin)
    if len(fb):
        raw["业绩快报"] = int(len(fb))
        fb = fb.copy()
        fb["股票代码"] = fb["股票代码"].astype(str).str.zfill(6)
        for _, r in fb.iterrows():
            rows.append({
                "code": r["股票代码"], "name": safe_text(r.get("股票简称")),
                "source": "业绩快报", "period": period,
                "announce": safe_text(r.get("公告日期"))[:10],
                "growth_cum": to_num(r.get("净利润-同比增长")),
                "forecast_type": "", "reason": "",
                "np_cum": to_num(r.get("净利润-净利润")), "np_prev_cum": to_num(r.get("净利润-去年同期")),
                "industry": safe_text(r.get("所处行业")),
            })

    # ---------- 正式财报 ----------
    rp = fetch_report(period, force=force_fin)
    if len(rp):
        raw["正式财报"] = int(len(rp))
        rp = rp.copy()
        rp["股票代码"] = rp["股票代码"].astype(str).str.zfill(6)
        for _, r in rp.iterrows():
            rows.append({
                "code": r["股票代码"], "name": safe_text(r.get("股票简称")),
                "source": "正式财报", "period": period,
                "announce": safe_text(r.get("最新公告日期"))[:10],
                "growth_cum": to_num(r.get("净利润-同比增长")),
                "forecast_type": "", "reason": "",
                "np_cum": to_num(r.get("净利润-净利润")), "np_prev_cum": None,
                "industry": safe_text(r.get("所处行业")),
            })

    # 公告日期窗口过滤 + 去重（同股保留信息量更大的一条）
    out: dict[str, dict] = {}
    prio = {"正式财报": 0, "业绩快报": 1, "业绩预告": 2}
    stat = {"rows": len(rows), "no_date": 0, "out_of_window": 0,
            "in_window": 0, "suspect_ann": 0}
    dl = legal_deadline(period)
    for r in rows:
        try:
            ann = dt.date.fromisoformat(r["announce"])
        except Exception:
            stat["no_date"] += 1                 # 公告日缺失 / 解析失败：单列计数，不混进窗口剔除
            continue
        if ann < win_start or ann > win_end:
            stat["out_of_window"] += 1
            continue
        r["announce"] = ann.isoformat()
        # 正式财报的「最新公告日期」会被后续公告刷新，晚于法定披露截止即可疑。
        # 可疑行不改窗口（窗口已含宽限），只做标记 → 阶段一用「业绩季内按跳空反推」定位锚点。
        if r["source"] == "正式财报" and ann > dl:
            r["ann_suspect"] = True
            stat["suspect_ann"] += 1
        old = out.get(r["code"])
        if old is None or prio[r["source"]] < prio[old["source"]]:
            if old and old.get("reason") and not r.get("reason"):
                r["reason"] = old["reason"]
                r["forecast_type"] = r.get("forecast_type") or old.get("forecast_type", "")
            out[r["code"]] = r
    cands = list(out.values())
    stat["in_window"] = len(cands)

    # 计算单季与加速度
    for c in cands:
        code = c["code"]
        sq, sq_yoy, y_sq = single_quarter(code, period, cmaps)
        c["np_single"] = sq
        c["np_single_year_ago"] = y_sq
        c["growth_single"] = round(sq_yoy, 2) if sq_yoy is not None else None
        cm = cmaps.get(period, {}).get(code) or {}
        cm_prev = cmaps.get(prev_quarter_end(period) or "", {}).get(code) or {}
        c["industry"] = c.get("industry") or cm.get("industry") or cm_prev.get("industry") or ""
        c["growth_prev_cum"] = cm_prev.get("yoy")
        c["announce_report"] = cm.get("ann") or c["announce"]

        growth = c["growth_single"] if c["growth_single"] is not None else c["growth_cum"]
        c["growth"] = round(growth, 2) if growth is not None else None
        c["growth_basis"] = "单季同比" if c["growth_single"] is not None else "累计同比"
        prev_growth = cm_prev.get("yoy")
        c["growth_prev"] = round(prev_growth, 2) if prev_growth is not None else None
        if c["growth"] is not None and c["growth_prev"] is not None:
            c["accel"] = round(c["growth"] - c["growth_prev"], 2)
        else:
            c["accel"] = None
    stat["raw"] = raw
    stat["period"] = period
    return cands, cmaps, stat


def calendar_stub(period: str) -> list[str]:
    """单季差分所需的历史报告期（同年上一季 + 去年同期两季）"""
    y = year_ago(period)
    return [p for p in (prev_quarter_end(period), prev_quarter_end(y), y) if p]


# ================================================================ 打分与标签
def enrich(c: dict, gap: dict | None, args) -> dict:
    code = c["code"]
    c["board"] = board_of(code)
    tags, risks = [], []

    growth = c.get("growth")
    accel = c.get("accel")

    # ---- 利润断层判定（v1.12 起两道利润门槛默认都不设，清单由「价格断层」单独决定）----
    # 门槛关掉后 profit_gap 恒为 True，仍保留这个字段是因为预告池 / 标签 / 页面文案还在用它。
    yoy_ok = True if args.min_yoy is None else (growth is not None and growth >= args.min_yoy)
    accel_ok = True if args.min_accel is None else (accel is not None and accel >= args.min_accel)
    profit_gap = bool(yoy_ok and accel_ok)
    if yoy_ok and not accel_ok and c.get("forecast_type") in ("扭亏", "预增"):
        profit_gap = True
        risks.append("缺上期数据或加速度未达标（口径差异）")
        # 记录「放行是走了口径豁免」，业绩预告池要据此把这类单独标出来，
        # 不能笼统说成「加速度达标」——预告普遍缺上期单季数据，全靠这条豁免进来。
        c["accel_exempt"] = True
    c["accel_ok"] = bool(accel_ok)
    if c.get("forecast_type") == "扭亏":
        tags.append("扭亏")
        risks.append("扭亏型：上年同期为负，增速口径失真")
    elif c.get("forecast_type") in ("预增", "略增", "续盈"):
        tags.append(c["forecast_type"])
    # 「增速加速」标签是给用户看的「这只确实在加速」的强信号，不能因为门槛被关掉
    # 就退化成 accel >= 0 都打——那等于把标签变成噪声。所以阈值恒为 20pct，与门槛解耦。
    if profit_gap and accel is not None and accel >= ACCEL_TAG_PCT:
        tags.append("增速加速")
    if c.get("growth_basis") == "单季同比":
        tags.append("单季口径")
    if c["source"] == "正式财报":
        tags.append("正式财报")
    elif c["source"] == "业绩快报":
        tags.append("业绩快报")

    reason = c.get("reason") or ""
    hit = [k for k in ND_KEYWORDS if k in reason]
    if hit:
        risks.append("非经常损益嫌疑：" + "/".join(hit[:3]))

    # ---- 低基数识别（增速失真的主要来源）----
    low_base = False
    y_sq = c.get("np_single_year_ago")
    if c.get("growth_basis") == "单季同比" and y_sq is not None and 0 < y_sq < 1000e4:
        low_base = True
        risks.append(f"低基数：上年同期单季净利仅 {y_sq/1e4:.0f} 万元，增速参考性弱")
    elif (growth or 0) > 1000 and c.get("growth_basis") == "累计同比" and (c.get("np_prev_cum") or 0) <= 0:
        low_base = True
        risks.append("低基数：上年同期亏损或微利，累计增速失真")
    elif (growth or 0) > 3000:
        low_base = True
        risks.append("增速极端（>3000%），大概率为基数效应")
    c["low_base"] = low_base
    if low_base:
        tags.append("低基数")
    if growth is not None and growth > 500:
        risks.append("增速极端（>500%），注意低基数")
    if args.exclude_st and re.search(r"ST|退", c.get("name", "")):
        risks.append("ST/退市风险股")

    # ---- 价格断层 ----
    price_gap = False
    # 行情缺失必须与「确实没跳空」区分开：前者无法判断，后者是判定结果。
    # 混为一谈会让抓取失败静默混进「已剔除未跳空」，真漏无痕。
    # 再往下细分两层：网络故障（可能漏票，要告警）与无该股行情（未上市/停牌，不可交易）。
    fetch_failed = bool(isinstance(gap, dict) and gap.get("__fetch_failed__"))
    no_quote = bool(isinstance(gap, dict) and gap.get("__no_quote__"))
    c["fetch_failed"] = fetch_failed
    c["no_quote"] = no_quote
    if fetch_failed or no_quote:
        gap = None
    if gap:
        gap["valid"] = bool(gap.get("gap_vs_close", 0) >= args.min_gap)
        c["gap"] = gap
        price_gap = bool(gap["valid"])
        if price_gap:
            tags.append("跳空高开")
        if not gap.get("filled"):
            tags.append("缺口未回补")
        elif not price_gap:
            risks.append("公告后无有效跳空")
        if gap.get("gap_vs_close", 0) >= 9:
            risks.append("接近一字板，恐难买入")
    else:
        c["gap"] = None
        if fetch_failed:
            risks.append("行情抓取失败（网络/接口），无法判断是否跳空")
        elif no_quote:
            risks.append("无行情数据（未上市或长期停牌）")
        else:
            risks.append("公告后无有效跳空")

    c["profit_gap"] = profit_gap
    c["price_gap"] = price_gap
    # ---- 分层（v1.12：利润侧不再设门槛，tier 降级为「描述性标签」，不承担过滤职责）----
    # 用户 2026-10-04 明确「利润侧完全不设门槛，只要出现跳空就列出来」。两道利润门槛都关掉后
    # profit_gap 恒为 True，再用它分层会把所有个股一律标成「双断层」——对业绩下滑的公司是误导。
    # 因此改用只作文案用途的 grow_up（本期同比是否为正）：
    #   正增长 + 跳空 → 核心池·双断层；低基数 → 观察池·低基数断层；未增长但有跳空 → 跟踪·仅价格缺口。
    # grow_up **不参与任何过滤**，业绩下滑但跳空的个股照样进清单，只是标签如实写「仅价格缺口」。
    grow_up = (growth is not None and growth > 0)
    c["grow_up"] = grow_up
    if low_base:
        c["tier"] = "观察池·低基数断层"
        if price_gap:
            tags.append("双断层(价格已确认)")
    elif grow_up and price_gap:
        c["tier"] = "核心池·双断层"
    elif price_gap:
        c["tier"] = "跟踪·仅价格缺口"
    elif grow_up:
        c["tier"] = "观察池·仅利润断层"
    else:
        c["tier"] = "剔除"
    tags.append(c["tier"].split("·")[0])

    # ---- 评分 ----
    s = 0.0
    if growth is not None:
        s += min(max(growth, 0), 300) / 300 * 30
    if accel is not None:
        s += min(max(accel, 0), 150) / 150 * 20
    if gap and price_gap:
        s += min(gap["gap_vs_close"], 9) / 9 * 20
    if gap and not gap.get("filled"):
        s += 15
    amt = (gap or {}).get("amount") or 0
    s += min(amt / 5e8, 1) * 10
    if c["source"] in ("正式财报", "业绩快报"):
        s += 5
    if low_base:
        s -= 12          # 低基数降权：增速不可靠
    mcap = (gap or {}).get("mcap")
    if mcap is not None and mcap < 30e8:
        s -= 5           # 小市值流动性与波动风险
        risks.append("流通市值 < 30 亿元")
    c["score"] = round(max(min(s, 100), 0), 1)
    c["tags"] = tags
    c["risks"] = risks
    return c


# ================================================================ 主流程
def scan(args) -> dict:
    cal = TradeCalendar()
    today = dt.date.today()
    last_td = cal.last_trading_day(today)
    market_open = cal.is_trading(today)
    periods = [args.period] if args.period else quarter_ends(today)
    grace = max(0, int(getattr(args, "grace_days", REFRESH_GRACE_DAYS) or 0))
    back = getattr(args, "window_back", None)
    if back is not None:
        back = max(0, int(back))          # None = 下界取「上一报告期结束日」
    # 窗口模式：默认「报告期覆盖」（各期用自己的法定披露季），传了 --days 才退回滚动 N 天
    if args.days is None:
        window_mode = "period"
        windows = {p: period_window(p, today, grace, back) for p in periods}
    else:
        window_mode = "days"
        windows = {p: (today - dt.timedelta(days=args.days), today) for p in periods}
    # 窗口内报告期强制刷新财报缓存：公告是滚动的，用隔夜的快照必然漏掉当天盘后新披露的个股
    force_fin = not getattr(args, "fin_cache", False)
    log(f"扫描日 {today} | 最后交易日 {last_td} | 市场{'交易中/已收盘' if market_open else '休市中'} | 报告期 {periods}")
    log(f"公告窗口模式 {window_mode}：" + "；".join(
        f"{period_label(p)} {a.isoformat()}~{b.isoformat()}" for p, (a, b) in windows.items()))
    lo_desc = "上一报告期结束日" if back is None else f"期末 − {back} 天"
    log(f"窗口下界 {lo_desc} · 上界宽限 {grace} 天（法定披露截止 + {grace}）")
    for p in periods:
        dl = legal_deadline(p)
        cover = "披露季已结束·窗口完整" if today > dl else f"披露季进行中·覆盖至 {min(today, dl + dt.timedelta(days=grace))}"
        log(f"  {period_label(p)} 法定披露截止 {dl}（{cover}）")
    if force_fin:
        log("财报缓存：窗口内报告期强制重抓（--fin-cache 可关闭）")

    all_c: dict[str, dict] = {}
    cmaps_all: dict[str, dict] = {}
    period_stats: list[dict] = []
    failed_periods: list[str] = []
    SOURCE_ERRORS.clear()
    for p in periods:
        try:
            cands, cmaps, st = collect_candidates(p, cal, windows[p][0], windows[p][1],
                                                 args, force_fin=force_fin)
        except Exception as e:
            # 整期失败会让该期个股**全部消失**，属于最高级别的静默漏票 → 记录下来大声报错
            log(f"[ERROR] 报告期 {p} 处理失败，该期个股全部缺席：{e}")
            failed_periods.append(p)
            continue
        cmaps_all.update(cmaps)
        for c in cands:
            old = all_c.get(c["code"])
            if old is None or (c.get("growth") or -1e9) > (old.get("growth") or -1e9):
                all_c[c["code"]] = c
        period_stats.append(st)
        log(f"  报告期 {period_label(p)}：接口返回 预告 {st['raw']['业绩预告']} / "
            f"快报 {st['raw']['业绩快报']} / 财报 {st['raw']['正式财报']} 行"
            f" → 有效候选行 {st['rows']} → 窗口内 {len(cands)} 只"
            + (f"；其中公告日疑似被刷新 {st['suspect_ann']} 只" if st["suspect_ann"] else ""))
        if not cands:
            log(f"  [WARN] 报告期 {period_label(p)} 窗口内候选为 0 —— 若该期已进入披露季，"
                f"说明接口或窗口出了问题，请核查")

    cands = list(all_c.values())
    suspect_total = sum(st["suspect_ann"] for st in period_stats)
    log(f"候选合计 {len(cands)} 只（公告日疑似被后续公告刷新 {suspect_total} 只，将改用业绩季反推锚点），开始过滤与缺口检测…")

    # ---- 来源整批缺失检查（第 7 条漏票渠道）----
    # 正式财报是**强制披露**：报告期一旦进入披露季（期末 + SOURCE_OPEN_DAYS 天），全市场就不可能 0 行。
    # 若此时取到 0 行（接口失败被 fetch_report 吞成空表），意味着这一整个来源整批丢了——
    # 会静默少掉几千只候选，而审计器的自洽校验（拿引擎自己记录的行数比）是发现不了的。
    # 快报/预告属自愿披露、时有时无，只登记接口异常、不作硬拦截。
    missing_src: list[str] = []
    for st in period_stats:
        p = st["period"]
        if today < _period_end(p) + dt.timedelta(days=SOURCE_OPEN_DAYS):
            continue                        # 还没到披露季，0 行是正常的（如当前的三季报）
        if (st.get("raw") or {}).get("正式财报", 0) == 0:
            missing_src.append(f"{period_label(p)} 正式财报 0 行（期末已过 {SOURCE_OPEN_DAYS} 天，应已披露）")
    src_err: list[str] = []
    seen: set[tuple] = set()
    for e in SOURCE_ERRORS:
        k = (e["source"], e["period"])
        if k in seen or e["period"] not in set(periods):
            continue
        seen.add(k)
        src_err.append(f"{period_label(e['period'])} {e['source']}：{e['error'][:60]}")
    if src_err:
        log(f"[WARN] 窗口内报告期接口异常 {len(src_err)} 处（若该期已进入披露季则已计入 missing_sources）："
            + "；".join(src_err))

    # 板块 / ST 过滤
    boards = [b.strip() for b in args.boards.split(",") if b.strip()]
    kept = []
    board_out = st_out = 0
    for c in cands:
        b = board_of(c["code"])
        if boards and b not in boards:
            board_out += 1
            continue
        if args.exclude_st and re.search(r"ST|退", c.get("name", "")):
            st_out += 1
            continue
        kept.append(c)
    log(f"板块过滤后 {len(kept)} 只（剔除非目标板块 {board_out} 只 / ST·退 {st_out} 只）")

    # ---- 连续断层期数：需要多期累计口径财报，一次性补载（缓存 12 小时） ----
    streak_n = max(1, int(args.streak_max))
    need_periods: set[str] = set()
    for c in kept:
        need_periods |= streak_needed_periods(c["period"], streak_n)
    todo = sorted(p for p in need_periods if p not in cmaps_all)
    if todo:
        log(f"连续断层期数：补载 {len(todo)} 个历史报告期财报（{todo[0]} … {todo[-1]}）")
        for p in todo:
            cmaps_all.setdefault(p, cum_profit_map(p))
    for c in kept:
        st, series, start = compute_streak(c["code"], c["period"], cmaps_all, streak_n, args.streak_yoy)
        c["streak"] = st
        c["streak_series"] = series
        c["streak_from"] = start
        c["streak_periods"] = [s["period"] for s in series if s.get("hit")]
    got = sum(1 for c in kept if c["streak_series"])
    best = max((c["streak"] for c in kept), default=0)
    log(f"连续断层期数：{got}/{len(kept)} 只取到单季序列，最长连续 {best} 期（门槛 单季同比 ≥{args.streak_yoy}%）")

    # 缺口检测 + K 线缓存（对全部候选取行情，保证每只都能看 K 线）
    if args.min_yoy is None:
        need_price = list(kept)
    else:
        need_price = [c for c in kept if (c.get("growth") or -1e9) >= args.min_yoy]
    # 安全阀：--max-candidates 0 表示不限。**一旦触发不再截断，而是自动抬高并告警** ——
    # 被截断的个股拿不到行情 → 判为「未跳空」→ 静默漏扫。用户的第一诉求是「不许漏」，
    # 所以宁可变慢也不能悄悄丢票。
    cap = int(getattr(args, "max_candidates", 0) or 0)
    truncated = 0
    if cap and len(need_price) > cap:
        truncated = len(need_price) - cap
        log(f"[WARN] 候选 {len(need_price)} 只超过 --max-candidates {cap}：**本次不截断**，"
            f"自动抬高上限至 {len(need_price)} 只（强行截断会静默漏掉 {truncated} 只，不允许发生）")
    # 业绩预告候选往往加速度不突出，可能被 max_candidates 截断，补捞一次（数量很小，代价可忽略）
    have = {c["code"] for c in need_price}
    extra = [c for c in kept if c.get("source") == "业绩预告" and c["code"] not in have]
    if extra:
        need_price = need_price + extra
        log(f"  额外纳入 {len(extra)} 只业绩预告候选（避免被 max_candidates 截断掉）")
    need_price = list({id(c): c for c in need_price}.values())   # 去重，保持顺序
    base_days = max(20, int(args.hist_days))
    cap_days = max(base_days, int(getattr(args, "hist_days_max", base_days) or base_days))
    workers = max(1, min(args.workers, (os.cpu_count() or 4)))

    log(f"阶段一：缺口检测 {len(need_price)} 只（窗口 {base_days} 个交易日，进程数 {workers}）")
    price_map: dict[str, dict] = {}
    if need_price:
        # 第 4 项 ann_suspect：东财「最新公告日期」晚于法定披露截止 → 不可信，
        # 阶段一改在该期业绩季内按跳空反推锚点（见 _gap_worker）。
        tasks = [(c["code"], c["announce"], c["period"], bool(c.get("ann_suspect")))
                 for c in need_price]
        if workers == 1:
            res_all = [_gap_worker((tasks, last_td, base_days, args.min_gap))]
        else:
            from concurrent.futures import ProcessPoolExecutor
            chunk = max(1, (len(tasks) + workers - 1) // workers)
            chunks = [tasks[i:i + chunk] for i in range(0, len(tasks), chunk)]
            res_all = []
            with ProcessPoolExecutor(max_workers=min(workers, len(chunks))) as ex:
                done = 0
                for res in ex.map(_gap_worker,
                                  [(ch, last_td, base_days, args.min_gap) for ch in chunks]):
                    res_all.append(res)
                    done += 1
                    log(f"  行情进度 {done}/{len(chunks)} 批")
        for res in res_all:
            for code, g in res.items():
                price_map[code] = g

    results = [enrich(c, price_map.get(c["code"]), args) for c in kept]
    if args.min_np > 0:
        results = [r for r in results if (r.get("np_single") or 0) >= args.min_np]
    if args.min_mcap > 0:
        results = [r for r in results if ((r.get("gap") or {}).get("mcap") or 0) >= args.min_mcap]
    results = [r for r in results if r["tier"] != "剔除" and r["score"] >= args.min_score]

    # ---- 行情缺失：单独计数、单独告警，绝不混进「已剔除未跳空」 ----
    ff_rows = [r for r in results if r.get("fetch_failed")]
    nq_rows = [r for r in results if r.get("no_quote")]
    ff_codes = [r["code"] for r in ff_rows]
    nq_codes = [r["code"] for r in nq_rows]
    if nq_rows:
        log(f"无行情数据 {len(nq_rows)} 只（未上市 / 长期停牌，不可交易，不算漏票）："
            + " ".join(nq_codes[:30]) + (" …" if len(nq_codes) > 30 else ""))
    if ff_rows:
        rate = len(ff_rows) / max(1, len(kept)) * 100
        log(f"[WARN] 行情抓取失败 {len(ff_rows)} 只（占候选 {rate:.1f}%）："
            + " ".join(ff_codes[:40]) + (" …" if len(ff_codes) > 40 else ""))
        log("       ↑ 这些个股无法判断是否跳空，**不在**「已剔除未跳空」计数内；"
            "若其中有真跳空，本次清单会缺它们（已重试 3 次仍失败）")
    suspect_n = sum(1 for c in kept if c.get("ann_suspect"))
    suspect_recov = sum(1 for r in results if (r.get("gap") or {}).get("anchor_inferred"))

    # ---------------- 业绩预告池（v1.12 起默认关闭，需显式 --pre-pool 开启）----------------
    # 该池的原始理由是「利润断层已成立、但价格还没跳空」，用作提前埋伏的线索。
    # 但利润侧门槛关掉后 profit_gap 恒为 True，这个条件会把**所有没有有效跳空的预告**
    # 全捞进来，直接违反用户「保留 ≥min_gap% 跳空条件」的要求，所以默认关闭。
    # 现在预告只有真正跳空了才进清单，与正式财报 / 快报一视同仁。
    pre_pool: list[dict] = []
    if args.require_price_gap and getattr(args, "pre_pool", False):
        for r in results:
            if r.get("source") != "业绩预告" or not r.get("profit_gap"):
                continue
            g = r.get("gap") or {}
            if g.get("valid") and not g.get("filled"):
                continue                       # 有效且未回补 → 它已经在主清单里了
            r["gap_state"] = "已回补" if g.get("valid") else "尚未跳空"
            # 预告普遍缺上期单季数据，靠「预增/扭亏 口径豁免」进来的必须单独标出，
            # 否则用户会以为它们的加速度也达标了。
            r["pre_tier"] = "口径豁免" if r.get("accel_exempt") else "增速加速"
            pre_pool.append(r)
        pre_pool.sort(key=lambda r: (0 if r.get("pre_tier") == "增速加速" else 1,
                                     -r["score"], -(r.get("growth") or 0)))
        if pre_pool:
            ng = sum(1 for r in pre_pool if r["gap_state"] == "尚未跳空")
            ex = sum(1 for r in pre_pool if r["pre_tier"] == "口径豁免")
            log(f"业绩预告池：{len(pre_pool)} 只预告型利润断层"
                f"（尚未跳空 {ng} / 已回补 {len(pre_pool) - ng}；其中口径豁免 {ex} 只）")

    # 只保留真正出现有效跳空的个股（用户要求：不需要「未跳空」的个股）
    # 注意：抓取失败的个股此处同样会被剔出清单（无法确认跳空），但**不计入**
    # 「已剔除未跳空」—— 口径必须干净，否则真漏会被伪装成正常剔除。
    no_gap_removed = 0
    if args.require_price_gap:
        removed = [r for r in results if not (r.get("gap") or {}).get("valid")]
        # 「行情缺失」两类都不算「未跳空」：那是没查到，不是判定结果
        no_gap_removed = sum(1 for r in removed
                             if not r.get("fetch_failed") and not r.get("no_quote"))
        results = [r for r in results if (r.get("gap") or {}).get("valid")]
    if no_gap_removed:
        log(f"已剔除未跳空个股 {no_gap_removed} 只（无有效跳空 ≥{args.min_gap}%）")

    # 已形成有效跳空缺口（≥min_gap）但随后被回补的个股**彻底剔除**：
    # 不进清单、不进 K 线缓存、不写进任何产物文件，只在 summary 里留一个计数。
    dropped_filled = 0
    dropped_filled_codes: list[str] = []
    # 「当日开盘就低于前一日最高价」的缺口：开盘跳空为正（gap_vs_close ≥ min_gap），
    # 但价格仍在前一日的日内区间之内（gap_vs_high ≤ 0）→ detect_gap 会立刻判为已回补。
    # 这类未必是真的「缺口被补」，需要单独计量，否则口径问题会被当成正常剔除。
    dropped_filled_inrange = 0
    if not args.keep_filled:
        keep_res = []
        for r in results:
            g = r.get("gap") or {}
            if g.get("valid") and g.get("filled"):
                dropped_filled += 1
                dropped_filled_codes.append(r["code"])
                if (g.get("gap_vs_high") or 0) <= 0:
                    dropped_filled_inrange += 1
                continue
            keep_res.append(r)
        results = keep_res
    results.sort(key=lambda r: (-r["score"], -(r.get("growth") or 0)))
    if dropped_filled:
        log(f"已剔除缺口回补个股 {dropped_filled} 只（不再出现在看板任何位置）")
    # ---------------- 阶段二：只给最终保留的个股抓长历史 K 线 + 每期断层的跳空 ----------------
    # 预告池的个股也要 K 线（它们的「还没跳空」最需要看图确认），所以一起进阶段二。
    all_rows = results + pre_pool
    kline_map: dict[str, dict] = {}
    kline_base = max(base_days, int(getattr(args, "kline_days", base_days) or base_days))
    days_map = {
        r["code"]: kline_days_for(r.get("streak_periods") or [], last_td, kline_base, cap_days)
        for r in all_rows
    }
    axis_len = max([kline_base] + list(days_map.values())) if days_map else kline_base
    gdates = [d.isoformat() for d in cal.between(last_td - dt.timedelta(days=int(axis_len * 1.8)), last_td)][-axis_len:]
    deep = sum(1 for v in days_map.values() if v > kline_base)
    log(f"阶段二：K 线 {len(all_rows)} 只（主清单 {len(results)} + 预告池 {len(pre_pool)}；全局日期轴 {len(gdates)} 个交易日；"
        f"{deep} 只因连续断层回溯更长；基准 {kline_base} / 上限 {cap_days}）")

    gap_series = 0
    if all_rows:
        t2 = []
        for r in all_rows:
            # ⚠️ 这个局部变量**不能叫 `periods`**：会遮蔽第 968 行那个「本轮覆盖的报告期」列表，
            # 循环结束后 `periods` 会变成最后一只个股的命中期（通常是 []），
            # 于是 meta.periods / period_labels 全空 → 简报里「覆盖报告期：；」。
            hit_periods = [(s["period"], s["label"], s.get("ann"))
                           for s in (r.get("streak_series") or []) if s.get("hit")]
            t2.append((r["code"], hit_periods))
        if workers == 1:
            res2 = [_kline_worker((t2, last_td, gdates, days_map, args.min_gap))]
        else:
            from concurrent.futures import ProcessPoolExecutor
            chunk2 = max(1, (len(t2) + workers - 1) // workers)
            ch2 = [t2[i:i + chunk2] for i in range(0, len(t2), chunk2)]
            res2 = []
            with ProcessPoolExecutor(max_workers=min(workers, len(ch2))) as ex:
                for res in ex.map(_kline_worker, [(c, last_td, gdates, days_map, args.min_gap) for c in ch2]):
                    res2.append(res)
        kdata: dict[str, dict] = {}
        for res in res2:
            kdata.update(res)
        for r in all_rows:
            v = kdata.get(r["code"]) or {}
            if v.get("kline"):
                kline_map[r["code"]] = v["kline"]
            pg = v.get("period_gaps") or []
            r["period_gaps"] = pg
            # 该股实际抓取的 K 线交易日数（看板「回溯深度」展示 + 自检校验用）
            r["kline_days"] = int(days_map.get(r["code"]) or 0)
            gap_series += sum(1 for x in pg if x.get("valid"))
        log(f"阶段二完成：{len(kline_map)} 只有 K 线；累计标出 {gap_series} 次有效跳空（含历史各期）")

    summary = {
        "total": len(results),
        "core": sum(1 for r in results if r["tier"].startswith("核心")),
        "watch": sum(1 for r in results if r["tier"].startswith("观察")),
        "price_only": sum(1 for r in results if r["tier"].startswith("跟踪")),
        "low_base": sum(1 for r in results if r.get("low_base")),
        "dropped_filled": dropped_filled,
        "dropped_nogap": no_gap_removed,
        "with_kline": len(kline_map),
        "gap_series": gap_series,
        "gap_multi": sum(1 for r in results if len([x for x in (r.get("period_gaps") or []) if x.get("valid")]) >= 2),
        "streak_best": max([r.get("streak") or 0 for r in results], default=0),
        "streak_ge3": sum(1 for r in results if (r.get("streak") or 0) >= 3),
        "top_growth": max([r["growth"] for r in results if r.get("growth") is not None], default=None),
        "top_gap": max([r["gap"]["gap_vs_close"] for r in results if r.get("gap")], default=None),
        # 业绩预告池（单独成表，不受「必须有跳空」约束）
        "pre_pool": len(pre_pool),
        "pre_nogap": sum(1 for r in pre_pool if r.get("gap_state") == "尚未跳空"),
        "pre_filled": sum(1 for r in pre_pool if r.get("gap_state") == "已回补"),
        "pre_exempt": sum(1 for r in pre_pool if r.get("pre_tier") == "口径豁免"),
    }

    # ---------------- 数据完整性审计（v1.15） ----------------
    # 目的：把「有没有漏票」从「看不出来」变成「有数可查、可断言」。
    # 既有产物页面上不展示（用户已要求删除一切解释文案），落盘到 data/audit_YYYYMMDD.json，
    # 并可由 tools/audit_pipeline.py 独立核验。
    audit = {
        "scan_date": today.isoformat(),
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_trade_date": last_td.isoformat(),
        "window_mode": window_mode,
        "grace_days": grace,
        "window_back_days": back,
        "periods": periods,
        # 各期实际生效的闭区间窗口，供 tools/audit_pipeline.py 独立复算
        "windows": {p: [windows[p][0].isoformat(), windows[p][1].isoformat()] for p in periods},
        "period_stats": period_stats,          # 各期原始行 / 窗口内 / 公告日可疑
        "failed_periods": failed_periods,      # 整期失败 = 该期个股全缺席
        "board_filtered_out": board_out,
        "st_filtered_out": st_out,
        "candidates": len(cands),
        "kept": len(kept),
        "need_price": len(need_price),
        "truncated_by_max_candidates": truncated,
        "fetch_failed": len(ff_rows),
        "fetch_failed_codes": ff_codes,
        "no_quote": len(nq_rows),
        "no_quote_codes": nq_codes,
        "suspect_ann": suspect_n,              # 公告日疑似被后续公告刷新
        "suspect_ann_total_in_window": suspect_total,
        "suspect_ann_recovered": suspect_recov,  # 其中靠业绩季反推锚点进入清单的
        "dropped_nogap": no_gap_removed,
        "dropped_filled": dropped_filled,
        "dropped_filled_inrange": dropped_filled_inrange,
        "dropped_filled_codes": dropped_filled_codes,
        "kept_final": len(results),
        "fin_cache_forced": force_fin,
        "missing_sources": missing_src,        # 来源整批缺失（正式财报披露季内 0 行）
        "source_errors": src_err,              # 窗口内报告期的接口异常（登记用，快报/预告不硬拦）
    }
    # 硬性健康检查：任何一条不满足都说明本次结果可能不完整
    problems = []
    if failed_periods:
        problems.append(f"报告期处理失败 {failed_periods}（该期个股全部缺席）")
    if truncated:
        problems.append(f"候选被 --max-candidates 截断 {truncated} 只")
    if ff_rows and len(ff_rows) / max(1, len(kept)) > 0.01:
        problems.append(f"行情抓取失败 {len(ff_rows)} 只（占比 {len(ff_rows)/max(1,len(kept))*100:.1f}% > 1%）")
    if any(st["in_window"] == 0 for st in period_stats):
        problems.append("存在窗口内候选为 0 的报告期")
    if missing_src:
        problems.append("来源整批缺失：" + "；".join(missing_src))
    audit["problems"] = problems
    if problems:
        log("[ERROR] 数据完整性检查未通过：" + "；".join(problems) + " —— 本次清单可能不完整")
    else:
        log("数据完整性检查通过：无整期失败 / 无截断 / 无异常抓取失败")

    # 功能③：按行业（板块）聚合
    sectors = sector_summary(results)
    log(f"行业聚合：{len(sectors)} 个板块")

    payload = {
        "meta": {
            "scan_date": today.isoformat(),
            "last_trade_date": last_td.isoformat(),
            "market_status": "交易中/已收盘" if market_open else "休市（使用最近交易日行情）",
            "periods": periods,
            "period_labels": [period_label(p) for p in periods],
            "window_mode": window_mode,
            # window_start / window_days 保留兼容旧读取方：period 模式下取各期窗口的并集区间
            "window_start": min(a for a, _ in windows.values()).isoformat(),
            "window_end": max(b for _, b in windows.values()).isoformat(),
            "window_days": args.days,
            "window_ranges": [
                {"period": p, "label": period_label(p),
                 "start": windows[p][0].isoformat(), "end": windows[p][1].isoformat()}
                for p in periods
            ],
            # 页面与简报统一用这一句，别再各自拼 window_start/window_days
            "window_label": _window_label(window_mode, args.days, windows, periods, grace),
            "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "thresholds": {
                "min_yoy": args.min_yoy, "min_accel": args.min_accel,
                "min_gap": args.min_gap, "boards": args.boards,
                "drop_filled": not args.keep_filled, "hist_days": len(gdates),
                "hist_days_base": base_days, "kline_days": kline_base, "hist_days_max": cap_days,
                "require_gap": bool(args.require_price_gap),
                "streak_yoy": args.streak_yoy, "streak_max": streak_n,
                "grace_days": grace,
            },
            "sources": ["东方财富（业绩预告/快报/报表）", "新浪财经·腾讯财经（日线行情）"],
        },
        "summary": summary,
        "audit": audit,
        "sectors": sectors,
        "kline": {"dates": gdates, "data": kline_map},
        "candidates": results,
        # 业绩预告池：预告型利润断层但「尚未跳空 / 已回补」，与主清单完全分离
        "pre_pool": pre_pool,
    }
    return payload


def sector_summary(results: list[dict]) -> list[dict]:
    """按东财行业（板块）聚合断层个股。"""
    agg: dict[str, dict] = {}
    for r in results:
        ind = (r.get("industry") or "").strip() or "未标注行业"
        a = agg.setdefault(ind, {"industry": ind, "count": 0, "core": 0, "unfilled": 0,
                                 "growth_sum": 0.0, "growth_n": 0, "gap_sum": 0.0, "gap_n": 0,
                                 "score_sum": 0.0, "stocks": []})
        a["count"] += 1
        if r["tier"].startswith("核心"):
            a["core"] += 1
        g = r.get("gap") or {}
        unfilled = bool(g.get("valid") and not g.get("filled"))
        if unfilled:
            a["unfilled"] += 1
        if r.get("growth") is not None:
            a["growth_sum"] += r["growth"]
            a["growth_n"] += 1
        if g.get("gap_vs_close") is not None:
            a["gap_sum"] += g["gap_vs_close"]
            a["gap_n"] += 1
        a["score_sum"] += r.get("score") or 0
        a["stocks"].append({
            "code": r["code"], "name": r["name"], "score": r.get("score"),
            "growth": r.get("growth"), "gap": g.get("gap_vs_close"),
            "tier": r["tier"], "unfilled": unfilled,
        })
    out = []
    for a in agg.values():
        stocks = sorted(a.pop("stocks"), key=lambda x: -(x.get("score") or 0))
        a["avg_growth"] = round(a.pop("growth_sum") / a["growth_n"], 1) if a["growth_n"] else None
        a.pop("growth_n")
        a["avg_gap"] = round(a.pop("gap_sum") / a["gap_n"], 2) if a["gap_n"] else None
        a.pop("gap_n")
        a["avg_score"] = round(a["score_sum"] / a["count"], 1) if a["count"] else 0
        a["core_ratio"] = round(a["core"] / a["count"] * 100, 0) if a["count"] else 0
        a["leaders"] = stocks[:3]
        out.append(a)
    out.sort(key=lambda x: (-x["core"], -x["count"], -x["avg_score"]))
    return out


# 结果表 / 历史信号库的规范列结构（顺序即输出顺序）
FLAT_COLUMNS = [
    "股票代码", "股票简称", "板块", "行业", "公告日", "数据来源", "报告期",
    "增速能力", "增速口径", "上期增速", "加速度", "连续断层期数", "单季净利(元)",
    "缺口日", "跳空幅度%", "当日涨幅%", "缺口未回补", "持有交易日",
    "缺口后涨幅%", "成交额(元)", "流通市值(亿元)", "低基数",
    "评分", "分层", "标签", "风险", "业绩说明",
]

# 历史版本列结构（按列数识别）。_fit_row 按【列名】把旧行对齐到当前结构，
# 因此这里只需列出该版本「实际有哪些列」，列顺序与插入位置都不再重要。
_LEGACY_COLUMNS: dict[int, list[str]] = {
    # v1.6 及以前：没有「连续断层期数」
    26: [c for c in FLAT_COLUMNS if c != "连续断层期数"],
    # v1.5 及以前：同时没有「流通市值(亿元)」「低基数」
    24: [c for c in FLAT_COLUMNS if c not in ("连续断层期数", "流通市值(亿元)", "低基数")],
}


def _fit_row(rec: list) -> list:
    """把任意历史版本的数据行按列名对齐到当前 FLAT_COLUMNS 结构。"""
    n, m = len(rec), len(FLAT_COLUMNS)
    if n == m:
        return rec
    legacy = _LEGACY_COLUMNS.get(n)
    if legacy:
        pos = {c: i for i, c in enumerate(legacy)}
        return [rec[pos[c]] if (c in pos and pos[c] < n) else "" for c in FLAT_COLUMNS]
    if n < m:
        return rec + [""] * (m - n)
    return rec[:m]


def load_hist(path: str) -> "pd.DataFrame":
    """读取历史信号库，自动兼容旧列结构（表头漂移或行列数不一致时自愈）。"""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rd = csv.reader(f)
        header = next(rd, None) or []
        if header and header != FLAT_COLUMNS:
            log(f"[WARN] 历史信号库表头为旧结构（{len(header)} 列），已按当前 {len(FLAT_COLUMNS)} 列结构归一化")
        rows = [_fit_row(rec) for rec in rd if rec]
    return pd.DataFrame(rows, columns=FLAT_COLUMNS)


def write_outputs(payload: dict, args) -> str:
    stamp = payload["meta"]["scan_date"].replace("-", "")
    jpath = os.path.join(DATA_DIR, f"scan_{stamp}.json")
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    with open(os.path.join(DATA_DIR, "scan_latest.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    # 数据完整性审计单独落盘：不进页面（用户已要求删净解释文案），供 tools/audit_pipeline.py 核验
    audit = payload.get("audit")
    if audit:
        apath = os.path.join(DATA_DIR, f"audit_{stamp}.json")
        with open(apath, "w", encoding="utf-8") as f:
            json.dump(audit, f, ensure_ascii=False, indent=1)
        log(f"输出：{apath}")

    pre = payload.get("pre_pool") or []
    flat = []
    for r in payload["candidates"]:
        g = r.get("gap") or {}
        flat.append({
            "股票代码": r["code"], "股票简称": r["name"], "板块": r["board"], "行业": r.get("industry", ""),
            "公告日": r["announce"], "数据来源": r["source"], "报告期": period_label(r["period"]),
            "增速能力": r.get("growth"), "增速口径": r.get("growth_basis"), "上期增速": r.get("growth_prev"),
            "加速度": r.get("accel"), "连续断层期数": r.get("streak"),
            "单季净利(元)": r.get("np_single"),
            "缺口日": g.get("gap_date"), "跳空幅度%": g.get("gap_vs_close"), "当日涨幅%": g.get("day_chg"),
            "缺口未回补": (not g.get("filled")) if g else None, "持有交易日": g.get("days_held"),
            "缺口后涨幅%": g.get("ret_since_gap"), "成交额(元)": g.get("amount"),
            "流通市值(亿元)": round((g.get("mcap") or 0) / 1e8, 1) if g.get("mcap") else None,
            "低基数": r.get("low_base"),
            "评分": r["score"], "分层": r["tier"], "标签": "|".join(r.get("tags", [])),
            "风险": "|".join(r.get("risks", [])),
            "业绩说明": safe_text(r.get("reason"))[:300],
        })
    cpath = os.path.join(DATA_DIR, f"scan_{stamp}.csv")
    pd.DataFrame(flat, columns=FLAT_COLUMNS).to_csv(cpath, index=False, encoding="utf-8-sig")

    # 预告池单独出一份 CSV：不进「历史信号.csv」（那本是主清单的信号库，混入未跳空个股会污染统计）
    if pre:
        ppath = os.path.join(DATA_DIR, f"预告池_{stamp}.csv")
        pp = []
        for r in pre:
            g = r.get("gap") or {}
            pp.append({
                "股票代码": r["code"], "股票简称": r["name"], "板块": r["board"], "行业": r.get("industry", ""),
                "公告日": r["announce"], "数据来源": r["source"], "报告期": period_label(r["period"]),
                "预告类型": r.get("forecast_type", ""), "增速%": r.get("growth"), "增速口径": r.get("growth_basis"),
                "上期增速": r.get("growth_prev"), "加速度": r.get("accel"),
                "连续断层期数": r.get("streak"),
                "断层强度": r.get("pre_tier", ""), "缺口状态": r.get("gap_state", ""),
                "缺口日": g.get("gap_date"), "跳空幅度%": g.get("gap_vs_close"),
                "缺口已回补": g.get("filled") if g else None,
                "评分": r["score"], "分层": r["tier"],
                "标签": "|".join(r.get("tags", [])), "风险": "|".join(r.get("risks", [])),
                "业绩说明": safe_text(r.get("reason"))[:300],
            })
        pd.DataFrame(pp).to_csv(ppath, index=False, encoding="utf-8-sig")
        log(f"输出：{ppath}（业绩预告池 {len(pp)} 只）")

    hist = os.path.join(DATA_DIR, "历史信号.csv")
    if flat:
        new = pd.DataFrame(flat, columns=FLAT_COLUMNS)
        if os.path.exists(hist):
            try:
                old = load_hist(hist)
                key = ["股票代码", "公告日", "分层"]
                merged = pd.concat([old, new], ignore_index=True)
                merged = merged.drop_duplicates(subset=key, keep="last")
                merged.to_csv(hist, index=False, encoding="utf-8-sig")
            except Exception as e:
                log(f"[WARN] 历史信号库合并失败，改为追加写入：{e}")
                new.to_csv(hist, mode="a", header=False, index=False, encoding="utf-8-sig")
        else:
            new.to_csv(hist, index=False, encoding="utf-8-sig")

    # Markdown 简报
    m = payload["meta"]
    t = m['thresholds']
    lines = [
        f"# 利润断层扫描简报 · {m['scan_date']}",
        "",
        f"- 数据时点：{m['generated_at']}（行情截至 {m['last_trade_date']}，{m['market_status']}）",
        f"- 覆盖报告期：{'、'.join(m['period_labels'])}；公告日期窗口：{m.get('window_label') or (str(m['window_start']) + ' 起 ' + str(m['window_days']) + ' 天')}",
        f"- 判定门槛：净利润增速 {gate_text(t['min_yoy'], '%')}、增速加速度 {gate_text(t['min_accel'], 'pct')}、"
        + (f"跳空 {gate_text(t['min_gap'], '%')}（利润侧不设门槛时，本条件是筛选清单的**唯一**依据）"
           if t['min_yoy'] is None and t['min_accel'] is None else f"跳空 {gate_text(t['min_gap'], '%')}"),
        f"- 连续断层期数口径：单季同比 ≥{t.get('streak_yoy', 20)}% 且单季盈利为「断层期」，最多回溯 {t.get('streak_max', 6)} 个报告期",
        f"- 结果：共 {payload['summary']['total']} 只（核心池 {payload['summary']['core']} / 观察池 {payload['summary']['watch']} / 仅价格缺口 {payload['summary']['price_only']}）",
        f"- 分层口径：核心池·双断层 = 本期净利润同比为正 + 有效跳空；"
        f"跟踪·仅价格缺口 = 业绩未增长（同比 ≤ 0）但出现跳空——利润侧不设门槛后，这一档会明显变大",
        f"- 已剔除缺口回补个股 {payload['summary'].get('dropped_filled', 0)} 只（价格断层失效，已从本页彻底移除，仅保留计数）",
        f"- 已剔除未跳空个股 {payload['summary'].get('dropped_nogap', 0)} 只（公告后无 ≥{t['min_gap']}% 有效跳空，不进入清单）",
        (f"- 数据完整性：行情抓取失败 {payload['audit'].get('fetch_failed', 0)} 只 · "
         f"无行情数据（未上市/停牌）{payload['audit'].get('no_quote', 0)} 只 · "
         f"候选被截断 {payload['audit'].get('truncated_by_max_candidates', 0)} 只 · "
         f"报告期处理失败 {len(payload['audit'].get('failed_periods') or [])} 个 · "
         f"公告日疑似被后续公告刷新 {payload['audit'].get('suspect_ann_total_in_window', 0)} 只"
         if payload.get("audit") else "- 数据完整性：未采集到审计信息"),
        *(["- **完整性告警**：" + "；".join(payload["audit"]["problems"]) + "（本次清单可能不完整，建议重跑）"]
          if (payload.get("audit") or {}).get("problems") else []),
        *([f"- 业绩预告池 {payload['summary']['pre_pool']} 只（已开启 --pre-pool：利润断层成立但尚未跳空 / 已回补）"]
          if payload['summary'].get('pre_pool') else []),
        "",
        "## 断层清单（按评分降序）",
        "",
        "| 代码 | 名称 | 板块 | 公告日 | 来源 | 最新价 | 当日涨幅% | 增速% | 口径 | 加速度 | 连续期数 | 跳空% | 缺口未回补 | 评分 | 分层 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in payload["candidates"][:40]:
        g = r.get("gap") or {}
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            r["code"], r["name"], r["board"], r["announce"], r["source"],
            g.get("last_close", "—"), g.get("day_chg", "—"),
            r.get("growth"), r.get("growth_basis"), r.get("accel"),
            r.get("streak"),
            g.get("gap_vs_close", "—"),
            ("是" if g and not g.get("filled") else ("否" if g else "—")),
            r["score"], r["tier"]))
    pre = payload.get("pre_pool") or []
    if pre:
        s = payload["summary"]
        lines += [
            "",
            "## 业绩预告池（预告型利润断层 · 尚未形成有效价格缺口）",
            "",
            f"- 共 {len(pre)} 只：尚未跳空 {s.get('pre_nogap', 0)} 只、已回补 {s.get('pre_filled', 0)} 只；"
            f"其中口径豁免 {s.get('pre_exempt', 0)} 只（预告缺可比单季/上期数据，按预增/扭亏放行加速度门槛，加速度可能为负）",
            "- 本表不受「必须有有效跳空」约束，只要求利润断层成立；一旦重新跳空且缺口未回补，即移入上方主清单。",
            "",
            "| 代码 | 名称 | 板块 | 行业 | 公告日 | 预告类型 | 增速% | 口径 | 加速度 | 连续期数 | 断层强度 | 缺口状态 | 评分 |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in pre[:20]:
            lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                r["code"], r["name"], r["board"], r.get("industry", ""), r["announce"],
                r.get("forecast_type", "—"), r.get("growth"), r.get("growth_basis"),
                r.get("accel"), r.get("streak"), r.get("pre_tier", "—"),
                r.get("gap_state", "—"), r["score"]))

    lines += ["", "> 本简报仅供研究参考，不构成个人投资建议。"]
    mpath = os.path.join(DATA_DIR, f"简报_{stamp}.md")
    with open(mpath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log(f"输出：{jpath}")
    return jpath


def main():
    ap = argparse.ArgumentParser(description="利润断层扫描")
    ap.add_argument("--days", type=int, default=None,
                    help="公告窗口退回「今天往前 N 天」的滚动模式（窄窗盯盘用）。"
                         "**不传则默认按报告期覆盖**：各报告期用自己的法定披露季做窗口，"
                         "不会因为「今天往前 N 天」从披露季中间切断而静默漏掉个股")
    ap.add_argument("--period", type=str, default=None, help="指定报告期 YYYYMMDD")
    ap.add_argument("--min-yoy", type=str, default="off",
                    help="净利润增速门槛（%%）：数值如 50，或 off/none/不设 表示不设门槛（默认 off）")
    ap.add_argument("--min-accel", type=str, default="off",
                    help="增速加速度门槛（百分点）：数值如 20，或 off/none/不设 表示不设门槛"
                         "（默认 off —— 利润侧不设门槛，只按价格跳空筛选）")
    ap.add_argument("--min-gap", type=float, default=DEFAULTS["min_gap"])
    ap.add_argument("--min-score", type=float, default=DEFAULTS["min_score"])
    ap.add_argument("--min-np", type=float, default=0.0, help="单季净利润下限（元），0 为不限")
    ap.add_argument("--min-mcap", type=float, default=0.0, help="流通市值下限（元），0 为不限")
    ap.add_argument("--boards", type=str, default=DEFAULTS["boards"])
    ap.add_argument("--exclude-st", action="store_true", default=DEFAULTS["exclude_st"])
    ap.add_argument("--keep-st", action="store_true",
                    help="保留名称含 ST / 退 的个股（默认剔除；此前 --exclude-st 恒为真、无法关闭）")
    ap.add_argument("--max-candidates", type=int, default=DEFAULTS["max_candidates"],
                    help="安全阀：超过此数会告警（**不再截断**，因为截断等于静默漏票）。0 = 不限")
    ap.add_argument("--grace-days", type=int, default=REFRESH_GRACE_DAYS,
                    help="公告日刷新宽限（天）：东财「最新公告日期」会被后续公告覆盖，"
                         "窗口上界放宽到 法定披露截止 + 本值，避免 8 月底披露、9 月发过"
                         f"更正公告的个股被静默丢掉（默认 {REFRESH_GRACE_DAYS}）")
    ap.add_argument("--window-back", type=int, default=None,
                    help="窗口下界：不传（默认）= 上一报告期结束日，即「本期披露季的起点」；"
                         "传 N = 期末 − N 天。下界过小会把「远早于报告期结束就发预告」的个股"
                         "整批丢掉（实测 2026 三季报有 8 只 8 月末即预告的次新股落在 期末−20 之外）")
    ap.add_argument("--fin-cache", action="store_true",
                    help="复用财报缓存。**默认不复用**：窗口内报告期每次强制重抓，"
                         "否则复用当天上午的快照会漏掉当晚盘后披露的全部公告")
    ap.add_argument("--workers", type=int, default=5, help="行情抓取进程数（V8 不线程安全，用多进程）")
    ap.add_argument("--hist-days", type=int, default=DEFAULTS["hist_days"],
                    help="阶段一缺口判定窗口（全部候选都抓，别调太大）")
    ap.add_argument("--kline-days", type=int, default=DEFAULTS["kline_days"],
                    help="阶段二 K 线最低回溯交易日数（只对最终保留的个股抓）")
    ap.add_argument("--hist-days-max", type=int, default=DEFAULTS["hist_days_max"],
                    help="K 线回溯上限：连续断层越多的个股最多回溯到这里")
    ap.add_argument("--keep-filled", action="store_true", help="保留缺口已回补的个股（默认剔除）")
    ap.add_argument("--allow-no-gap", action="store_true",
                    help="保留未出现有效跳空的个股（默认剔除，仅保留跳空 ≥ min_gap 的个股）")
    ap.add_argument("--pre-pool", action="store_true",
                    help="额外生成「业绩预告池」（利润断层成立但尚未跳空 / 已回补的预告股）。"
                         "v1.12 起默认关闭：利润侧已不设门槛，开启会让未跳空的预告混进清单")
    ap.add_argument("--streak-max", type=int, default=DEFAULTS["streak_max"],
                    help="「连续断层期数」最多回看的报告期数（默认 6）")
    ap.add_argument("--streak-yoy", type=float, default=DEFAULTS["streak_yoy"],
                    help="判定单期为「断层期」的单季同比门槛（%%），默认 20")
    ap.add_argument("--track", action="store_true", help="附带历史信号跟踪")
    args = ap.parse_args()
    args.min_yoy = parse_gate(args.min_yoy)
    args.min_accel = parse_gate(args.min_accel)
    args.require_price_gap = bool(DEFAULTS["require_price_gap"] and not args.allow_no_gap)
    args.exclude_st = bool(DEFAULTS["exclude_st"] and not args.keep_st)

    payload = scan(args)
    jpath = write_outputs(payload, args)
    log(f"完成：{payload['summary']['total']} 只断层候选（核心 {payload['summary']['core']}）")
    print(jpath)

    # 发现问题就**以非 0 退出码结束**：产物已经落盘，但定时任务/脚本必须能感知到
    # 「本次清单可能不完整」。静默通过是这类 bug 能潜伏至今的根本原因。
    problems = (payload.get("audit") or {}).get("problems") or []
    if problems:
        log("[FATAL] 数据完整性检查未通过：" + "；".join(problems))
        sys.exit(3)
    sys.exit(0)


if __name__ == "__main__":
    main()
