# -*- coding: utf-8 -*-
"""把本轮扫描的关键结论打印成纯文本，供 GitHub Actions 落盘为 data/last_cloud_run.txt。

存在的理由：2026-10-04 遇到过 GitHub Actions 日志存储故障（Azure 返回
InvalidAuthenticationInfo），日志读不出来。所以「这一轮扫出什么、有没有问题」
必须落在仓库文件里，不能只依赖 Actions 日志。
"""
import json
import os
import sys

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "scan_latest.json")


def main() -> int:
    if not os.path.exists(PATH):
        print(f"未找到 {PATH}（扫描可能未完成）")
        return 1
    with open(PATH, encoding="utf-8") as f:
        d = json.load(f)

    meta = d.get("meta") or {}
    s = d.get("summary") or {}
    a = d.get("audit") or {}

    print("窗口:", meta.get("window_label") or "?")
    print("清单个股数:", len(d.get("candidates") or []))
    for k in ("total", "core", "low_base", "price_only", "streak_best", "streak_ge3"):
        if k in s:
            print(f"  {k} = {s[k]}")

    problems = a.get("problems") or []
    print("完整性问题:", "；".join(problems) if problems else "无")

    missing = a.get("missing_sources") or []
    if missing:
        print("来源整批缺失:", "；".join(missing))

    errs = a.get("source_errors") or []
    if errs:
        print("来源接口异常:", "；".join(errs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
