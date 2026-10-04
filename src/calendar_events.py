#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
个人投资工作台 · 投资日历事件抓取
=================================
抓 A 股投资事件，输出 data/calendar_events.json 供 src/build_home.py 渲染。

事件类型（5 类来源）：
  1. 财报披露  —— 东财「预约披露时间」（RPT_PUBLIC_BS_APPOIN）。**不走 akshare**：
                 akshare 1.18.64 的 stock_yysj_em 列名映射过时，会抛
                 "Length mismatch: Expected axis has 29 elements, new values have 22"。
                 直接调 datacenter-web 并分页即可（实测 5222 条 / 11 页）。
  2. 分红除权  —— akshare stock_fhps_em（股权登记日 / 除权除息日）
  3. 限售解禁  —— akshare stock_restricted_release_detail_em（个股明细，非市场汇总）
  4. 新股申购  —— akshare stock_xgsglb_em（申购日期 / 上市日期）
  5. 经济数据  —— akshare news_economic_baidu（按天抓，日历窗口内逐日）

⚠️ 沿用本项目「无静默丢数」约定：
  - 每个来源独立 try/except + 重试，结果记进 sources[].status（ok / empty / error）；
  - 任一「整批型」来源 error → problems → 退出码 3（云端据此不提交、保留上一版页面）；
  - 经济数据是「逐日型」，单日偶发失败不算整批失败：失败比例 > 20% 才升格为 problems，
    否则记 degraded 并把失败日列出来 —— 不隐瞒，但也不因一天抽风就整轮白跑。

用法：
  python src/calendar_events.py                  # 默认窗口 今天−45天 ~ 今天+75天
  python src/calendar_events.py --back 30 --ahead 60
  python src/calendar_events.py --no-macro        # 跳过经济数据（快，用于调试）
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import traceback

import requests

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "cache")
OUT = os.path.join(ROOT, "data", "calendar_events.json")

EM_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Safari/537.36"}

RETRY = 3
RETRY_SLEEP = 2.0
PAGE_SIZE = 500
MACRO_FAIL_RATIO = 0.20      # 经济数据单日失败比例上限
MACRO_MIN_IMPORTANCE = 2     # 百度财经日历的重要性只有 1/2 两档；取 2 = 「重要」
MACRO_CACHE_TTL_PAST = 7.0   # 过去日期的宏观日历不会再变，缓存 7 天
MACRO_CACHE_TTL_SOON = 0.25  # 今天/未来：6 小时内可能更新（预期值会变）

# 事件类型表：JSON 里事件只存下标 t，省体积
TYPES = ["财报披露", "分红除权", "股权登记", "限售解禁", "新股申购", "新股上市", "经济数据"]
T = {name: i for i, name in enumerate(TYPES)}


def log(msg: str) -> None:
    print(msg, flush=True)


class NoData(Exception):
    """数据源**明确表示**「该期还没有数据」——正常空，不是失败。
    必须与「接口异常」区分开（本项目「三态显式三值」约定）：
    年报在 10 月还没开始预约披露，东财会回 code=9201「返回数据为空」，
    这是预期内的空，不能记成 error、更不能让整轮退出码变 3。"""


def s(v) -> str:
    """把 pandas/None/NaN 一律转成干净字符串，绝不出现 'nan' / 'NaT'。"""
    if v is None:
        return ""
    if pd is not None:
        try:
            if pd.isna(v):
                return ""
        except Exception:
            pass
    if isinstance(v, (dt.datetime, dt.date)):
        return v.strftime("%Y-%m-%d")
    t = str(v).strip()
    if t in ("nan", "NaT", "None", "-", "--", "NoneType"):
        return ""
    return t


def d10(v) -> str:
    """取 YYYY-MM-DD 部分（东财常带 00:00:00 或 时间戳）。"""
    t = s(v)
    if not t:
        return ""
    if " " in t:
        t = t.split(" ")[0]
    if t.endswith("00:00:00"):
        t = t[:10]
    return t[:10] if len(t) >= 10 else ""


def retry(fn, what: str, n: int = RETRY):
    """重试包装：返回 (结果, 错误字符串)。错误不吞，交回调用方登记。
    NoData（数据源明确说没数据）不重试、直接抛给调用方。"""
    last = ""
    for i in range(n):
        try:
            return fn(), ""
        except NoData:
            raise
        except Exception as e:  # noqa: BLE001 —— 故意兜住所有异常，但要登记
            last = f"{type(e).__name__}: {e}"
            if i < n - 1:
                log(f"    [retry {i + 1}/{n - 1}] {what}：{last}")
                time.sleep(RETRY_SLEEP * (i + 1))
    return None, last


# --------------------------------------------------------------------------
# 1. 财报披露（东财预约披露时间，直接调接口，绕开 akshare 的列名 bug）
# --------------------------------------------------------------------------
def fetch_disclosure(win_start: dt.date, win_end: dt.date, problems: list) -> tuple:
    periods = _periods_in_window(win_start, win_end)
    rows, errs, notes = [], [], []
    for p in periods:
        date_str = p.strftime("%Y-%m-%d")
        acc, page = [], 1
        while True:
            params = {
                "sortColumns": "FIRST_APPOINT_DATE,SECURITY_CODE",
                "sortTypes": "1,1",
                "pageSize": str(PAGE_SIZE),
                "pageNumber": str(page),
                "reportName": "RPT_PUBLIC_BS_APPOIN",
                "columns": "ALL",
                "filter": ('(SECURITY_TYPE_CODE in ("058001001","058001008"))'
                           '(TRADE_MARKET_CODE!="069001017")'
                           f"(REPORT_DATE='{date_str}')"),
            }

            def _one(params=params):
                r = requests.get(EM_URL, params=params, timeout=25, headers=UA)
                r.raise_for_status()
                j = r.json()
                if not j.get("success", True):
                    msg = str(j.get("message") or "")
                    # 「返回数据为空」= 该期还没开始预约披露，属正常空，不是失败
                    if j.get("code") in (9201, 9202) or "为空" in msg or "无数据" in msg:
                        raise NoData(msg or "返回数据为空")
                    raise RuntimeError(f"东财返回 success=False: {str(j)[:160]}")
                res = j.get("result") or {}
                return res.get("data") or [], res.get("count")

            try:
                got, err = retry(_one, f"预约披露 {date_str} 第{page}页")
            except NoData as e:
                notes.append(f"{date_str}：东财无该期预约数据（{e}），视为正常空")
                break
            if err:
                errs.append(f"{date_str} 第{page}页: {err}")
                break
            data, count = got
            acc.extend(data)
            if not data or len(acc) >= (count or 0):
                break
            page += 1

        for d in acc:
            ann = d10(d.get("APPOINT_PUBLISH_DATE")) or d10(d.get("FIRST_APPOINT_DATE"))
            act = d10(d.get("ACTUAL_PUBLISH_DATE"))
            day = act or ann
            if not day or not (win_start.isoformat() <= day <= win_end.isoformat()):
                continue
            rname = s(d.get("REPORT_TYPE_NAME")) or _period_label(p)
            detail = f"{rname}{'实际披露' if act else '预约披露'}"
            if not act and ann and d10(d.get("FIRST_APPOINT_DATE")) and ann != d10(d.get("FIRST_APPOINT_DATE")):
                detail += f"（原定 {d10(d.get('FIRST_APPOINT_DATE'))}）"
            rows.append({"d": day, "t": T["财报披露"],
                         "c": s(d.get("SECURITY_CODE")), "n": s(d.get("SECURITY_NAME_ABBR")),
                         "x": detail,
                         "b": s(d.get("BOARD_NAME")) or s(d.get("TRADE_MARKET"))})
    if errs:
        problems.append("财报披露：接口异常 " + "；".join(errs[:4]))
    return rows, errs, notes


def _periods_in_window(ws: dt.date, we: dt.date) -> list:
    """窗口可能覆盖两个报告期的预约披露季（如 8 月末半年报 + 10 月三季报）。"""
    ends = []
    for y in (ws.year - 1, ws.year, ws.year + 1):
        for m, dd in ((3, 31), (6, 30), (9, 30), (12, 31)):
            try:
                ends.append(dt.date(y, m, dd))
            except ValueError:
                pass
    out = []
    for e in ends:
        if e - dt.timedelta(days=20) <= we and e + dt.timedelta(days=210) >= ws:
            out.append(e)
    return sorted(set(out))


def _period_label(p: dt.date) -> str:
    return {3: "一季报", 6: "半年报", 9: "三季报", 12: "年报"}.get(p.month, "财报")


# --------------------------------------------------------------------------
# 2. 分红除权（akshare stock_fhps_em）
# --------------------------------------------------------------------------
def fetch_dividend(win_start: dt.date, win_end: dt.date, problems: list) -> tuple:
    import akshare as ak
    rows, errs = [], []
    for p in _recent_periods(win_start, 4):
        got, err = retry(lambda p=p: ak.stock_fhps_em(date=p.strftime("%Y%m%d")),
                         f"分红送配 {p:%Y%m%d}")
        if err:
            errs.append(f"{p:%Y%m%d}: {err}")
            continue
        df = got
        if df is None or len(df) == 0:
            continue
        for _, r in df.iterrows():
            code, name = s(r.get("代码")), s(r.get("名称"))
            plan = _plan_text(r)
            reg, ex = d10(r.get("股权登记日")), d10(r.get("除权除息日"))
            if reg and win_start.isoformat() <= reg <= win_end.isoformat():
                rows.append({"d": reg, "t": T["股权登记"], "c": code, "n": name, "x": plan})
            if ex and win_start.isoformat() <= ex <= win_end.isoformat():
                rows.append({"d": ex, "t": T["分红除权"], "c": code, "n": name, "x": plan})
    if errs:
        problems.append("分红除权：接口异常 " + "；".join(errs[:4]))
    return rows, errs, []


def _plan_text(r) -> str:
    parts = []
    cash = r.get("现金分红-现金分红比例")
    if s(cash):
        parts.append(f"10派{cash}元")
    total = r.get("送转股份-送转总比例")
    if s(total):
        parts.append(f"10送转{total}股")
    if not parts:
        return s(r.get("方案进度")) or "分红送配"
    prog = s(r.get("方案进度"))
    return "，".join(parts) + (f"（{prog}）" if prog else "")


def _recent_periods(ref: dt.date, n: int) -> list:
    ends, y = [], ref.year
    for yy in (y, y - 1, y - 2):
        for m, dd in ((12, 31), (9, 30), (6, 30), (3, 31)):
            ends.append(dt.date(yy, m, dd))
    ends = sorted([e for e in ends if e <= ref], reverse=True)
    return ends[:n]


# --------------------------------------------------------------------------
# 3. 限售解禁（akshare 个股明细）
# --------------------------------------------------------------------------
def fetch_restricted(win_start: dt.date, win_end: dt.date, problems: list) -> tuple:
    import akshare as ak
    got, err = retry(lambda: ak.stock_restricted_release_detail_em(
        start_date=win_start.strftime("%Y%m%d"), end_date=win_end.strftime("%Y%m%d")),
        "限售解禁明细")
    if err:
        problems.append(f"限售解禁：接口异常 {err}")
        return [], [err], []
    df = got
    if df is None:
        problems.append("限售解禁：接口返回 None")
        return [], ["None"], []
    rows = []
    for _, r in df.iterrows():
        day = d10(r.get("解禁时间"))
        if not day or not (win_start.isoformat() <= day <= win_end.isoformat()):
            continue
        kind = s(r.get("限售股类型"))
        mv = r.get("实际解禁市值")
        try:
            mv_txt = f"{float(mv) / 1e8:.2f}亿" if s(mv) else ""
        except Exception:
            mv_txt = ""
        ratio = s(r.get("占解禁前流通市值比例"))
        try:
            ratio_txt = f"占流通 {float(ratio) * 100:.2f}%" if ratio else ""
        except Exception:
            ratio_txt = ""
        detail = "，".join([x for x in (kind, mv_txt and f"解禁市值 {mv_txt}", ratio_txt) if x])
        rows.append({"d": day, "t": T["限售解禁"], "c": s(r.get("股票代码")),
                     "n": s(r.get("股票简称")), "x": detail})
    return rows, [], []


# --------------------------------------------------------------------------
# 4. 新股申购 / 上市（akshare）
# --------------------------------------------------------------------------
def fetch_ipo(win_start: dt.date, win_end: dt.date, problems: list) -> tuple:
    import akshare as ak
    got, err = retry(lambda: ak.stock_xgsglb_em(symbol="全部股票"), "新股申购与中签")
    if err:
        problems.append(f"新股申购：接口异常 {err}")
        return [], [err], []
    df = got
    if df is None:
        problems.append("新股申购：接口返回 None")
        return [], ["None"], []
    rows = []
    for _, r in df.iterrows():
        code, name = s(r.get("股票代码")), s(r.get("股票简称"))
        board = s(r.get("板块"))
        price = s(r.get("发行价格"))
        sub, lst = d10(r.get("申购日期")), d10(r.get("上市日期"))
        if sub and win_start.isoformat() <= sub <= win_end.isoformat():
            rows.append({"d": sub, "t": T["新股申购"], "c": code, "n": name,
                         "x": "，".join([x for x in (board, price and f"发行价 {price}元") if x])})
        if lst and win_start.isoformat() <= lst <= win_end.isoformat():
            rows.append({"d": lst, "t": T["新股上市"], "c": code, "n": name,
                         "x": "，".join([x for x in (board, price and f"发行价 {price}元") if x])})
    return rows, [], []


# --------------------------------------------------------------------------
# 5. 经济数据（akshare 百度财经日历，逐日）
# --------------------------------------------------------------------------
def fetch_macro(win_start: dt.date, win_end: dt.date, problems: list,
                workers: int = 1) -> tuple:
    import akshare as ak
    os.makedirs(CACHE, exist_ok=True)
    days, d = [], win_start
    while d <= win_end:
        days.append(d)
        d += dt.timedelta(days=1)
    rows, failed = [], []
    for day in days:
        key = day.strftime("%Y%m%d")
        path = os.path.join(CACHE, f"cal_macro_{key}.json")
        ttl = MACRO_CACHE_TTL_PAST if day < dt.date.today() else MACRO_CACHE_TTL_SOON
        if os.path.exists(path):
            try:
                if (time.time() - os.path.getmtime(path)) < ttl * 86400:
                    rows.extend(json.load(open(path, encoding="utf-8")))
                    continue
            except Exception:
                pass
        got, err = retry(lambda day=day: ak.news_economic_baidu(date=day.strftime("%Y%m%d")),
                         f"经济日历 {day}", n=2)
        if err:
            failed.append(f"{day}:{err.split(':')[0]}")
            continue
        df = got
        bucket = []
        if df is not None and len(df):
            for _, r in df.iterrows():
                try:
                    imp = int(float(s(r.get("重要性")) or 0))
                except Exception:
                    imp = 0
                if imp < MACRO_MIN_IMPORTANCE:
                    continue
                bucket.append({"d": d10(r.get("日期")) or day.isoformat(), "t": T["经济数据"],
                               "c": "", "n": s(r.get("事件")),
                               "x": _macro_detail(r), "i": imp,
                               "r": s(r.get("地区")), "tm": s(r.get("时间"))})
        rows.extend(bucket)
        try:
            json.dump(bucket, open(path, "w", encoding="utf-8"), ensure_ascii=False)
        except Exception:
            pass
    ratio = (len(failed) / len(days)) if days else 0.0
    notes = []
    if ratio > MACRO_FAIL_RATIO:
        problems.append(f"经济数据：{len(failed)}/{len(days)} 天抓取失败（{ratio:.0%}）")
    elif failed:
        notes.append(f"{len(failed)}/{len(days)} 天抓取失败（未超 {MACRO_FAIL_RATIO:.0%} 阈值，已跳过）")
        log(f"    [warn] 经济数据 {len(failed)}/{len(days)} 天失败（未超阈值）：{failed[:6]}")
    return rows, [], notes


def _macro_detail(r) -> str:
    pub, exp, prev = s(r.get("公布")), s(r.get("预期")), s(r.get("前值"))
    parts = []
    if pub:
        parts.append(f"公布 {pub}")
    if exp:
        parts.append(f"预期 {exp}")
    if prev:
        parts.append(f"前值 {prev}")
    return "，".join(parts) or "待公布"


# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--back", type=int, default=45, help="窗口往前天数（默认 45）")
    ap.add_argument("--ahead", type=int, default=75, help="窗口往后天数（默认 75）")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--no-macro", action="store_true", help="跳过经济数据（调试用）")
    args = ap.parse_args()

    today = dt.date.today()
    ws, we = today - dt.timedelta(days=args.back), today + dt.timedelta(days=args.ahead)
    log(f"[1] 窗口 {ws} ~ {we}（今天 {today}）")

    problems: list = []
    sources: list = []
    events: list = []

    jobs = [
        ("财报披露", lambda: fetch_disclosure(ws, we, problems)),
        ("分红除权", lambda: fetch_dividend(ws, we, problems)),
        ("限售解禁", lambda: fetch_restricted(ws, we, problems)),
        ("新股申购", lambda: fetch_ipo(ws, we, problems)),
    ]
    if not args.no_macro:
        jobs.append(("经济数据", lambda: fetch_macro(ws, we, problems)))

    for name, fn in jobs:
        t0 = time.time()
        notes = []
        try:
            rows, errs, notes = fn()
            status = "error" if errs else ("ok" if rows else "empty")
        except Exception as e:  # noqa: BLE001 —— 单来源崩了不能拖垮整轮，但要登记
            rows, errs, status = [], [f"{type(e).__name__}: {e}"], "error"
            problems.append(f"{name}：抓取异常 {errs[0][:160]}")
            log("    " + traceback.format_exc().strip().split("\n")[-1])
        events.extend(rows)
        sources.append({"name": name, "status": status, "rows": len(rows),
                        "errors": errs[:5], "notes": notes[:5], "sec": round(time.time() - t0, 1)})
        log(f"    {name}: {status}  {len(rows)} 条  {time.time() - t0:.1f}s"
            + (f"  错误 {errs[0][:90]}" if errs else ""))

    events.sort(key=lambda e: (e["d"], e["t"], e.get("c", "")))
    log(f"[2] 事件合计 {len(events)} 条")

    payload = {
        "meta": {
            "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "today": today.isoformat(),
            "window_start": ws.isoformat(),
            "window_end": we.isoformat(),
            "types": TYPES,
        },
        "sources": sources,
        "problems": problems,
        "events": events,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    log(f"[3] 已写出 {args.out}（{os.path.getsize(args.out) / 1024:.0f} KB）")

    if problems:
        log("[!] 完整性问题：")
        for p in problems:
            log("    - " + p)
        return 3
    log("[✓] 全部来源正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
