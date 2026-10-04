#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""产物校验：确保交付的页面「不是空的」。

存在的理由：流水线原本只看 python 脚本的退出码。但一个页面完全可能**成功生成、却内容为空**
（数据源整批返回空、payload 写入失败、模板变量没渲染…），退出码仍是 0，
于是空页面被提交上线，谁也不知道。这里做最后一道「内容非空」检查。

退出码：0 = 全部通过；1 = 有致命问题。
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (文件, 最小字节数, 说明)
PAGES = [
    ("利润断层工作台.html", 300_000, "主看板（含 K 线 payload）"),
    ("个人投资工作台.html", 100_000, "聚合页（投资日历 + 选股平台）"),
    ("home.html", 100_000, "聚合页 ASCII 别名"),
    ("index.html", 100_000, "站点首页（Pages 入口）"),
]

problems = []


def payload(html, pid):
    m = re.search(r'<script[^>]*id="%s"[^>]*>(.*?)</script>' % pid, html, re.S)
    if not m:
        return None
    return json.loads(m.group(1))


def main():
    for name, min_bytes, desc in PAGES:
        p = os.path.join(ROOT, name)
        if not os.path.exists(p):
            problems.append("%s 不存在（%s）" % (name, desc))
            continue
        size = os.path.getsize(p)
        if size < min_bytes:
            problems.append("%s 只有 %d 字节，低于下限 %d（%s）"
                            % (name, size, min_bytes, desc))
        else:
            print("  ok  %-22s %8.1f KB  %s" % (name, size / 1024, desc))

    # ---- 聚合页 payload 必须真的有内容 ----
    agg = os.path.join(ROOT, "个人投资工作台.html")
    if os.path.exists(agg):
        html = open(agg, encoding="utf-8").read()
        try:
            cal = payload(html, "cal-payload")
            pk = payload(html, "pk-payload")
        except Exception as e:                                  # noqa: BLE001
            problems.append("聚合页 payload 解析失败：%r" % (e,))
            cal = pk = None

        if cal is not None:
            ev = cal.get("events") or []
            if not ev:
                problems.append("聚合页投资日历事件为 0 条（数据源整批缺失？）")
            else:
                print("  ok  投资日历事件 %d 条 · 来源 %d 个"
                      % (len(ev), len(cal.get("sources") or [])))
            if cal.get("problems"):
                # 日历是可选数据源，不致命，但必须显式喊出来
                print("  !!  投资日历 problems：%s" % "；".join(map(str, cal["problems"])))

        if pk is not None:
            rows = pk.get("rows") or []
            if not rows:
                problems.append("聚合页断层清单为 0 只（多半是扫描失败后仍继续生成）")
            else:
                print("  ok  断层清单 %d 只" % len(rows))
            need = {"c", "n", "d", "g", "dc", "v", "i", "tier"}
            miss = [r.get("c") for r in rows if not need <= set(r)]
            if miss:
                problems.append("断层清单有 %d 行缺字段（如 %s）"
                                % (len(miss), "、".join(map(str, miss[:5]))))
            else:
                print("  ok  断层清单字段齐备（名称/代码/日期/幅度/涨跌幅/成交量/行业/分层）")

    # ---- 主看板 payload ----
    # 注意：主看板的清单键是 candidates（不是 rows），registry 里还另有 sectors / kline 等。
    # 别拿聚合页的键名套过来 —— 猜错会误报「清单 0 行」。
    wb = os.path.join(ROOT, "利润断层工作台.html")
    if os.path.exists(wb):
        m = re.search(r'id="wb-payload"[^>]*>([\s\S]*?)</script>',
                      open(wb, encoding="utf-8").read())
        if not m:
            problems.append("主看板找不到 wb-payload")
        else:
            d = json.loads(m.group(1))
            rows = d.get("candidates") or []
            if not rows:
                problems.append("主看板清单为 0 行")
            else:
                kl = (d.get("kline") or {}).get("data") or {}
                print("  ok  主看板清单 %d 行 · K 线 %d 只 · 板块 %d 个"
                      % (len(rows), len(kl), len(d.get("sectors") or [])))
                if not kl:
                    problems.append("主看板没有 K 线数据（弹窗会点不开）")
                sm = d.get("summary") or {}
                if sm.get("total") != len(rows):
                    problems.append("主看板 summary.total=%s 与 candidates=%d 不一致"
                                    % (sm.get("total"), len(rows)))

    print()
    if problems:
        print("❌ 产物校验未通过：")
        for x in problems:
            print("   · %s" % x)
        return 1
    print("✅ 产物校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
