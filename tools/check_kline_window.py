#!/usr/bin/env python
"""K 线回溯窗口 + 历史各期断层自检：核对 payload 结构、各股轴偏移、体积收益与公告日合理性。

用法：python tools/check_kline_window.py
"""
import datetime as dt
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
J = os.path.join(ROOT, "data", "scan_latest.json")
H = os.path.join(ROOT, "利润断层工作台.html")


def period_bounds(period: str) -> tuple[dt.date, dt.date]:
    """与引擎一致的公告日合理区间：期末 − 20 天 → 期末 + 200 天。"""
    y, m, d = int(period[:4]), int(period[4:6]), int(period[6:8])
    e = dt.date(y, m, d)
    return e - dt.timedelta(days=20), e + dt.timedelta(days=200)


def main() -> int:
    d = json.load(open(J, encoding="utf-8"))
    kl = d.get("kline") or {}
    dates = kl.get("dates") or []
    data = kl.get("data") or {}
    th = (d.get("meta") or {}).get("thresholds") or {}
    bad = []

    print(f"全局日期轴: {len(dates)} 个交易日  {dates[0] if dates else '-'} → {dates[-1] if dates else '-'}")
    print(f"K 线条数:   {len(data)}   阈值: base={th.get('kline_days')} max={th.get('hist_days_max')} "
          f"axis={th.get('hist_days')} 阶段一窗口={th.get('hist_days_base')}")

    if th.get("hist_days") != len(dates):
        bad.append("meta.thresholds.hist_days 与 dates 长度不一致")
    if (th.get("kline_days") or 0) < 250:
        bad.append(f"kline_days={th.get('kline_days')} 过小，K 线往前拖不了多远")
    if len(dates) < 200:
        bad.append(f"全局日期轴只有 {len(dates)} 个交易日，不足以复盘历史断层")

    lens, legacy = {}, 0
    for code, v in data.items():
        if isinstance(v, dict):
            bars, d0 = v.get("bars") or [], int(v.get("d0") or 0)
        else:                                    # 旧格式：与全局轴等长的裸数组
            legacy += 1
            bars, d0 = v, 0
        if not bars:
            bad.append(f"{code} bars 为空")
            continue
        if d0 < 0 or d0 + len(bars) > len(dates):
            bad.append(f"{code} d0 越界：d0={d0} len={len(bars)} axis={len(dates)}")
        if bars[0] is None or bars[-1] is None:
            bad.append(f"{code} 首/末根为 null（应已裁掉首尾空档）")
        lens[code] = len(bars)

    vals = sorted(lens.values())
    total = sum(vals)
    filled = len(data) * len(dates)
    print(f"bars 长度:  min={vals[0]}  中位={int(statistics.median(vals))}  max={vals[-1]}  合计={total}")
    print(f"体积收益:   若每只都补齐到全局轴 → {filled} 条，实际 {total} 条（省 {1 - total / filled:.0%}）")
    print(f"旧格式条数: {legacy}（应为 0）")
    if legacy:
        bad.append("仍有旧格式（裸数组）K 线数据")

    # 连续断层越多的个股，回溯应越长
    rows = d.get("candidates") or []
    deep = [r for r in rows if (r.get("streak") or 0) >= 2 and lens.get(r["code"])]
    kbase = th.get("kline_days") or th.get("hist_days_base") or 0
    if deep:
        top = max(deep, key=lambda r: r["streak"])
        print(f"最长连续:   {top['code']} {top['name']} streak={top['streak']} "
              f"bars={lens[top['code']]} 起={dates[int(data[top['code']]['d0'])]} "
              f"止={dates[int(data[top['code']]['d0']) + lens[top['code']] - 1]}")
        if lens[top["code"]] <= kbase:
            bad.append(f"连续断层 {top['streak']} 期的个股 K 线未加长（{lens[top['code']]} ≤ base {kbase}）")
    else:
        bad.append("清单里找不到连续 ≥2 期的个股，无法验证按起点加长")

    # ---- 历史各期断层（period_gaps）----
    tot_pg = valid_pg = multi = 0
    inferred = 0
    out_of_axis = []
    for r in rows:
        pgs = [x for x in (r.get("period_gaps") or []) if x]
        if len(pgs) >= 2:
            multi += 1
        for x in pgs:
            tot_pg += 1
            valid_pg += 1 if x.get("valid") else 0
            inferred += 1 if x.get("inferred") else 0
            per = x.get("period") or ""
            if len(per) == 8:
                lo, hi = period_bounds(per)
                a = x.get("ann")
                if a:
                    ad = dt.date.fromisoformat(a[:10])
                    if not (lo <= ad <= hi):
                        bad.append(f"{r['code']} {x.get('label')} 公告日越界：{a} ∉ [{lo}, {hi}]")
            if x.get("valid") and not x.get("gap_date"):
                bad.append(f"{r['code']} {x.get('label')} 标为有效跳空却缺 gap_date")
            if x.get("gap_date") and (x["gap_date"] < (dates[0] if dates else "") or
                                      x["gap_date"] > (dates[-1] if dates else "")):
                out_of_axis.append(f"{r['code']} {x.get('label')} {x['gap_date']}")
    print(f"历史期断层: 期次合计={tot_pg}（含本期）多期个股={multi} 有效跳空={valid_pg} 反推锚点={inferred}")
    print(f"摘要对账:   summary.gap_series={(d.get('summary') or {}).get('gap_series')} "
          f"gap_multi={(d.get('summary') or {}).get('gap_multi')}")
    if multi == 0:
        bad.append("没有任何个股带 ≥2 期断层，历史断层叠加无从验证")
    if (d.get("summary") or {}).get("gap_series") != valid_pg:
        bad.append("summary.gap_series 与 payload 实际有效跳空期次不一致")
    if out_of_axis:
        print(f"注意: {len(out_of_axis)} 条跳空日落在全局日期轴之外（窗口裁剪，属正常边界）")

    if base := kbase:
        short = [c for c, n in lens.items() if n < base - 40]
        if short:
            print(f"注意: {len(short)} 只个股 K 线短于 base（次新股/停牌，属正常边界）")

    hsize = os.path.getsize(H) / 1024 if os.path.exists(H) else 0
    jsize = os.path.getsize(J) / 1024
    print(f"文件体积:   看板 {hsize:.0f} KB | JSON {jsize:.0f} KB")

    print("❌ 未通过：" + "；".join(bad) if bad else "✅ K 线窗口 & 历史断层自检通过")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
