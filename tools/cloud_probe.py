# -*- coding: utf-8 -*-
"""云端数据源连通性探测：GitHub Actions  runner 上跑，结果打到 stdout。"""
import socket, ssl, time, traceback, urllib.request

URLS = [
    ("控制组", "https://api.github.com"),
    ("控制组", "https://www.cloudflare.com"),
    ("东财数据中心(业绩报表)", "https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_DMSK_FN_MAINFINADATA&columns=ALL&pageNumber=1&pageSize=1"),
    ("东财push2(行情列表)", "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=1&fs=m:0+t:6&fields=f12"),
    ("新浪行情", "https://hq.sinajs.cn/list=sh600519"),
    ("腾讯日K", "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,,,10,qfq"),
]
HOSTS = ["datacenter-web.eastmoney.com", "push2.eastmoney.com", "hq.sinajs.cn", "web.ifzq.gtimg.cn"]

def head(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return f"{r.status}  {time.time()-t0:.2f}s  {len(r.read())}B"
    except Exception as e:
        return f"失败 {type(e).__name__}: {str(e)[:60]}  ({time.time()-t0:.2f}s)"

print("=== 环境 ===")
print(f"  平台: {__import__('platform').platform()}")
print(f"  CPU 核数: {__import__('os').cpu_count()}")

print("\n=== DNS 解析 ===")
for h in HOSTS:
    try:
        print(f"  {h} -> {socket.getaddrinfo(h, 443)[0][4][0]}")
    except Exception as e:
        print(f"  {h} -> 解析失败 {e}")

print("\n=== HTTP 连通性 ===")
for tag, u in URLS:
    print(f"  [{tag}] {head(u)}")
    print(f"       {u[:110]}")

print("\n=== akshare 实测 ===")
try:
    t0 = time.time(); import akshare as ak; print(f"  import akshare: {time.time()-t0:.1f}s  ver={getattr(ak,'__version__','?')}")
except Exception:
    print("  import akshare 失败:"); traceback.print_exc()

try:
    t1 = time.time()
    df = ak.stock_yjbb_em(date="20260630")
    print(f"  东财业绩报表 20260630: {time.time()-t1:.1f}s  行数={len(df)}")
except Exception:
    print("  东财业绩报表 失败:"); traceback.print_exc()

try:
    t2 = time.time()
    df2 = ak.stock_zh_a_daily(symbol="sh600519", adjust="qfq")
    print(f"  新浪日K sh600519: {time.time()-t2:.1f}s  行数={len(df2)}")
except Exception:
    print("  新浪日K 失败:"); traceback.print_exc()

print("\n完成。")
