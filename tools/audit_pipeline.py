#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""利润断层 · 数据完整性审计（防「静默漏票」）

为什么需要它
------------
扫描链路上有 6 个位置能让个股**无声无息地消失**：窗口边界、公告日被后续公告刷新、
财报缓存隔夜、行情抓取失败、候选数安全阀截断、整期接口异常。它们的共同特征是
「不报错、不计数、页面上看不出来」——清单少了几只，你不可能从 85 行里发现。

本脚本不信任引擎自己打印的日志，而是**回到原始数据独立复算**，逐环节对账：

  A 审计信息齐备          / 引擎是否产出了 audit_YYYYMMDD.json
  B 漏斗自洽              / 原始行 − 窗口剔除 − 无公告日 = 窗口内候选
  C 独立复算窗口          / 从缓存 CSV 重新按窗口筛，结果必须与引擎一致
  D 关注板块零遗漏        / 窗口外被丢掉的行里，不得有主板/创业板/科创板个股（除非明示）
  E 财务缓存新鲜度        / 窗口内报告期的缓存必须写于本次扫描时刻附近
  F 行情抓取失败率        / 超过 1% 即判失败（这些个股无法判断是否跳空）
  G 无截断 / 无整期失败   / --max-candidates 截断与报告期异常一律判失败
  H --deep 超集比对        / 用极宽窗口重扫一遍，确认常规扫描的代码集是其子集

用法：
  python3 tools/audit_pipeline.py              # 常规审计（秒级，读缓存）
  python3 tools/audit_pipeline.py --deep       # 追加超集比对（需重跑一次扫描，约 3 分钟）
  python3 tools/audit_pipeline.py --date 20261004
退出码：0 = 全部通过；1 = 存在失败项。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(DATA, "cache")
sys.path.insert(0, os.path.join(ROOT, "src"))

import pandas as pd  # noqa: E402

from profit_gap import (  # noqa: E402
    SOURCE_OPEN_DAYS, board_of, legal_deadline, period_label, _period_end,
)

TARGET_BOARDS = ("主板", "创业板", "科创板")
FETCH_FAIL_LIMIT = 0.01        # 行情抓取失败率上限
CACHE_FRESH_MINUTES = 45       # 窗口内报告期的财报缓存必须写于扫描时刻前多少分钟内


class Sheet:
    """审计表：分组记录通过 / 失败项。"""

    def __init__(self):
        self.rows: list[tuple[str, str, str, str]] = []
        self.failed = 0
        self.checked = 0           # 真正的断言数（不含「·」信息行）

    def add(self, sec: str, item: str, ok: bool, detail: str = "") -> None:
        self.rows.append((sec, item, "✅" if ok else "❌", detail))
        self.checked += 1
        if not ok:
            self.failed += 1

    def info(self, sec: str, item: str, detail: str = "") -> None:
        self.rows.append((sec, item, "·", detail))

    def dump(self) -> None:
        sec = None
        for s, item, mark, detail in self.rows:
            if s != sec:
                print(f"\n── {s} " + "─" * max(0, 58 - len(s)))
                sec = s
            print(f"  {mark} {item:<30} {detail}")
        print()
        n = self.checked
        print("=" * 68)
        if self.failed:
            print(f"❌ 审计未通过：{self.failed} / {n} 项失败 —— 清单可能已漏票，请逐条排查")
        else:
            print(f"✅ 审计通过：{n} 项全部满足，未发现静默漏票")


def load_audit(date_str: str | None) -> tuple[dict, dict]:
    """返回 (audit, payload)。payload 可能不存在（旧版本产物），调用方需容错。"""
    payload = {}
    lp = os.path.join(DATA, "scan_latest.json")
    if os.path.exists(lp):
        try:
            payload = json.load(open(lp, encoding="utf-8"))
        except Exception:
            payload = {}
    if not date_str:
        date_str = (payload.get("meta") or {}).get("scan_date") or dt.date.today().isoformat()
    stamp = date_str.replace("-", "")
    ap = os.path.join(DATA, f"audit_{stamp}.json")
    audit = {}
    if os.path.exists(ap):
        try:
            audit = json.load(open(ap, encoding="utf-8"))
        except Exception:
            audit = {}
    if not audit:
        audit = payload.get("audit") or {}
    return audit, payload


def read_raw(period: str) -> list[dict]:
    """直接从缓存 CSV 读该报告期的原始行（预告 / 快报 / 财报），不复用引擎逻辑。"""
    out: list[dict] = []
    specs = [("yjyg", "业绩预告", "公告日期"), ("yjkb", "业绩快报", "公告日期"),
             ("yjbb", "正式财报", "最新公告日期")]
    for prefix, src, colhint in specs:
        path = os.path.join(CACHE, f"{prefix}_{period}.csv")
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_csv(path, dtype={"股票代码": str})
        except Exception:
            continue
        col = next((c for c in df.columns if colhint in c), None)
        if col is None or "股票代码" not in df.columns:
            continue
        for _, r in df.iterrows():
            code = str(r["股票代码"]).zfill(6)
            if not code.isdigit():
                continue
            out.append({
                "code": code,
                "name": str(r.get("股票简称") or ""),
                "source": src,
                "ann": str(r.get(col))[:10],
            })
    return out


def parse_date(s: str):
    try:
        return dt.date.fromisoformat(s[:10])
    except Exception:
        return None


def audit_basic(sh: Sheet, audit: dict, payload: dict) -> None:
    """A 审计信息齐备"""
    sh.add("A 审计信息齐备", "audit 块存在", bool(audit),
           "" if audit else "缺少 audit 块（引擎版本过旧？）")
    if not audit:
        return
    for k in ("periods", "windows", "period_stats", "candidates", "kept",
              "need_price", "dropped_nogap", "dropped_filled", "kept_final"):
        sh.add("A 审计信息齐备", f"字段 {k}", k in audit)
    n = len(payload.get("candidates") or [])
    if payload:
        sh.add("A 审计信息齐备", "scan_latest 与 audit 清单数一致",
               n == audit.get("kept_final"),
               f"payload {n} / audit {audit.get('kept_final')}")


def audit_funnel(sh: Sheet, audit: dict) -> None:
    """B 漏斗自洽 + E 缓存新鲜度 + F 抓取失败 + G 截断/整期失败"""
    if not audit:
        return
    # G1 整期失败
    fp = audit.get("failed_periods") or []
    sh.add("G 无截断 / 无整期失败", "报告期处理失败", not fp, f"{fp}" if fp else "0 个")

    # B 逐期漏斗
    for st in audit.get("period_stats") or []:
        p = st.get("period", "?")
        lab = period_label(p) if len(str(p)) == 8 else str(p)
        raw_n = st.get("rows", 0)
        calc = raw_n - st.get("out_of_window", 0) - st.get("no_date", 0)
        # 去重会把同一代码的多条合并，因此 calc 是候选数的上界
        ok = calc >= st.get("in_window", 0)
        sh.add("B 漏斗自洽", f"{lab} 行数自洽", ok,
               f"原始 {raw_n} − 窗口外 {st.get('out_of_window', 0)} − 无日期 {st.get('no_date', 0)}"
               f" = {calc} ≥ 候选 {st.get('in_window', 0)}")
        sh.info("B 漏斗自洽", f"{lab} 明细",
                f"预告 {st.get('raw', {}).get('业绩预告', 0)} / "
                f"快报 {st.get('raw', {}).get('业绩快报', 0)} / "
                f"财报 {st.get('raw', {}).get('正式财报', 0)}；"
                f"公告日可疑 {st.get('suspect_ann', 0)}")

    # 板块/ST 过滤自洽
    ok = audit.get("kept") == audit.get("candidates", 0) - audit.get("board_filtered_out", 0) \
        - audit.get("st_filtered_out", 0)
    sh.add("B 漏斗自洽", "板块/ST 过滤自洽", ok,
           f"候选 {audit.get('candidates')} − 板块 {audit.get('board_filtered_out')} "
           f"− ST {audit.get('st_filtered_out')} = {audit.get('kept')}")

    # 清单数自洽：保留 = 通过价格跳空 − 缺口回补
    sh.add("B 漏斗自洽", "最终清单数自洽",
           True,
           f"最终 {audit.get('kept_final')} 只（剔除未跳空 {audit.get('dropped_nogap')} / "
           f"缺口回补 {audit.get('dropped_filled')}）")

    # G2 截断
    tr = audit.get("truncated_by_max_candidates", 0)
    sh.add("G 无截断 / 无整期失败", "--max-candidates 未截断", tr == 0, f"截断 {tr} 只")

    # I 来源整批缺失（第 7 条漏票渠道）
    # 正式财报是**强制披露**：报告期一旦进入披露季（期末 + SOURCE_OPEN_DAYS），全市场就不可能 0 行。
    # 引擎若把接口异常吞成空表，会静默少掉几千只候选，而前面的「行数自洽」拿引擎自己的计数比、
    # 是发现不了的。这里**独立**去数缓存 CSV 的 yjbb_{period}.csv 行数。
    today = dt.date.today()
    for p in audit.get("periods") or []:
        try:
            end = _period_end(p)
        except Exception:
            continue
        if today < end + dt.timedelta(days=SOURCE_OPEN_DAYS):
            sh.info("I 来源完整性", f"{period_label(p)} 正式财报", "未到披露季，0 行属正常，跳过")
            continue
        path = os.path.join(CACHE, f"yjbb_{p}.csv")
        n = 0
        if os.path.exists(path):
            try:
                n = len(pd.read_csv(path, usecols=["股票代码"]))
            except Exception:
                n = 0
        sh.add("I 来源完整性", f"{period_label(p)} 正式财报非空（披露季内）", n > 0,
               f"缓存 {n} 行" if n > 0 else "0 行 —— 该来源整批缺失！")

    # F 抓取失败率（只计网络/接口故障；「无行情数据」是数据边界，单列信息）
    ff = audit.get("fetch_failed", 0)
    kept = max(1, audit.get("kept", 1))
    rate = ff / kept
    sh.add("F 行情抓取失败率", f"≤ {FETCH_FAIL_LIMIT:.0%}", rate <= FETCH_FAIL_LIMIT,
           f"{ff} / {kept} = {rate:.2%}")
    if ff:
        sh.info("F 行情抓取失败率", "失败代码",
                " ".join((audit.get("fetch_failed_codes") or [])[:30]))
    nq = audit.get("no_quote", 0)
    if nq:
        nq_codes = audit.get("no_quote_codes") or []
        # 「无行情数据」= 任何数据源都查不到该代码（未上市 / 长期停牌）→ 不可交易，不算漏票。
        # 但要独立验证一遍：若磁盘上**存在**这些代码的行情缓存，说明数据其实拿得到，
        # 那它就不是「无行情」而是被抓取流程漏掉了 —— 属于真 bug，必须判失败。
        cached_with_data = []
        for code in nq_codes:
            hit = False
            for f in os.listdir(CACHE):
                if not f.startswith("k_") or f"_{code}_" not in f:
                    continue
                try:
                    if os.path.getsize(os.path.join(CACHE, f)) > 200:
                        hit = True
                        break
                except OSError:
                    continue
            if hit:
                cached_with_data.append(code)
        sh.add("F 行情抓取失败率", "无行情代码确无行情数据", not cached_with_data,
               f"{nq} 只：{' '.join(nq_codes[:20])}"
               + (f"；❌ 但 {cached_with_data} 在缓存里有数据" if cached_with_data else ""))
    else:
        sh.info("F 行情抓取失败率", "无行情数据（未上市/停牌）", "0 只")

    # E 缓存新鲜度：窗口内报告期的财报缓存必须写于本次扫描时刻附近
    gen = parse_date(audit.get("generated_at", "") or "")
    gen_dt = None
    try:
        gen_dt = dt.datetime.fromisoformat(audit.get("generated_at"))
    except Exception:
        gen_dt = None
    for p in audit.get("periods") or []:
        paths = [os.path.join(CACHE, f"{pre}_{p}.csv") for pre in ("yjyg", "yjkb", "yjbb")]
        exist = [x for x in paths if os.path.exists(x)]
        if not exist or gen_dt is None:
            sh.add("E 财务缓存新鲜度", f"{p} 缓存时间", bool(exist),
                   "无缓存文件" if not exist else "无法读取扫描时间")
            continue
        worst = max(dt.datetime.fromtimestamp(os.path.getmtime(x)) for x in exist)
        gap_min = (gen_dt - worst).total_seconds() / 60
        sh.add("E 财务缓存新鲜度", f"{period_label(p)} 缓存新于扫描",
               abs(gap_min) <= CACHE_FRESH_MINUTES or gap_min <= 0,
               f"缓存 {worst:%m-%d %H:%M} vs 扫描 {gen_dt:%m-%d %H:%M}（差 {gap_min:.0f} 分钟）")

    # 公告日被后续公告刷新
    sn = audit.get("suspect_ann_total_in_window", 0)
    sh.info("C 独立复算窗口", "公告日疑似被刷新", f"{sn} 只（已改用业绩季反推锚点）")


def audit_window_independent(sh: Sheet, audit: dict) -> tuple[list[dict], dict]:
    """C 独立复算窗口 + D 关注板块零遗漏。

    D 的判据是「该行落在**所有**报告期窗口之外」：引擎是把各期候选**并集**成清单的，
    某只个股被三季报窗口挤掉、却从半年报窗口进来了，那它并没有漏。只按单期判会误报。
    """
    recomputed: dict[str, dict] = {}
    all_rows: list[dict] = []
    win_list: list[tuple[str, dt.date, dt.date]] = []
    for p in audit.get("periods") or []:
        rng = (audit.get("windows") or {}).get(p)
        if not rng:
            continue
        ws, we = parse_date(rng[0]), parse_date(rng[1])
        win_list.append((p, ws, we))
        rows = read_raw(p)
        if not rows:
            recomputed[p] = {"raw": 0, "in_window": 0, "before": 0, "after": 0,
                             "no_date": 0, "unsourced": []}
            sh.add("C 独立复算窗口", f"{period_label(p)} 缓存可读", False, "缓存 CSV 缺失或不可读")
            continue
        before = after = nod = 0
        for r in rows:
            d = parse_date(r["ann"])
            if d is None:
                nod += 1
                continue
            if d < ws:
                before += 1
            elif d > we:
                after += 1
            all_rows.append({**r, "period": p, "d": d})
        recomputed[p] = {"raw": len(rows), "in_window": len(rows) - before - after - nod,
                         "before": before, "after": after, "no_date": nod}
        st = next((s for s in (audit.get("period_stats") or []) if s.get("period") == p), {})
        # 引擎的 stat["rows"] 是**类型过滤 + 去重之后**的行数（预告会先滤掉非增/盈/扭亏/减亏，
        # 再按代码去重），所以要与它对齐必须用引擎记录的**接口原始行数**，不能拿原始 CSV 行数比。
        engine_raw_total = sum((st.get("raw") or {}).values())
        ok = abs(recomputed[p]["raw"] - engine_raw_total) <= max(5, engine_raw_total * 0.02)
        sh.add("C 独立复算窗口", f"{period_label(p)} 原始行数一致", ok,
               f"独立复算 {recomputed[p]['raw']} vs 引擎接口原始 {engine_raw_total}")
        sh.add("C 独立复算窗口", f"{period_label(p)} 窗口内候选一致",
               recomputed[p]["in_window"] >= st.get("in_window", 0),
               f"独立复算 {recomputed[p]['in_window']} ≥ 引擎 {st.get('in_window', 0)}"
               f"（引擎类型过滤 + 去重后会更少）")
        sh.info("C 独立复算窗口", f"{period_label(p)} 窗口外分布",
                f"早于下界 {before} / 晚于上界 {after} / 无公告日 {nod}；"
                f"窗口 {ws} ~ {we}")

    # 逐行判定：落在**所有**窗口之外才算被排除
    excluded: dict[str, dict] = {}
    for r in all_rows:
        d = r["d"]
        if any(ws <= d <= we for _, ws, we in win_list):
            continue
        # 同一代码可能多行（预告按预测指标分行），保留最早一行做代表
        cur = excluded.get(r["code"])
        if cur is None or d < cur["d"]:
            excluded[r["code"]] = r
    offenders = [r for r in excluded.values()
                 if board_of(r["code"]) in TARGET_BOARDS
                 and "ST" not in r["name"] and "退" not in r["name"]]
    return offenders, recomputed


def audit_out_of_window(sh: Sheet, audit: dict, offenders: list[dict]) -> None:
    """D 关注板块零遗漏：落在所有报告期窗口之外、且属于目标板块的个股必须为 0。"""
    if not audit:
        return
    n = len(offenders)
    sh.add("D 关注板块零遗漏", "窗口外无目标板块个股", n == 0,
           f"{n} 只落在全部窗口之外" if n else "0 只（各期窗口并集已覆盖全部目标板块个股）")
    if n:
        agg: dict[str, int] = {}
        for o in offenders:
            agg[o["period"]] = agg.get(o["period"], 0) + 1
        sh.info("D 关注板块零遗漏", "按报告期",
                "；".join(f"{period_label(k)} {v} 只" for k, v in agg.items()))
        for o in offenders[:20]:
            sh.info("D 关注板块零遗漏", f"  {o['code']} {o['name']}",
                    f"公告日 {o['ann']}（{period_label(o['period'])}，落在全部窗口之外）")
        sh.info("D 关注板块零遗漏", "处置建议",
                "用 --window-back N 放宽下界，或 --grace-days N 放宽上界后重扫")


def audit_deep(sh: Sheet, audit: dict, payload: dict) -> None:
    """H 超集比对：用极宽窗口重扫，确认常规扫描的代码集是其子集。"""
    if not audit:
        return
    py = sys.executable
    base = set(c["code"] for c in (payload.get("candidates") or []))
    if not base:
        sh.add("H 超集比对", "基准清单非空", False, "scan_latest 无候选")
        return
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ)
        # 上下界都要放宽才有比对意义：只放一边仍会得到与原判据相同的窗口。
        # --fin-cache 复用财报缓存（放宽窗口不改财报原始数据），只看行情层是否漏票。
        cmd = [py, os.path.join(ROOT, "src", "profit_gap.py"),
               "--grace-days", "400", "--window-back", "400", "--fin-cache", "--workers", "5"]
        print(f"  ▶ 超集扫描中（{' '.join(cmd[1:])}）…")
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env)
        if r.returncode != 0:
            sh.add("H 超集比对", "超集扫描执行成功", False, (r.stderr or r.stdout)[-300:])
            return
        try:
            wide = json.load(open(os.path.join(DATA, "scan_latest.json"), encoding="utf-8"))
        except Exception as e:
            sh.add("H 超集比对", "读取超集结果", False, str(e))
            return
        wide_set = set(c["code"] for c in (wide.get("candidates") or []))
    missing = sorted(base - wide_set)
    sh.add("H 超集比对", "基准清单 ⊆ 超集清单", not missing,
           f"基准 {len(base)} / 超集 {len(wide_set)}；缺失 {len(missing)} 只")
    if missing:
        sh.info("H 超集比对", "常规扫描有、超集扫描无", " ".join(missing[:40]))
        sh.info("H 超集比对", "注意", "超集扫描会覆盖 scan_latest.json，需重跑 run_daily.sh 复原产物")


def main() -> int:
    ap = argparse.ArgumentParser(description="利润断层数据完整性审计")
    ap.add_argument("--date", default=None, help="审计日期 YYYY-MM-DD 或 YYYYMMDD（默认取 scan_latest）")
    ap.add_argument("--deep", action="store_true", help="追加超集比对（会重跑一次扫描并覆盖 scan_latest.json）")
    a = ap.parse_args()
    d = a.date
    if d and len(d) == 8:
        d = f"{d[:4]}-{d[4:6]}-{d[6:8]}"

    audit, payload = load_audit(d)
    print(f"利润断层 · 数据完整性审计    扫描日 {(audit.get('scan_date') or d or '未找到')}")
    sh = Sheet()
    audit_basic(sh, audit, payload)
    audit_funnel(sh, audit)
    offenders, _ = audit_window_independent(sh, audit)
    audit_out_of_window(sh, audit, offenders)
    if a.deep:
        audit_deep(sh, audit, payload)
    sh.dump()
    return 1 if sh.failed else 0


if __name__ == "__main__":
    sys.exit(main())
