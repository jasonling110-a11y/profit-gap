#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
利润断层工作台 · 单文件 HTML 生成器 v2
=======================================
读取 data/scan_latest.json，渲染为自包含 HTML 看板：
KPI 概览 / 断层强度四象限 / 板块分布（可点击筛选）/ 板块全景表 / 可排序断层清单 /
点击查看 K 线图（蜡烛+成交量+均线+缺口标注，键盘可达）/ 明细分卡 / 判定口径 / 免责声明

无外部依赖（不加载 CDN），双击即可打开。红涨绿跌，深色主题。
用法：python3 build_workbench.py [--json data/scan_latest.json] [--out 利润断层工作台.html]
"""
from __future__ import annotations

import argparse
import json
import os
import datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TPL = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>利润断层工作台</title>
<style>
:root{
  color-scheme:dark;
  --bg:#0d1117; --panel:#151b23; --panel2:#1b232d; --line:#242c37; --line2:#3b4557; --ctl:#5a6577;
  --tx:#e6edf3; --tx2:#9aa7b4; --tx3:#8b98a6;
  --up:#f0483e; --upbg:rgba(240,72,62,.12); --down:#22a06b; --downbg:rgba(34,160,107,.12);
  --acc:#63a888; --warn:#d9a13b; --info:#4f8cc9;
  --ma5:#e0b64a; --ma10:#6fa8dc; --ma20:#c586c0;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track,::-webkit-scrollbar-corner{background:var(--bg)}
::-webkit-scrollbar-thumb{background:#39424f;border-radius:6px;border:2px solid var(--bg)}
::-webkit-scrollbar-thumb:hover{background:#4c5764}
body{background:var(--bg);color:var(--tx);font:13px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;padding:22px 20px 60px}
.wrap{max-width:1320px;margin:0 auto}
.skip{position:absolute;left:-9999px;top:0;background:var(--panel2);border:1px solid var(--ctl);color:var(--tx);padding:8px 14px;border-radius:0 0 8px 0;z-index:99}
.skip:focus{left:0}
header{display:flex;flex-wrap:wrap;align-items:flex-end;gap:14px;padding-bottom:14px;border-bottom:1px solid var(--line)}
h1{font-size:20px;font-weight:600;letter-spacing:.5px}
h1 span{color:var(--up)}
.sub{color:var(--tx2);font-size:13px;line-height:1.9}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;border:1px solid var(--line2);color:var(--tx2);margin-right:6px}
.badge.open{color:var(--up);border-color:rgba(240,72,62,.45);background:var(--upbg)}
.badge.shut{color:var(--warn);border-color:rgba(217,161,59,.45);background:rgba(217,161,59,.1)}
section{margin-top:24px}
h2{font-size:15px;font-weight:600;margin-bottom:10px;display:flex;align-items:center;gap:8px}
h2:before{content:"";width:3px;height:14px;background:var(--up);border-radius:2px;flex:none}
h2 em{font-style:normal;color:var(--tx2);font-size:12px;font-weight:400}
details{margin-top:24px}
details>summary{list-style:none;cursor:pointer;font-size:15px;font-weight:600;display:flex;align-items:center;gap:8px}
details>summary::-webkit-details-marker{display:none}
details>summary:before{content:"";width:3px;height:14px;background:var(--up);border-radius:2px;flex:none}
details>summary:after{content:"▸ 展开";color:var(--tx2);font-size:12px;font-weight:400}
details[open]>summary:after{content:"▾ 收起"}
details>summary em{font-style:normal;color:var(--tx2);font-size:12px;font-weight:400}
details>summary:hover{color:var(--tx)}
details>*:not(summary){margin-top:10px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(184px,1fr));gap:10px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:13px 15px}
.kpi .k{color:var(--tx2);font-size:13px}
.kpi .v{font-size:24px;font-weight:600;font-variant-numeric:tabular-nums;margin-top:4px;line-height:1.25}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:980px){.grid2{grid-template-columns:1fr}}
.tools{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:10px}
input[type=search],select{background:var(--panel2);border:1px solid var(--ctl);color:var(--tx);border-radius:7px;padding:6px 10px;font-size:13px;outline:none;transition:border-color .2s}
input[type=search]{min-width:180px}
input[type=search]:focus,select:focus{border-color:var(--acc)}
button{font:inherit;cursor:pointer;transition:transform .2s,background-color .2s,border-color .2s}
button:active{transform:scale(.95)}
:focus-visible{outline:2px solid var(--info);outline-offset:2px}
table{width:100%;border-collapse:collapse;font-size:13px}
caption{text-align:left}
th,td{padding:7px 9px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--line)}
th{color:var(--tx2);font-weight:500;font-size:12px;cursor:pointer;user-select:none;position:sticky;top:0;background:var(--panel);z-index:1}
th:hover{color:var(--tx);background:var(--panel2)}
th.on{color:var(--tx)}
th:not(.ns):after{content:" ⇅";color:var(--tx3);font-size:12px}
th.on:after{content:" ▼";color:var(--acc)}
th.on.asc:after{content:" ▲";color:var(--acc)}
th.ns{cursor:default}
td.l,th.l{text-align:left}
tbody tr{cursor:pointer}
tbody tr:hover{background:var(--panel2)}
tbody tr:focus-within{background:var(--panel2)}
.tblwrap{overflow:auto;max-height:620px;border:1px solid var(--line);border-radius:10px;-webkit-overflow-scrolling:touch}
.up{color:var(--up)} .down{color:var(--down)} .mut{color:var(--tx3)}
.px{color:var(--tx);font-variant-numeric:tabular-nums;font-weight:500}
.tag{display:inline-block;padding:1px 6px;border-radius:5px;font-size:12px;border:1px solid var(--line2);color:var(--tx2);margin:1px 3px 1px 0}
.tag.core{color:var(--up);border-color:rgba(240,72,62,.5);background:var(--upbg)}
.tag.watch{color:var(--info);border-color:rgba(79,140,201,.5);background:rgba(79,140,201,.12)}
.tag.risk{color:var(--warn);border-color:rgba(217,161,59,.5);background:rgba(217,161,59,.1)}
.warnc{color:var(--warn)}
/* 类型标签（预告 / 快报 / 财报）——「分类」就靠它 */
.tag.kind{font-weight:600;letter-spacing:.02em}
.tag.kind.warn{color:var(--warn);border-color:rgba(217,161,59,.55);background:rgba(217,161,59,.14)}
.tag.kind.info{color:var(--info);border-color:rgba(79,140,201,.55);background:rgba(79,140,201,.14)}
.tag.kind.plain{color:var(--tx3);border-color:var(--line);background:var(--panel2)}
/* 混排后靠左侧色条再区分一次，扫清单时不用逐行读标签 */
#tbl tbody tr.k-warn>td:first-child{box-shadow:inset 3px 0 0 rgba(217,161,59,.75)}
#tbl tbody tr.k-info>td:first-child{box-shadow:inset 3px 0 0 rgba(79,140,201,.7)}
.tag.good{color:var(--down);border-color:rgba(34,160,107,.5);background:var(--downbg)}
.tag.streak{color:var(--acc);border-color:rgba(99,168,136,.55);background:rgba(99,168,136,.12)}
.kbtn{background:var(--panel2);border:1px solid var(--ctl);color:var(--tx2);border-radius:6px;padding:2px 8px;font-size:12px}
.kbtn:hover{color:var(--tx);border-color:var(--info);background:rgba(79,140,201,.14)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,396px),1fr));gap:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:13px 14px;cursor:pointer}
.card.core{border-left:3px solid var(--up)}
.card.watch{border-left:3px solid var(--info)}
.card:hover{border-color:var(--line2)}
.card h3{font-size:15px;font-weight:600;display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.card h3 .code{color:var(--tx3);font-size:12px;font-weight:400}
.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin:10px 0 8px}
.metrics div{background:var(--panel2);border-radius:7px;padding:6px 8px}
.metrics .k{color:var(--tx2);font-size:12px}
.metrics .v{font-size:15px;font-weight:600;font-variant-numeric:tabular-nums}
.note{color:var(--tx2);font-size:13px;background:var(--panel2);border-radius:7px;padding:8px 10px;max-height:96px;overflow:auto}
.bars{display:flex;flex-direction:column;gap:6px}
.bar{display:grid;grid-template-columns:104px 1fr 150px;align-items:center;gap:10px;width:100%;background:none;border:none;color:var(--tx);text-align:left;padding:3px 4px;border-radius:7px}
.bar:hover{background:var(--panel2)}
.bar .nm{font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar .track{background:var(--panel2);border-radius:4px;height:16px;overflow:hidden;display:flex}
.bar .fillC{background:rgba(240,72,62,.85);height:100%}
.bar .fillW{background:rgba(79,140,201,.5);height:100%}
.bar .num{font-size:12px;color:var(--tx2);text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.modal{position:fixed;inset:0;background:rgba(5,8,12,.72);display:none;align-items:center;justify-content:center;padding:20px;z-index:50}
.modal.on{display:flex}
.mbox{background:var(--panel);border:1px solid var(--line2);border-radius:12px;width:100%;max-width:760px;max-height:92vh;overflow:auto;padding:16px 18px 18px}
.mhead{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:4px}
.mhead h3{font-size:16px;font-weight:600}
.mhead .code{color:var(--tx3);font-size:12px;font-weight:400;margin-left:6px}
.mclose{background:var(--panel2);border:1px solid var(--ctl);color:var(--tx2);border-radius:7px;width:30px;height:30px;font-size:16px;line-height:1}
.mclose:hover{color:var(--tx);border-color:var(--up)}
.mnav{display:flex;align-items:center;gap:6px;flex-shrink:0}
.mnavbtn{background:var(--panel2);border:1px solid var(--ctl);color:var(--tx2);border-radius:7px;padding:5px 10px;font-size:12px;white-space:nowrap;height:30px}
.mnavbtn:hover:not(:disabled){color:var(--tx);border-color:var(--info);background:rgba(79,140,201,.14)}
.mnavbtn:disabled{opacity:.32;cursor:not-allowed}
.mpos{color:var(--tx3);font-size:12px;font-variant-numeric:tabular-nums;min-width:58px;text-align:center}
.msub{color:var(--tx2);font-size:13px;margin-bottom:10px;line-height:1.9}
.mmetrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(104px,1fr));gap:7px;margin:10px 0}
.mmetrics div{background:var(--panel2);border-radius:7px;padding:7px 9px}
.mmetrics .k{color:var(--tx2);font-size:12px}
.mmetrics .v{font-size:15px;font-weight:600;font-variant-numeric:tabular-nums}
.chartbox{position:relative;background:#111721;border:1px solid var(--line);border-radius:9px;padding:6px;user-select:none;overscroll-behavior:contain}
/* pan-y：横向手势交给 JS 平移 K 线，纵向滑动仍交给浏览器滚动弹窗内容（避免图表「卡住」页面）；
   同时不授予 pinch-zoom，双指捏合才能被 pointer 事件拿到用于缩放 */
.chartbox svg{touch-action:pan-y;cursor:crosshair}
.chartbox.dragging svg{cursor:grabbing}
.krange{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:10px 0 8px}
.krange[hidden]{display:none}
.krange .mrl{color:var(--tx3);font-size:12px}
.krange .mrn{color:var(--tx3);font-size:12px;font-variant-numeric:tabular-nums}
.krange .mrz{display:inline-flex;gap:6px;align-items:center;margin-left:4px;padding-left:8px;border-left:1px solid var(--line)}
.krange button{font:inherit;font-size:12px;background:var(--panel2);color:var(--tx2);border:1px solid var(--line);border-radius:6px;padding:3px 10px;cursor:pointer;transition:border-color .2s,color .2s}
.krange button:hover:not(:disabled){color:var(--tx);border-color:var(--line2)}
.krange button[aria-pressed="true"]{background:#1d2a3a;color:var(--tx);border-color:#3f5f86;font-weight:500}
.krange button:disabled{opacity:.38;cursor:not-allowed}
.krange button.latest{background:#1d2a3a;color:var(--tx);border-color:#3f5f86}

.tip{position:absolute;pointer-events:none;background:rgba(13,17,23,.96);border:1px solid var(--line2);border-radius:7px;padding:6px 9px;font-size:12px;line-height:1.75;white-space:nowrap;display:none;color:var(--tx)}
.legend{display:flex;flex-wrap:wrap;gap:12px;color:var(--tx2);font-size:12px;margin-top:7px}
.legend i{display:inline-block;width:12px;height:2px;vertical-align:middle;margin-right:4px}
/* 断层强度分布：气泡可点击打开 K 线 */
.sclegend{align-items:center;gap:8px 11px;padding-top:2px}
.sclegend .lgh{color:var(--tx3);font-size:11px;letter-spacing:.03em}
.sclegend i{width:11px;height:11px;border-radius:50%;margin-right:4px}
.sclegend i[style*="border-top"]{height:0;border-radius:0;width:16px;background:none!important}
#scatter circle.pt{cursor:pointer;transition:fill-opacity .12s,stroke-width .12s}
#scatter circle.pt:hover{fill-opacity:.85;stroke-width:2.6}
#scatter circle.pt:active{fill-opacity:1}
.streakline{display:flex;flex-wrap:wrap;gap:4px 6px;align-items:center;margin-top:8px;font-size:12px;color:var(--tx2)}
.streakline .cell{display:inline-flex;align-items:baseline;gap:4px;background:var(--panel2);border-radius:6px;padding:2px 7px;font-variant-numeric:tabular-nums}
.histline{display:flex;flex-wrap:wrap;gap:4px 6px;align-items:center;margin-top:6px;font-size:12px;color:var(--tx2)}
.histline .cell{display:inline-flex;align-items:baseline;gap:5px;background:var(--panel2);border:1px solid transparent;border-radius:6px;padding:2px 7px;font-variant-numeric:tabular-nums}
.histline .cell.gap{border-color:rgba(201,146,74,.55)}
.histline .cell .d{color:var(--tx3);font-size:11px}
.empty{color:var(--tx2);padding:26px;text-align:center;font-size:13px}
footer{margin-top:26px;padding-top:14px;border-top:1px solid var(--line);color:var(--tx2);font-size:12px;line-height:1.9}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}
@media(max-width:620px){
  body{padding:16px 14px 48px}
  .kpis{grid-template-columns:1fr 1fr;gap:8px}
  .kpi{padding:10px 12px}
  .kpi .v{font-size:20px}
  .metrics{grid-template-columns:repeat(2,1fr)}
  .mnavbtn{padding:5px 7px}
  .mpos{min-width:44px}
  .mhead{flex-wrap:wrap;row-gap:2px}
  .mhead>div:first-child{flex:1 1 100%}
  .mnav{order:-1;margin-left:auto}
  .bar{grid-template-columns:1fr 1fr;grid-template-areas:"nm track" "num num";row-gap:2px}
  .bar .nm{grid-area:nm}
  .bar .track{grid-area:track}
  .bar .num{grid-area:num;text-align:right}
  #tbl thead{display:none}
  #tbl,#tbl tbody,#tbl tr,#tbl td{display:block;width:100%}
  #tbl tr{border-bottom:1px solid var(--line);padding:8px 2px}
  #tbl td{border:none;white-space:normal;padding:2px 0;display:flex;justify-content:space-between;gap:10px;text-align:right}
  #tbl td:before{content:attr(data-label);color:var(--tx2);font-size:12px;text-align:left;flex:none}
  #tbl td.l{text-align:right}
  #tbl td[data-label="K线"]{display:none}
}
@media(prefers-reduced-motion:reduce){
  *,*:before,*:after{animation:none!important;transition:none!important}
  html{scroll-behavior:auto}
}
/* ===== 交易日历（外部模块 · iframe 嵌入）================================
   为什么必须是「全屏覆盖层」而不是内联进文档流：
   日历本体（webapp/index.html）是 body{overflow:hidden} + .app{height:100dvh}
   的全屏应用，布局为「左 396px 日历栏 + 右侧内容栏」，且内部滚动交给自己的容器。
   内联到本页文档流里要么没有确定高度（塌陷），要么被窄容器挤爆。
   给它独立一整层，既保持了原版页面结构与观感，也满足「两模块互不干扰」。
   ==================================================================== */
.hdr-nav{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.hdr-tabs{display:flex;gap:4px;background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:3px}
.hdr-tab{appearance:none;-webkit-appearance:none;border:0;background:transparent;color:var(--tx2);
  font:600 13px/1.6 inherit;padding:6px 14px;border-radius:7px;cursor:pointer;white-space:nowrap;
  transition:background-color .2s,color .2s}
.hdr-tab:hover{color:var(--tx);background:var(--panel2)}
.hdr-tab[aria-current="true"]{background:var(--upbg);color:var(--up);box-shadow:inset 0 0 0 1px rgba(240,72,62,.45)}
.hdr-tab:focus-visible{outline:2px solid var(--info);outline-offset:2px}
.hdr-tab .dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--line2);margin-right:7px;vertical-align:1px}
.hdr-tab[aria-current="true"] .dot{background:var(--up)}
@media(max-width:560px){
  .hdr-nav{width:100%}
  .hdr-tabs{flex:1;justify-content:stretch}
  .hdr-tab{flex:1;text-align:center;padding:7px 6px}
}
/* 覆盖层：100dvh 放在 100vh 之后——iOS Safari 的 100vh 含地址栏，会把底部裁掉 */
#calMask{position:fixed;inset:0;background:rgba(6,9,13,.72);z-index:120;display:none}
#calMask.on{display:block}
#calShell{position:fixed;inset:0;z-index:121;display:none;flex-direction:column;
  background:var(--bg);height:100vh;height:100dvh}
#calShell.on{display:flex}
.cal-bar{flex:none;display:flex;align-items:center;gap:10px;
  min-height:calc(48px + env(safe-area-inset-top,0px));
  padding:env(safe-area-inset-top,0px) 14px 0;border-bottom:1px solid var(--line);background:var(--panel)}
.cal-bar .t{font-size:14px;font-weight:600;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cal-bar .t em{font-style:normal;color:var(--tx3);font-size:12px;font-weight:400;margin-left:8px}
.cal-btn{appearance:none;-webkit-appearance:none;background:var(--panel2);border:1px solid var(--ctl);
  color:var(--tx);border-radius:7px;padding:6px 11px;font:13px/1.4 inherit;cursor:pointer;
  white-space:nowrap;text-decoration:none;transition:border-color .2s,transform .2s}
.cal-btn:hover{border-color:var(--acc)}
.cal-btn:active{transform:scale(.96)}
.cal-btn:focus-visible{outline:2px solid var(--info);outline-offset:2px}
.cal-stage{flex:1;min-height:0;position:relative;background:var(--bg)}
.cal-stage>iframe{display:block;width:100%;height:100%;border:0;background:var(--bg)}
.cal-wrap{position:absolute;inset:0;display:none;flex-direction:column;align-items:center;
  justify-content:center;gap:14px;padding:24px;text-align:center;color:var(--tx2)}
.cal-wrap.on{display:flex}
.cal-wrap h3{font-size:15px;color:var(--tx);font-weight:600}
.cal-wrap p{font-size:13px;max-width:440px;line-height:1.9;color:var(--tx2)}
.cal-wrap .ops{display:flex;gap:8px;flex-wrap:wrap;justify-content:center}
.cal-spin{width:18px;height:18px;border:2px solid var(--line2);border-top-color:var(--up);
  border-radius:50%;animation:calspin .8s linear infinite}
@keyframes calspin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.cal-spin{animation:none}}
@media(max-width:560px){
  .cal-bar .t em{display:none}
  .cal-bar{padding-left:10px;padding-right:10px}
  .cal-btn{padding:6px 9px}
}
</style>
</head>
<body>
<a class="skip" href="#list">跳到断层清单</a>
<div class="wrap">
  <header>
    <div style="flex:1;min-width:280px">
      <h1>利润断层<span>工作台</span></h1>
      <div class="sub" id="meta"></div>
    </div>
    <nav class="hdr-nav" aria-label="模块切换">
      <div class="hdr-tabs">
        <button type="button" class="hdr-tab" id="tabHome" aria-current="true"><span class="dot"></span>利润断层</button>
        <button type="button" class="hdr-tab" id="tabCal" aria-current="false"><span class="dot"></span>交易日历</button>
      </div>
      <a class="cal-btn" id="goHome" href="个人投资工作台.html">工作台首页</a>
      <a class="cal-btn" id="calNew" href="https://market-calendar-71280.app.workbuddy.host/" target="_blank" rel="noopener noreferrer">新窗口打开</a>
    </nav>
  </header>

  <main>
    <section id="overview">
      <h2>概览</h2>
      <div class="kpis" id="kpis"></div>
    </section>

    <section id="list">
      <h2>断层清单</h2>
      <nav class="tools" aria-label="清单筛选与排序">
        <input type="search" id="q" placeholder="搜索代码 / 名称 / 行业 / 标签" aria-label="搜索个股">
        <select id="find" aria-label="按行业筛选"><option value="">全部行业</option></select>
        <select id="fboard" aria-label="按上市板块筛选"><option value="">全部板块</option></select>
        <select id="fsrc" aria-label="按数据来源筛选">
          <option value="">全部来源</option>
          <option value="业绩预告">业绩预告</option>
          <option value="业绩快报">业绩快报</option>
          <option value="正式财报">正式财报</option>
        </select>
        <select id="ftier" aria-label="按分层筛选">
          <option value="">全部层级</option>
          <option value="核心池">核心池·双断层</option>
          <option value="观察池">观察池</option>
          <option value="低基数">仅看低基数断层</option>
          <option value="跟踪">仅价格缺口</option>
        </select>
        <select id="fsort" aria-label="排序方式（与点击表头等效）">
          <option value="score">按评分</option>
          <option value="streak">按连续断层期数</option>
          <option value="accel">按加速度</option>
          <option value="growth">按增速</option>
          <option value="price">按最新价</option>
          <option value="daychg">按当日涨跌幅</option>
          <option value="gap">按跳空幅度</option>
          <option value="after">按缺口后涨幅</option>
          <option value="amount">按成交额</option>
          <option value="mcap">按流通市值</option>
          <option value="npsingle">按单季净利</option>
        </select>
        <button id="reset" class="kbtn" style="padding:6px 12px">重置筛选</button>
        <span class="mut" id="cnt" style="font-size:12px"></span>
      </nav>
      <div class="tblwrap"><table id="tbl">
        <caption class="sr-only">利润断层个股清单：列含最新价、当日涨跌幅、跳空幅度、净利润增速、加速度、连续断层期数与评分；点击表头可切换升降序，点击行可查看 K 线图</caption>
        <thead></thead><tbody></tbody></table></div>
    </section>

    <section class="grid2">
      <div>
        <h2>断层强度分布</h2>
        <div class="panel" style="padding:6px"><div id="scatter"></div></div>
      </div>
      <div>
        <h2>板块分布</h2>
        <div class="panel" id="sectorbars" style="max-height:432px;overflow:auto"></div>
      </div>
    </section>

    <details id="d-sec">
      <summary>板块全景</summary>
      <div class="tblwrap" style="max-height:440px"><table id="stbl">
        <caption class="sr-only">按东方财富行业口径聚合的板块全景表：断层个股数、核心池数量、核心占比、缺口未回补数、平均增速、平均跳空、平均评分与代表个股；点击行可筛选清单</caption>
        <thead></thead><tbody></tbody></table></div>
    </details>

    <details id="d-cards">
      <summary>明细分卡</summary>
      <div class="cards" id="cards"></div>
    </details>
  </main>

  <footer id="foot"></footer>
</div>

<div class="modal" id="modal" role="dialog" aria-modal="true" aria-labelledby="mTitle">
  <div class="mbox" role="document">
    <div class="mhead">
      <div>
        <h3 id="mTitle">—</h3>
        <div class="msub" id="mSub"></div>
      </div>
      <div class="mnav">
        <button class="mnavbtn" id="mPrev" aria-label="上一个个股（快捷键 上箭头）" title="上一个个股（↑）">▲ 上一个</button>
        <span class="mpos" id="mPos" title="按当前清单的顺序翻页（含筛选与排序）">—</span>
        <button class="mnavbtn" id="mNext" aria-label="下一个个股（快捷键 下箭头）" title="下一个个股（↓）">下一个 ▼</button>
        <button class="mclose" id="mClose" aria-label="关闭 K 线图">×</button>
      </div>
    </div>
    <div class="mmetrics" id="mMetrics"></div>
    <div id="mStreak"></div>
    <div id="mHist"></div>
    <div class="krange" id="mRange" role="group" aria-label="K 线回顾区间"></div>
    <div class="chartbox" id="chartbox">
      <div id="mChart"></div>
      <div class="tip" id="tip" role="status" aria-live="polite"></div>
    </div>
    <div class="legend" id="mLegend"></div>
    <div id="mTags" style="margin-top:10px"></div>
    <div id="mNote" style="margin-top:8px"></div>
  </div>
</div>

<!-- ===== 交易日历 · 外部模块（iframe 嵌入 + 全屏覆盖层）====================
     role=dialog + aria-modal：读屏可识别，Esc 关闭，焦点锁在层内。
     关闭时会摘掉 iframe 的 src —— 让它彻底停止活动，两个模块互不干扰
     （不抢定时器、不抢滚动、不占后台网络）。
     ================================================================== -->
<div id="calMask"></div>
<section id="calShell" role="dialog" aria-modal="true" aria-labelledby="calTitle" tabindex="-1">
  <header class="cal-bar">
    <span class="t" id="calTitle">交易日历<em>外部模块 · 独立部署</em></span>
    <a class="cal-btn" id="calNewBar" href="https://market-calendar-71280.app.workbuddy.host/" target="_blank" rel="noopener noreferrer">新窗口</a>
    <button type="button" class="cal-btn" id="calRetry">重试</button>
    <button type="button" class="cal-btn" id="calClose">关闭 (Esc)</button>
  </header>
  <div class="cal-stage">
    <iframe id="calFrame" title="交易日历" referrerpolicy="no-referrer-when-downgrade"
      sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox allow-downloads"></iframe>
    <div class="cal-wrap" id="calLoad"><div class="cal-spin"></div><span>正在加载交易日历…</span></div>
    <div class="cal-wrap" id="calFb" role="alert">
      <h3>交易日历加载失败</h3>
      <p id="calFbMsg"></p>
      <div class="ops">
        <button type="button" class="cal-btn" id="calFbRetry">重试</button>
        <a class="cal-btn" id="calFbNew" href="https://market-calendar-71280.app.workbuddy.host/" target="_blank" rel="noopener noreferrer">在新窗口打开</a>
      </div>
    </div>
  </div>
</section>

<script type="application/json" id="wb-payload">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById("wb-payload").textContent);
const meta = DATA.meta, sum = DATA.summary || {}, rows = DATA.candidates || [];
const SEC = DATA.sectors || [];
/* payload 里两段：
     candidates = 有「有效且未回补跳空」的清单（价格断层成立）——v1.12 起利润侧不设门槛，
                  这一段实际上就等于「公告后跳空 ≥min_gap% 且未回补」的全部个股
     pre_pool   = 业绩预告型利润断层，但尚未跳空 / 已回补（**默认关闭**，需引擎加 --pre-pool；
                  利润侧门槛取消后它会把未跳空的预告全捞进来，与「必须跳空」冲突）
   看板上把两者**混排成同一张清单**，靠「类型」列 + 来源筛选区分；统计口径（KPI / 板块聚合 /
   明细卡 / 散点图）仍只算 candidates。 */
const PRE = DATA.pre_pool || [];
const ALLROWS = rows.concat(PRE);
const KL = DATA.kline || {dates:[], data:{}};
const KL_DATES = KL.dates || [];
const KL_DATA = KL.data || {};
/* 每只个股缓存为 {d0, bars}：d0 是它在全局日期轴 KL_DATES 上的起始下标。
   连续断层越多的个股回溯越长，因此各股长度不同，靠 d0 对齐。
   兼容旧格式（与全局轴等长的裸数组）。 */
function klineOf(code){
  const e = KL_DATA[code];
  if(!e) return null;
  if(Array.isArray(e)) return {d0:0, bars:e};
  const bars = e.bars || [];
  if(!bars.length) return null;
  return {d0: e.d0|0, bars:bars};
}
/* K 线视窗：CHART_WIN = 可见根数（0 = 全部可用历史），CHART_END = 右端下标（null = 贴住最新）。
   拖拽 / 滚轮 / 键盘都会改这两个值，区间按钮与「回到最新」只是它们的快捷方式。
   打开时由 autoWin() 决定窗口宽度：单期个股显示最近 120 根（同花顺手感，且前后都留拖动余地）；
   连续多期断层的个股则放大到能看见最早那一期 —— 否则「之前的断层」全在视野外，等于没标。 */
const DEFAULT_WIN = 120;
let CHART_WIN = DEFAULT_WIN;
let CHART_END = null;
let chartStock = null;
let CVST = null;                 /* drawChart 每次写入：{avail,win,start,end,bw,P,W} */
let dragging = false;
const WIN_OPTS = [[60,"近 60 日"],[120,"近 120 日"],[250,"近 250 日"],[0,"全部"]];
const MIN_BARS = 20;             /* 缩放下限：任何情况下至少显示 20 根 */
/* 日期 → 该股日期轴上的下标：公告日常落在非交易日，必须按「第一个 ≥ 该日的交易日」对齐，
   否则 indexOf 返回 -1，公告线 / 各期断层标记会整条消失 */
function idxOnOrAfter(dts, iso){
  if(!iso) return -1;
  const exact = dts.indexOf(iso);
  if(exact >= 0) return exact;
  for(let i=0;i<dts.length;i++){
    if(!dts[i]) continue;
    if(dts[i] >= iso){
      /* 只接受「紧挨着的那一个交易日」：公告日落在周末/节假日时最多差几天。
         差太多说明该日根本不在本窗口内（在窗口之前或之后），必须判为不可见 ——
         否则窗口之前的历史公告会被错误地钉在最左边第一根 K 线上。 */
      const b = Date.parse(dts[i]) - Date.parse(iso);
      return (b >= 0 && b <= 10*864e5) ? i : -1;
    }
  }
  return -1;
}
/* "2025年年报" → "25年报"、"2026年一季报" → "26一季报" */
function shortLabel(lab){ return String(lab||"").replace(/^\d{2}(\d{2})年/, "$1"); }
/* 打开弹窗时的默认视窗宽度：在标准档位里挑**够用且最小**的一档，保证最早那一期断层在视野内。
   够用 = 从最早一期断层的锚点日到最新交易日所需的根数（末尾留 12 根缓冲）。
   返回 0 表示「全部」；始终返回标准档位，这样「区间」里必然恰有一个按钮是高亮的。 */
const AUTO_WINS = [120, 250, 0];
function autoWin(r){
  const kd = r ? klineOf(r.code) : null;
  if(!kd) return DEFAULT_WIN;
  const avail = kd.bars.length;
  const pgs = (r.period_gaps||[]).filter(x=>x && x.ann && x.period!==r.period);
  if(!pgs.length) return Math.min(DEFAULT_WIN, avail);
  const dts = KL_DATES.slice(kd.d0, kd.d0+avail);
  let earliest = null;
  pgs.forEach(x=>{ const i = idxOnOrAfter(dts, x.ann); if(i>=0 && (earliest===null || i<earliest)) earliest = i; });
  if(earliest === null) return Math.min(DEFAULT_WIN, avail);
  const need = avail - earliest + 12;
  for(let k=0;k<AUTO_WINS.length;k++){
    const w = AUTO_WINS[k];
    if(w === 0) return 0;
    if(need <= w) return Math.min(w, avail);
  }
  return 0;
}

const fmt = (v,n=2) => (v===null||v===undefined||isNaN(v)) ? "—" : Number(v).toFixed(n);
const pct = v => (v===null||v===undefined||isNaN(v)) ? "—" : (v>=0?"+":"") + Number(v).toFixed(2) + "%";
const cls = v => (v===null||v===undefined||isNaN(v)) ? "mut" : (v>0?"up":(v<0?"down":"mut"));
const money = v => { if(!v) return "—"; if(v>=1e8) return (v/1e8).toFixed(2)+"亿"; if(v>=1e4) return (v/1e4).toFixed(0)+"万"; return Number(v).toFixed(0); };
const esc = s => String(s===null||s===undefined?"":s).replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

document.getElementById("meta").innerHTML =
  "数据时点 <b>"+meta.generated_at+"</b> · 行情截至 "+meta.last_trade_date+
  " <span class='badge "+(meta.market_status.indexOf("休市")>=0?"shut":"open")+"'>"+meta.market_status+"</span><br>"+
  "覆盖报告期："+(meta.period_labels||[]).join(" / ")+" · 公告日期窗口："+
  (meta.window_label || (meta.window_start+" 起 "+meta.window_days+" 天"));

/* 概览：3 个主指标，只给数字。红=强（业绩正增长），绿=弱（业绩没跟上的仅价格缺口）。 */
const kpi = [
  {k:"清单个股", v:ALLROWS.length, c:""},
  {k:"业绩正增长", v:sum.core, c:"up"},
  {k:"仅价格缺口", v:sum.price_only, c:"down"}
];
document.getElementById("kpis").innerHTML = kpi.map(x=>
  "<div class='kpi'><div class='k'>"+x.k+"</div><div class='v "+x.c+"'>"+x.v+"</div></div>").join("");

/* 断层强度分布（可交互）
   颜色 = 强弱（评分四档，红→蓝）；描边线型 = 分层；气泡半径 = 成交额。
   点任意气泡 → 直接打开该股 K 线图（鼠标 / 触屏）。键盘操作走上方清单。 */
const STRENGTH = [
  {min:75,   c:"#e8402f", t:"强 ≥75"},
  {min:60,   c:"#e07a35", t:"较强 60–74"},
  {min:45,   c:"#d9a13b", t:"一般 45–59"},
  {min:-1e9, c:"#5b7fa6", t:"弱 <45"}
];
const strengthOf = sc => STRENGTH.find(s=>(sc||0) >= s.min);
/* 分层 → 描边宽度 / 线型。气泡变小后描边也同步收细，否则小气泡会被描边填满 */
const TIER_STROKE = [
  {k:"核心",   w:1.8, da:""},
  {k:"低基数", w:1.4, da:"3.5 2.2"},
  {k:"跟踪",   w:1.1, da:"1.4 2.2"}
];
function tierStroke(t){
  const hit = TIER_STROKE.find(x=>String(t||"").indexOf(x.k)>=0);
  return hit || TIER_STROKE[2];
}
/* 气泡半径 = 成交额的平方根映射：r = R_MIN + R_SPAN*sqrt(amount/amax)
   想调气泡大小只改这两个数。v1.13b 用户反馈「太大了」，由 4 + 10（4~14）缩到 3.6 + 5.4（3.6~9）。
   R_MIN 不再往下压：半径即点击热区，3.6 在 620 宽的 viewBox 里已经是约 6px 直径，再小就点不中了。
   注意 r 是半径、面积按平方缩放（本轮视觉面积约为原来的 40%），别按线性比例估。 */
const R_MIN = 3.6, R_SPAN = 5.4;
const bubbleR = (amount, amax) => R_MIN + R_SPAN * Math.sqrt((amount||0)/(amax||1));
function scatter(){
  const W=620, H=400, P={l:48,r:16,t:16,b:36};
  const pts = rows.filter(r=>r.growth!==null && r.gap && r.gap.gap_vs_close>=0);
  const el = document.getElementById("scatter");
  if(!pts.length){ el.innerHTML="<div class='empty'>暂无可绘制的断层点</div>"; return; }
  const xs = pts.map(p=>Math.max(p.growth,0)), ys = pts.map(p=>p.gap.gap_vs_close);
  const xcap = 500;
  const xmax = Math.min(xcap, Math.max(120, Math.ceil(Math.max.apply(null,xs)/50)*50));
  const ymax = Math.max(4, Math.ceil(Math.max.apply(null,ys)/2)*2);
  const amax = Math.max.apply(null, pts.map(p=>p.gap.amount||0))||1;
  const sx = v => P.l + Math.min(Math.max(v,0),xmax)/xmax*(W-P.l-P.r) - (v>xmax?3:0);
  const sy = v => H-P.b - Math.min(Math.max(v,0),ymax)/ymax*(H-P.t-P.b);
  let s = "<svg viewBox='0 0 "+W+" "+H+"' width='100%' role='img' aria-label='断层强度分布图，颜色表示强弱，点击气泡可打开该股 K 线' style='display:block'>";
  s += "<rect x='"+P.l+"' y='"+P.t+"' width='"+(W-P.l-P.r)+"' height='"+(H-P.t-P.b)+"' fill='#111721' rx='8'/>";
  for(let i=0;i<=5;i++){ const x=P.l+(W-P.l-P.r)*i/5;
    s += "<line x1='"+x+"' y1='"+P.t+"' x2='"+x+"' y2='"+(H-P.b)+"' stroke='#1e2731'/>";
    s += "<text x='"+x+"' y='"+(H-P.b+16)+"' fill='#6b7684' font-size='10' text-anchor='middle'>"+Math.round(xmax*i/5)+"%</text>"; }
  for(let i=0;i<=4;i++){ const y=H-P.b-(H-P.t-P.b)*i/4;
    s += "<line x1='"+P.l+"' y1='"+y+"' x2='"+(W-P.r)+"' y2='"+y+"' stroke='#1e2731'/>";
    s += "<text x='"+(P.l-6)+"' y='"+(y+3)+"' fill='#6b7684' font-size='10' text-anchor='end'>"+(ymax*i/4).toFixed(1)+"%</text>"; }
  /* 门槛参考线：利润侧不设门槛时 min_yoy / min_accel 为 null，自动不画 */
  if(meta.thresholds.min_yoy!==null && meta.thresholds.min_yoy!==undefined){
    s += "<line x1='"+sx(meta.thresholds.min_yoy)+"' y1='"+P.t+"' x2='"+sx(meta.thresholds.min_yoy)+"' y2='"+(H-P.b)+"' stroke='#d9a13b' stroke-dasharray='4 3'/>";
    s += "<text x='"+(sx(meta.thresholds.min_yoy)+5)+"' y='"+(P.t+13)+"' fill='#d9a13b' font-size='10'>增速门槛 "+meta.thresholds.min_yoy+"%</text>";
  }
  s += "<line x1='"+P.l+"' y1='"+sy(meta.thresholds.min_gap)+"' x2='"+(W-P.r)+"' y2='"+sy(meta.thresholds.min_gap)+"' stroke='#d9a13b' stroke-dasharray='4 3'/>";
  s += "<text x='"+(W-P.r-6)+"' y='"+(sy(meta.thresholds.min_gap)-5)+"' fill='#d9a13b' font-size='10' text-anchor='end'>跳空门槛 "+meta.thresholds.min_gap+"%</text>";
  /* 按评分升序绘制：强的后画、压在上层，重叠时更容易点到强票 */
  pts.slice().sort((a,b)=>(a.score||0)-(b.score||0)).forEach(p=>{
    const r = bubbleR(p.gap.amount, amax);
    const st = strengthOf(p.score), tk = tierStroke(p.tier);
    const over = Math.max(p.growth,0) > xmax;
    const cx = sx(Math.max(p.growth,0)), cy = sy(p.gap.gap_vs_close);
    const lab = esc(p.name+" "+p.code+"，"+p.tier+"，评分 "+fmt(p.score,1)+"，点击查看 K 线图");
    if(over) s += "<circle cx='"+cx+"' cy='"+cy+"' r='"+(r+1.8).toFixed(1)+"' fill='none' stroke='"+st.c+"' stroke-width='0.9' stroke-opacity='0.5' pointer-events='none'/>";
    s += "<circle class='pt' data-code='"+p.code+"' cx='"+cx+"' cy='"+cy+"' r='"+r.toFixed(1)+
      "' fill='"+st.c+"' fill-opacity='0.4' stroke='"+st.c+"' stroke-width='"+tk.w+"'"+(tk.da?" stroke-dasharray='"+tk.da+"'":"")+
      " aria-label='"+lab+"'><title>"+esc(p.name)+" "+p.code+" | "+p.tier+" | 增速"+fmt(p.growth,1)+"% | 跳空"+fmt(p.gap.gap_vs_close,2)+"% | 评分"+fmt(p.score,1)+"</title></circle>";
  });
  pts.slice().sort((a,b)=>b.score-a.score).slice(0,8).forEach(p=>{
    const px = sx(Math.max(p.growth,0)), o = Math.max(p.growth,0) > xmax;
    s += "<text x='"+(o? px-6 : px+6)+"' y='"+(sy(p.gap.gap_vs_close)+4)+"' fill='#9aa7b4' font-size='10' text-anchor='"+(o?"end":"start")+"' pointer-events='none'>"+esc(p.name)+"</text>"; });
  const nOver = pts.filter(p=>Math.max(p.growth,0)>xmax).length;
  if(nOver) s += "<text x='"+(W-P.r-6)+"' y='"+(H-P.b-6)+"' fill='#6b7684' font-size='9.5' text-anchor='end' pointer-events='none'>"+"增速 &gt; "+xmax+"% 的 "+nOver+" 只已贴右缘（外圈细环）</text>";
  s += "</svg>";
  /* 图例：强弱（填充色）+ 分层（描边线型） */
  s += "<div class='legend sclegend'>"+
    "<span class='lgh'>强弱(评分)</span>"+
    STRENGTH.map(x=>"<span><i style='background:"+x.c+"'></i>"+x.t+"</span>").join("")+
    "<span class='lgh'>分层(描边)</span>"+
    "<span><i style='background:none;border-top:2.2px solid #9aa7b4'></i>核心池</span>"+
    "<span><i style='background:none;border-top:2px dashed #9aa7b4'></i>低基数</span>"+
    "<span><i style='background:none;border-top:2px dotted #9aa7b4'></i>仅价格缺口</span>"+
    "</div>";
  el.innerHTML = s;
}

const reduceMotion = () => !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
function scrollToTable(){
  const t = document.getElementById("tbl");
  if(t && typeof t.scrollIntoView === "function") t.scrollIntoView({behavior: reduceMotion()?"auto":"smooth", block:"start"});
}
function filterByIndustry(ind){
  document.getElementById("find").value = ind;
  scrollToTable();
  render();
}

function sectorBars(){
  const el = document.getElementById("sectorbars");
  if(!SEC.length){ el.innerHTML="<div class='empty'>暂无行业聚合数据</div>"; return; }
  const top = SEC.slice(0,16);
  const max = Math.max.apply(null, top.map(s=>s.count))||1;
  el.innerHTML = "<div class='bars'>"+top.map(s=>{
    return "<button class='bar' data-ind='"+esc(s.industry)+"' title='点击筛选："+esc(s.industry)+"'>"+
      "<span class='nm'>"+esc(s.industry)+"</span>"+
      "<span class='track'><span class='fillC' style='width:"+(s.core/max*100).toFixed(1)+"%'></span>"+
      "<span class='fillW' style='width:"+((s.count-s.core)/max*100).toFixed(1)+"%'></span></span>"+
      "<span class='num'>"+s.count+" 只 · 核心 "+s.core+" · 均分 "+fmt(s.avg_score,1)+"</span></button>";
  }).join("")+"</div><div class='legend'><span><i style='background:rgba(240,72,62,.85)'></i>核心池</span><span><i style='background:rgba(79,140,201,.5)'></i>非核心池</span></div>";
  /* 点击交给 document 级委托（见文件末尾 initDelegation），此处不再逐条绑定 */
}

const SCOLS = [
  {k:"industry", t:"行业", l:1, f:s=>s.industry},
  {k:"count", t:"断层数", f:s=>s.count},
  {k:"core", t:"核心池", f:s=>s.core},
  {k:"core_ratio", t:"核心占比%", f:s=>s.core_ratio},
  {k:"unfilled", t:"缺口未回补", f:s=>s.unfilled},
  {k:"avg_growth", t:"平均增速%", f:s=>s.avg_growth},
  {k:"avg_gap", t:"平均跳空%", f:s=>s.avg_gap},
  {k:"avg_score", t:"平均评分", f:s=>s.avg_score},
  {k:"leaders", t:"代表个股", l:1, f:s=>(s.leaders||[]).map(x=>x.name).join("、")}
];
let ssort = "core", sasc = false;

/* 表头统一生成：可排序列加 tabindex / role=columnheader 与**静态** aria-sort，
   键盘（Enter / 空格）与鼠标等效；不可排序列标 .ns —— 不可聚焦、不显示 ⇅ 提示 */
function headHTML(cols, activeKey, asc, sortableKeys){
  return "<tr>"+cols.map(c=>{
    const sortable = !sortableKeys || sortableKeys.indexOf(c.k) >= 0;
    const cls = " class='"+(c.l?"l":"")+(sortable?"":" ns")+(c.k===activeKey?" on":"")+(c.k===activeKey&&asc?" asc":"")+"'";
    const attrs = sortable
      ? (" tabindex='0' role='columnheader'"+(c.k===activeKey?(" aria-sort='"+(asc?"ascending":"descending")+"'"):""))
      : "";
    const title = sortable ? ("按「"+c.t+"」排序（先降序，再点升序）") : "";
    return "<th"+cls+" scope='col'"+attrs+" data-k='"+c.k+"' title='"+title+"'>"+c.t+"</th>";
  }).join("")+"</tr>";
}
document.getElementById("stbl").querySelector("thead").innerHTML =
  headHTML(SCOLS, ssort, sasc, null);

function paintSecHead(){
  document.querySelectorAll("#stbl thead th").forEach(x=>{
    const on = x.dataset.k===ssort;
    x.classList.toggle("on", on);
    x.classList.toggle("asc", on && sasc);
    if(on) x.setAttribute("aria-sort", sasc?"ascending":"descending"); else x.removeAttribute("aria-sort");
  });
}
function sectorSort(k){
  if(ssort===k) sasc = !sasc; else { ssort = k; sasc = false; }
  paintSecHead();
  renderSectors();
}
function renderSectors(){
  const col = SCOLS.find(c=>c.k===ssort)||SCOLS[1];
  const data = SEC.slice().sort((a,b)=> cmpRows(a, b, col, sasc));
  document.getElementById("stbl").querySelector("tbody").innerHTML = data.map(s=>
    "<tr data-ind='"+esc(s.industry)+"' tabindex='0'><td class='l'>"+esc(s.industry)+"</td><td>"+s.count+"</td>"+
    "<td>"+(s.core?"<b class='up'>"+s.core+"</b>":"0")+"</td><td>"+fmt(s.core_ratio,0)+"</td><td>"+s.unfilled+"</td>"+
    "<td class='"+cls(s.avg_growth)+"'>"+fmt(s.avg_growth,1)+"</td>"+
    "<td class='"+cls(s.avg_gap)+"'>"+fmt(s.avg_gap,2)+"</td><td>"+fmt(s.avg_score,1)+"</td>"+
    "<td class='l mut'>"+esc((s.leaders||[]).map(x=>x.name+"("+fmt(x.growth,0)+"%)").join("、"))+"</td></tr>").join("");
  /* 行的点击 / 回车由 initDelegation() 统一委托，不再逐行绑定 */
}

/* 清单是「预告 + 快报 + 正式财报」混排的一张表，靠「类型」列区分。
   KIND_RANK 让该列可以按分类排序（预告 → 快报 → 财报），否则纯文本列排序是空操作。 */
const KIND = {
  "业绩预告": {rank:0, cls:"warn",  short:"预告", title:"业绩预告：最早披露，未经审计；缺可比单季/上期数据"},
  "业绩快报": {rank:1, cls:"info",  short:"快报", title:"业绩快报：未经审计的初步核算数"},
  "正式财报": {rank:2, cls:"plain", short:"财报", title:"正式财报：已披露定期报告，经审计口径"}
};
const KIND_RANK = {"业绩预告":0, "业绩快报":1, "正式财报":2};
function kindTag(src){
  const k = KIND[src] || {cls:"plain", short:src||"—", title:""};
  return "<span class='tag kind "+k.cls+"' title='"+esc(k.title)+"'>"+esc(k.short)+"</span>";
}

const COLS = [
  {k:"kline", t:"K线", l:1, f:r=>""},
  {k:"code", t:"代码", l:1, f:r=>r.code},
  {k:"name", t:"名称", l:1, f:r=>r.name},
  {k:"industry", t:"行业", l:1, f:r=>r.industry||"—"},
  {k:"board", t:"板块", l:1, f:r=>r.board},
  {k:"announce", t:"公告日", l:1, f:r=>r.announce},
  {k:"source", t:"类型", l:1, f:r=>KIND_RANK[r.source]!==undefined?KIND_RANK[r.source]:9},
  {k:"price", t:"最新价", f:r=>(r.gap||{}).last_close},
  {k:"daychg", t:"当日%", f:r=>(r.gap||{}).day_chg},
  {k:"gap", t:"跳空%", f:r=>(r.gap||{}).gap_vs_close},
  {k:"growth", t:"增速%", f:r=>r.growth},
  {k:"growth_basis", t:"口径", l:1, f:r=>{
      let s = r.growth_basis || "—";
      if(r.low_base) s += "·低基数";
      /* 预告型断层靠「预增/扭亏 放行加速度门槛」进来时，加速度可能为负，必须在口径列标出来 */
      if(r.pre_tier === "口径豁免") s += "·加速豁免";
      if(r.forecast_type) s = r.forecast_type + "·" + s;
      return s;
    }},
  {k:"accel", t:"加速pct", f:r=>r.accel},
  {k:"streak", t:"连续期数", f:r=>r.streak},
  {k:"npsingle", t:"单季净利", l:1, f:r=>r.np_single},
  {k:"fill", t:"缺口", l:1, f:r=>!r.gap?"—":(r.gap.valid?(r.gap.filled?"已回补":"未回补"):"未跳空")},
  {k:"after", t:"缺口后%", f:r=>(r.gap||{}).ret_since_gap},
  {k:"mcap", t:"流通市值", l:1, f:r=>(r.gap||{}).mcap},
  {k:"amount", t:"成交额", l:1, f:r=>(r.gap||{}).amount},
  {k:"score", t:"评分", f:r=>r.score},
  {k:"tier", t:"层级", l:1, f:r=>r.tier}
];
let sortKey="score", sortAsc=false;
let VIEW = [];   /* render() 写入：当前筛选 + 排序后的清单，供 K 线弹窗上下翻页 */
let navCodes = [], navIdx = -1, navScope = "";

function paintHead(){
  document.querySelectorAll("#tbl thead th").forEach(x=>{
    const on = x.dataset.k===sortKey;
    x.classList.toggle("on", on);
    x.classList.toggle("asc", on && sortAsc);
    if(on) x.setAttribute("aria-sort", sortAsc?"ascending":"descending");
    else x.removeAttribute("aria-sort");
  });
}
function setSort(k, asc){
  sortKey = k; sortAsc = !!asc;
  const sel = document.getElementById("fsort");
  if(sel && Array.prototype.some.call(sel.options, o=>o.value===k)) sel.value = k;
  paintHead();
  render();
}
document.getElementById("tbl").querySelector("thead").innerHTML =
  headHTML(COLS, sortKey, sortAsc, COLS.filter(c=>c.k!=="kline").map(c=>c.k));

function fillOptions(){
  const inds = {}; ALLROWS.forEach(r=>{ const k=r.industry||"未标注行业"; inds[k]=(inds[k]||0)+1; });
  document.getElementById("find").innerHTML = "<option value=''>全部行业</option>"+
    Object.keys(inds).sort((a,b)=>inds[b]-inds[a]).map(k=>"<option value='"+esc(k)+"'>"+esc(k)+"（"+inds[k]+"）</option>").join("");
  const bs = Array.from(new Set(ALLROWS.map(r=>r.board))).filter(Boolean);
  document.getElementById("fboard").innerHTML = "<option value=''>全部板块</option>"+bs.map(b=>"<option>"+b+"</option>").join("");
  /* 来源下拉带上条数，一眼看出某类来源本轮是否有内容（例如三季报预告窗口还没打开时会显示 0）。
     口径 = 混排后的清单总数，与页面上看到的行数一致。 */
  const scnt = {};
  ALLROWS.forEach(r=>{ scnt[r.source] = (scnt[r.source]||0) + 1; });
  document.getElementById("fsrc").innerHTML = "<option value=''>全部来源</option>"+
    ["业绩预告","业绩快报","正式财报"].map(v=>
      "<option value='"+v+"'>"+v+"（"+(scnt[v]||0)+"）</option>").join("");
}

function visibleRows(){
  const q = (document.getElementById("q").value||"").trim().toLowerCase();
  const find = document.getElementById("find").value;
  const fb = document.getElementById("fboard").value, ft = document.getElementById("ftier").value;
  const fs = (document.getElementById("fsrc")||{}).value || "";
  return ALLROWS.filter(r=>{
    if(find && (r.industry||"未标注行业")!==find) return false;
    if(fb && r.board!==fb) return false;
    if(fs && r.source!==fs) return false;
    if(ft==="低基数"){ if(!r.low_base) return false; }
    else if(ft && r.tier.indexOf(ft)!==0) return false;
    if(!q) return true;
    return (r.code+r.name+(r.industry||"")+(r.tags||[]).join("")+(r.risks||[]).join("")+r.tier+r.source).toLowerCase().indexOf(q)>=0;
  });
}

/* 通用排序比较器：数值列正常排序；文本列保持原序；缺失值（— / null）恒排最后，
   否则按「最新价」升序时会把没有行情数据的行顶到最前面 */
function sortVal(row, col){
  const v = col.f(row);
  if(v===null || v===undefined || v==="—" || isNaN(v)) return null;
  return (typeof v==="number") ? v : 0;
}
function cmpRows(a, b, col, asc){
  const av = sortVal(a, col), bv = sortVal(b, col);
  if(av===null && bv===null) return 0;
  if(av===null) return 1;
  if(bv===null) return -1;
  return asc ? av-bv : bv-av;
}

function render(){
  let data = visibleRows();
  const col = COLS.find(c=>c.k===sortKey) || COLS.find(c=>c.k==="score");
  data = data.slice().sort((a,b)=>cmpRows(a,b,col,sortAsc));
  VIEW = data;
  document.getElementById("cnt").textContent = "共 "+data.length+" 只";
  const tb = document.getElementById("tbl").querySelector("tbody");
  if(!data.length){ tb.innerHTML = "<tr class='empty-row'><td class='empty'>无匹配结果</td></tr>"; return; }
  tb.innerHTML = data.map(r=>{
    const g = r.gap||{};
    const kind = KIND[r.source] ? KIND[r.source].cls : "plain";
    return "<tr data-code='"+r.code+"' data-kind='"+esc(r.source||"")+"' class='k-"+kind+"' tabindex='0' aria-label='"+
      esc(r.name+" "+r.code+"（"+(r.source||"")+"）"+(r.gap_state?("，"+r.gap_state):"")+"，按回车查看 K 线图")+"'>"+COLS.map(c=>{
      let v = c.f(r);
      if(c.k==="kline") v = "<button class='kbtn' data-code='"+r.code+"' aria-label='查看 "+esc(r.name)+" K 线图'>K线</button>";
      else if(c.k==="source") v = kindTag(r.source);
      else if(c.k==="growth"||c.k==="accel") v = "<span class='"+cls(c.f(r))+"'>"+fmt(c.f(r),1)+"</span>";
      else if(c.k==="price") v = (typeof c.f(r)==="number") ? "<span class='px'>"+fmt(c.f(r),2)+"</span>" : "—";
      else if(c.k==="gap"||c.k==="daychg"||c.k==="after") v = "<span class='"+cls(c.f(r))+"'>"+pct(c.f(r)).replace("%","")+"</span>";
      /* 缺口列：预告池个股带 gap_state（尚未跳空 / 已回补），比通用推断更准，优先用它 */
      else if(c.k==="fill") v = r.gap_state
        ? (r.gap_state==="已回补" ? "<span class='mut'>已回补</span>" : "<span class='warnc'>尚未跳空</span>")
        : (!r.gap?"—":(r.gap.valid?(r.gap.filled?"<span class='mut'>已回补</span>":"<span class='up'>未回补</span>"):"<span class='mut'>未跳空</span>"));
      else if(c.k==="mcap"||c.k==="amount"||c.k==="npsingle") v = (typeof c.f(r)==="number" && c.f(r)) ? money(c.f(r)) : "—";
      else if(c.k==="score") v = "<b>"+fmt(r.score,1)+"</b>";
      else if(c.k==="streak") v = streakCell(r);
      else if(c.k==="tier") v = "<span class='tag "+(r.tier.indexOf("核心")===0?"core":(r.tier.indexOf("低基数")>=0?"risk":"watch"))+"'>"+esc(r.tier)+"</span>";
      else if(typeof v==="string") v = esc(v);
      return "<td data-label='"+esc(c.t)+"' class='"+(c.l?"l":"")+"'>"+v+"</td>";
    }).join("")+"</tr>";
  }).join("");
  /* 行的点击 / 回车 / 行内 K 线按钮统一交给 initDelegation() 的事件委托 */
}

/* 连续断层期数：列表单元格（期数 + 悬浮显示单季同比序列） */
function streakCell(r){
  const n = r.streak;
  if(n===null || n===undefined) return "<span class='mut' title='该股历史单季数据不足'>—</span>";
  const tip = streakTip(r);
  if(n <= 0) return "<span class='mut' title='"+esc(tip)+"'>0</span>";
  return "<span class='tag streak' title='"+esc(tip)+"'>"+n+" 期</span>";
}
function streakTip(r){
  const s = r.streak_series||[];
  if(!s.length) return "暂无单季同比序列（历史财报缺失）";
  return "单季同比（近→远）："+s.map(x=>x.label+" "+fmt(x.yoy,1)+"%").join(" · ")+
    (r.streak_from?(" ｜ 断层自 "+r.streak_from+" 起连续 "+r.streak+" 期"):"");
}
/* 弹窗里的「历史各期断层」清单：与 K 线上的虚线标记一一对应，近 → 远 */
function histLine(r){
  const ps = (r.period_gaps||[]).filter(x=>x && x.period);
  if(ps.length < 2) return "";
  const items = ps.map(x=>{
    const cur = x.period===r.period;
    const st = x.valid ? ("跳空 "+fmt(x.gap_pct,2)+"%") : "未跳空";
    const d = x.ann ? ((x.inferred?"≈":"") + String(x.ann).slice(2)) : "日期不明";
    return "<span class='cell"+(x.valid?" gap":"")+"'>"+esc(x.label)+
           "<b class='"+(x.valid?"up":"mut")+"'>"+st+"</b>"+
           "<span class='d'>"+d+(cur?" · 本次":"")+"</span></span>";
  }).join("");
  const n = ps.filter(x=>x.valid).length;
  return "<div class='histline'><span>历史各期断层（近→远）</span>"+items+
    "<span>其中 <b>"+n+"</b> 期伴随有效跳空</span></div>";
}
/* 弹窗 / 明细卡里的序列条 */
function streakLine(r){
  const s = r.streak_series||[];
  if(!s.length) return "";
  return "<div class='streakline'><span>单季同比序列（近→远）</span>"+
    s.map(x=>"<span class='cell'>"+esc(x.label)+" <b class='"+cls(x.yoy)+"'>"+fmt(x.yoy,1)+"%</b></span>").join("")+
    "<span>"+(r.streak>0?("连续 "+r.streak+" 期达标"):"最近一期未达门槛")+"</span></div>";
}
function cards(){
  const top = rows.filter(r=>r.tier.indexOf("核心")===0).slice(0,10);
  const list = top.length ? top : rows.slice(0,10);
  if(!list.length){ document.getElementById("cards").innerHTML="<div class='empty'>暂无断层候选</div>"; return; }
  document.getElementById("cards").innerHTML = list.map(r=>{
    const g = r.gap||{};
    const tagHtml = (r.tags||[]).filter(t=>t.indexOf("核心")!==0&&t.indexOf("观察")!==0&&t.indexOf("跟踪")!==0)
      .map(t=>"<span class='tag'>"+esc(t)+"</span>").join("");
    const riskHtml = (r.risks||[]).map(t=>"<span class='tag risk'>"+esc(t)+"</span>").join("");
    return "<div class='card "+(r.tier.indexOf("核心")===0?"core":"watch")+"' data-code='"+r.code+"' tabindex='0' role='button' aria-label='"+esc(r.name+"，按回车查看 K 线图")+"'>"+
      "<h3><span>"+esc(r.name)+" <span class='code'>"+r.code+"</span></span><span class='tag "+(r.tier.indexOf("核心")===0?"core":"watch")+"'>"+esc(r.tier)+"</span></h3>"+
      "<div style='font-size:12px;color:var(--tx3);margin-top:3px'>"+r.announce+" 公告 · "+esc(r.source)+" · "+esc(r.board)+" · "+esc(r.industry||"行业未标注")+" · 评分 "+fmt(r.score,1)+"</div>"+
      "<div class='metrics'>"+
        "<div><div class='k'>增速("+esc(r.growth_basis||"—")+")</div><div class='v up'>"+fmt(r.growth,1)+"%</div></div>"+
        "<div><div class='k'>加速度pct</div><div class='v "+cls(r.accel)+"'>"+fmt(r.accel,1)+"</div></div>"+
        "<div><div class='k'>连续断层期数</div><div class='v "+((r.streak||0)>=3?"up":"")+"'>"+((r.streak===null||r.streak===undefined)?"—":r.streak)+"</div></div>"+
        "<div><div class='k'>跳空幅度</div><div class='v "+cls(g.gap_vs_close)+"'>"+fmt(g.gap_vs_close,2)+"%</div></div>"+
        "<div><div class='k'>缺口后涨幅</div><div class='v "+cls(g.ret_since_gap)+"'>"+fmt(g.ret_since_gap,2)+"%</div></div>"+
        "<div><div class='k'>单季净利</div><div class='v'>"+money(r.np_single)+"</div></div>"+
      "</div>"+
      streakLine(r)+
      "<div style='font-size:12px;color:var(--tx2);margin-bottom:6px'>缺口日 "+(g.gap_date||"—")+" · 当日涨幅 <span class='"+cls(g.day_chg)+"'>"+fmt(g.day_chg,2)+"%</span> · "+
      (!g.valid?"<span class='mut'>未跳空</span>":(g.filled?("<span class='mut'>缺口已回补</span>"):"<span class='up'>缺口未回补</span>"))+
      "<br>最新价 "+fmt(g.last_close,2)+" 元 · 单季净利 "+money(r.np_single)+" · 流通市值 "+money(g.mcap)+" · 缺口日成交额 "+money(g.amount)+"</div>"+
      "<div style='margin-bottom:6px'>"+tagHtml+"</div>"+
      (riskHtml?"<div style='margin-bottom:6px'>"+riskHtml+"</div>":"")+
      (r.reason?("<div class='note'>"+esc(r.reason)+"</div>"):"")+
      "</div>";
  }).join("");
  /* 卡片的点击 / 回车统一交给 initDelegation() 的事件委托 */
}

/* ---------------- K 线图 ---------------- */
function ma(vals, n){
  const out = []; let s = 0, c = 0;
  for(let i=0;i<vals.length;i++){
    const v = vals[i];
    if(v===null){ out.push(null); continue; }
    s += v; c++;
    if(i>=n){ const old = vals[i-n]; if(old!==null){ s -= old; c--; } }
    out.push(c>=n ? s/n : null);
  }
  return out;
}

function drawChart(r){
  const box = document.getElementById("mChart");
  const tip = document.getElementById("tip");
  tip.style.display = "none";
  chartStock = r;
  const kd = klineOf(r.code);
  if(!kd){
    box.innerHTML = "<div class='empty'>该股暂无行情数据（新股 / 未上市 / 接口无返回）</div>";
    document.getElementById("mLegend").innerHTML="";
    paintRange();
    return;
  }
  const avail = kd.bars.length;
  const floor = Math.min(MIN_BARS, avail);
  const win = Math.max(floor, Math.min(CHART_WIN>0 ? CHART_WIN : avail, avail));
  const end = Math.round(Math.max(win, Math.min(CHART_END===null ? avail : CHART_END, avail)));
  const start = end - win;
  const raw = (start===0 && end===avail) ? kd.bars : kd.bars.slice(start, end);
  const dts = KL_DATES.slice(kd.d0+start, kd.d0+end);
  const W=680,H=402,P={l:44,r:56,t:14,b:20}, VH=66, GAPV=16;
  const priceH = H-P.t-P.b-VH-GAPV;
  const n = raw.length;
  CVST = {avail:avail, win:win, start:start, end:end};
  const closes = raw.map(x=>x?x[3]:null);
  const lows = raw.filter(x=>x).map(x=>x[2]), highs = raw.filter(x=>x).map(x=>x[1]);
  let pmax = Math.max.apply(null, highs), pmin = Math.min.apply(null, lows);
  const pad = (pmax-pmin)*0.08 || 0.5; pmax += pad; pmin -= pad;
  const vmax = Math.max.apply(null, raw.map(x=>x?x[4]:0))||1;
  const bw = (W-P.l-P.r)/n;
  const x = i => P.l + bw*i + bw/2;
  const y = p => P.t + (pmax-p)/(pmax-pmin)*priceH;
  CVST.bw = bw; CVST.P = P; CVST.W = W;
  const vy = v => P.t+priceH+GAPV + (VH - v/vmax*VH);
  let s = "<svg viewBox='0 0 "+W+" "+H+"' width='100%' role='img' aria-label='"+esc(r.name+" K线图，含成交量与 MA5/10/20 均线")+"' style='display:block'>";
  s += "<rect x='"+P.l+"' y='"+P.t+"' width='"+(W-P.l-P.r)+"' height='"+priceH+"' fill='#0e141c' rx='6'/>";
  s += "<rect x='"+P.l+"' y='"+(P.t+priceH+GAPV)+"' width='"+(W-P.l-P.r)+"' height='"+VH+"' fill='#0e141c' rx='6'/>";
  for(let i=0;i<=4;i++){
    const p = pmin + (pmax-pmin)*i/4, yy = y(p);
    s += "<line x1='"+P.l+"' y1='"+yy+"' x2='"+(W-P.r)+"' y2='"+yy+"' stroke='#1b232d'/>";
    s += "<text x='"+(W-P.r+5)+"' y='"+(yy+3.5)+"' fill='#6b7684' font-size='10'>"+p.toFixed(2)+"</text>";
  }
  const gp = r.gap||{};
  const gi = gp.gap_date ? dts.indexOf(gp.gap_date) : -1;
  if(gp.valid && gi>=0 && gp.prev_high!=null && gp.low!=null){
    const yTop = y(gp.prev_high), yBot = y(gp.low);
    const fi = (gp.filled && gp.fill_date) ? dts.indexOf(gp.fill_date) : -1;
    const endIdx = fi>=0 ? Math.max(fi, gi) : n-1;
    const bx = x(gi)-bw/2, bwid = Math.max(x(endIdx)+bw/2-bx, bw);
    const bandCol = gp.filled ? "rgba(79,140,201,.10)" : "rgba(240,72,62,.11)";
    const lineCol = gp.filled ? "rgba(79,140,201,.45)" : "rgba(240,72,62,.4)";
    const txtCol = gp.filled ? "#79a7d8" : "#f0483e";
    const bh = Math.max(Math.abs(yBot-yTop), 5);
    s += "<rect x='"+bx+"' y='"+Math.min(yTop,yBot)+"' width='"+bwid+"' height='"+bh+"' fill='"+bandCol+"' stroke='"+lineCol+"' stroke-dasharray='3 3'/>";
    const lab = gp.filled ? ("缺口 "+String(gp.fill_date||"").slice(5)+" 已回补") : "缺口未回补";
    const lw = lab.length*10 + 6;
    const lx = (bx + lw > W-P.r) ? (W-P.r-4) : (bx+4);
    const la = (bx + lw > W-P.r) ? "end" : "start";
    const ly = Math.max(yTop,yBot)+bh+12;
    const cx0 = la==="end" ? lx-lw : lx-3;
    s += "<rect x='"+cx0+"' y='"+(ly-9.5)+"' width='"+(lw+2)+"' height='13' rx='3' fill='#0b0f16' fill-opacity='0.88' stroke='"+lineCol+"' stroke-width='0.5'/>";
    s += "<text x='"+lx+"' y='"+ly+"' fill='"+txtCol+"' font-size='10' text-anchor='"+la+"'>"+lab+"</text>";
  }
  const ai = idxOnOrAfter(dts, r.announce);
  if(ai>=0){
    s += "<line x1='"+x(ai)+"' y1='"+P.t+"' x2='"+x(ai)+"' y2='"+(P.t+priceH+GAPV+VH)+"' stroke='#d9a13b' stroke-dasharray='4 3'/>";
    s += "<text x='"+(x(ai)+4)+"' y='"+(P.t+11)+"' fill='#d9a13b' font-size='10'>公告</text>";
  }
  /* ---- 历史各期断层（连续 ≥2 期才有）：每期公告日一条细虚线，当期真跳空了再画一小段淡红色带。
        按「报告期」排除本股当前这一期 —— 不能用 slice(1)，因为当前这一期不一定就是
        period_gaps 的第一项（例如靠业绩预告入选、但连续断层起点在上一期）。
        色带必须画在 K 线之前（否则会盖住蜡烛），线条与标签放到最后画（否则会被蜡烛遮住）。 ---- */
  const pgs = (r.period_gaps||[]).filter(x=>x && x.ann && x.period!==r.period);
  const histPts = [];
  pgs.forEach(pg=>{
    const pi = idxOnOrAfter(dts, pg.ann);
    if(pi < 0) return;                                  /* 该期公告日在当前视窗之外 */
    if(pg.valid){
      const gi2 = idxOnOrAfter(dts, pg.gap_date);
      if(gi2 >= 0){
        const e2 = Math.min(gi2+14, n-1);
        const bx2 = x(gi2)-bw/2;
        s += "<rect x='"+bx2+"' y='"+P.t+"' width='"+Math.max(x(e2)+bw/2-bx2, bw)+"' height='"+priceH+"' fill='rgba(240,72,62,.07)'/>";
      }
    }
    histPts.push({i:pi, pg:pg});
  });
  raw.forEach((v,i)=>{
    if(!v) return;
    const o=v[0], h=v[1], l=v[2], c=v[3], vol=v[4];
    const up = c>=o, col = up ? "#f0483e" : "#22a06b";
    /* data-wick 只给蜡烛影线：自检按它统计可见根数，历史断层虚线不会被算进去 */
    s += "<line data-wick='1' x1='"+x(i)+"' y1='"+y(h)+"' x2='"+x(i)+"' y2='"+y(l)+"' stroke='"+col+"' stroke-width='1'/>";
    const bt = y(Math.max(o,c)), bb = y(Math.min(o,c));
    s += "<rect x='"+(x(i)-bw*0.32)+"' y='"+bt+"' width='"+(bw*0.64)+"' height='"+Math.max(bb-bt,0.8)+"' fill='"+(up?"none":col)+"' stroke='"+col+"' stroke-width='1'/>";
    s += "<rect x='"+(x(i)-bw*0.32)+"' y='"+vy(vol)+"' width='"+(bw*0.64)+"' height='"+(P.t+priceH+GAPV+VH-vy(vol))+"' fill='"+col+"' fill-opacity='0.5'/>";
  });
  [["MA5",5,"#e0b64a"],["MA10",10,"#6fa8dc"],["MA20",20,"#c586c0"]].forEach(m=>{
    const arr = ma(closes, m[1]);
    let d = "", started = false;
    arr.forEach((v,i)=>{ if(v===null){ started=false; return; } d += (started?" L":" M")+x(i).toFixed(1)+" "+y(v).toFixed(1); started=true; });
    if(d) s += "<path d='"+d+"' fill='none' stroke='"+m[2]+"' stroke-width='1.2'/>";
  });
  /* 历史各期断层的竖线与期次标签：放在最上层，避免被蜡烛 / 均线遮住 */
  histPts.forEach((hp, k)=>{
    const col = hp.pg.valid ? "#c9924a" : "#5d6470";
    s += "<line x1='"+x(hp.i)+"' y1='"+P.t+"' x2='"+x(hp.i)+"' y2='"+(P.t+priceH)+"' stroke='"+col+"' stroke-width='1' stroke-dasharray='2 4'/>";
    /* ≈ = 该期公告日不可信（东财会刷新成后续公告的日期），是按跳空反推的位置 */
    const lab = (hp.pg.inferred ? "≈" : "") + shortLabel(hp.pg.label) +
                (hp.pg.valid ? "" : " 未跳空");
    const tw = lab.length*9.5 + 7;
    const ly2 = P.t + ((k % 2) ? 24 : 13);
    const lx2 = Math.min(Math.max(x(hp.i)+3, P.l+1), W-P.r-tw);
    s += "<rect x='"+lx2+"' y='"+(ly2-9)+"' width='"+tw+"' height='12' rx='2.5' fill='#0b0f16' fill-opacity='0.9'/>";
    s += "<text x='"+(lx2+2)+"' y='"+ly2+"' fill='"+col+"' font-size='9.5'>"+lab+"</text>";
  });
  const step = Math.max(1, Math.floor(n/6));
  for(let i=0;i<n;i+=step){ s += "<text x='"+x(i)+"' y='"+(H-6)+"' fill='#6b7684' font-size='9.5' text-anchor='middle'>"+String(dts[i]||"").slice(5)+"</text>"; }
  s += "<rect id='hit' x='"+P.l+"' y='"+P.t+"' width='"+(W-P.l-P.r)+"' height='"+(priceH+VH+GAPV)+"' fill='transparent'/>";
  s += "<g id='cross' style='display:none'><line id='cx' y1='"+P.t+"' y2='"+(P.t+priceH+GAPV+VH)+"' stroke='#9aa7b4' stroke-width='0.8' stroke-dasharray='3 3'/><line id='cy' x1='"+P.l+"' x2='"+(W-P.r)+"' stroke='#9aa7b4' stroke-width='0.8' stroke-dasharray='3 3'/></g>";
  s += "</svg>";
  box.innerHTML = s;
  const svg = box.querySelector("svg");
  const hit = svg.querySelector("#hit"), cross = svg.querySelector("#cross");
  hit.addEventListener("mousemove", ev=>{
    if(dragging){ tip.style.display="none"; cross.style.display="none"; return; }  /* 拖动平移时不弹十字光标 */
    const rect = svg.getBoundingClientRect();
    const rx = (ev.clientX-rect.left)/rect.width*W;
    const i = Math.min(n-1, Math.max(0, Math.round((rx-P.l-bw/2)/bw)));
    const v = raw[i]; if(!v){ tip.style.display="none"; return; }
    const o=v[0], h=v[1], l=v[2], c=v[3], vol=v[4];
    cross.style.display = "";
    svg.querySelector("#cx").setAttribute("x1", x(i)); svg.querySelector("#cx").setAttribute("x2", x(i));
    svg.querySelector("#cy").setAttribute("y1", y(c)); svg.querySelector("#cy").setAttribute("y2", y(c));
    tip.style.display = "block";
    tip.innerHTML = "<b>"+dts[i]+"</b><br>开 "+o.toFixed(2)+" 高 "+h.toFixed(2)+"<br>低 "+l.toFixed(2)+" 收 <span class='"+cls(c-o)+"'>"+c.toFixed(2)+"</span><br>涨跌 <span class='"+cls(c-o)+"'>"+((c/o-1)*100).toFixed(2)+"%</span> · 量 "+(vol/1e4).toFixed(2)+"万手";
    const px = (x(i)/W)*rect.width, py = (y(c)/H)*rect.height;
    tip.style.left = Math.min(Math.max(px+12, 6), rect.width-150)+"px";
    tip.style.top = Math.max(py-64, 6)+"px";
  });
  hit.addEventListener("mouseleave", ()=>{ tip.style.display="none"; cross.style.display="none"; });
  document.getElementById("mLegend").innerHTML =
    "<span><i style='background:#f0483e'></i>阳线</span><span><i style='background:#22a06b'></i>阴线</span>"+
    "<span><i style='background:#e0b64a'></i>MA5</span><span><i style='background:#6fa8dc'></i>MA10</span><span><i style='background:#c586c0'></i>MA20</span>"+
    "<span><i style='background:rgba(240,72,62,.5)'></i>跳空缺口区间</span>"+
    (histPts.length ? "<span><i style='background:#c9924a'></i>历史断层期（≈ 公告日按跳空反推）</span>" : "");
  paintRange();
}

/* ---------- 视窗操作：区间按钮 / 滚轮缩放 / 拖动平移 / 回到最新（同花顺式） ---------- */
/* 统一改视窗；返回 false 表示没有实际变化（拖动时大量重复事件由此省掉重绘） */
function setView(win, end){
  if(!CVST || !chartStock) return false;
  const avail = CVST.avail, floor = Math.min(MIN_BARS, avail);
  const w = Math.max(floor, Math.min(Math.round(win), avail));
  const e2 = Math.max(w, Math.min(Math.round(end), avail));
  if(CVST.win===w && CVST.end===e2) return false;
  CHART_WIN = (w>=avail) ? 0 : w;      /* 0 表示「全部」，与区间按钮的取值约定一致 */
  CHART_END = (e2>=avail) ? null : e2; /* null 表示贴住最新交易日 */
  drawChart(chartStock);
  return true;
}
/* 缩放：t ∈ [0,1] 是锚点在窗口内的相对位置，保证缩放前后该点对应的 K 线不动（同花顺手感） */
function zoomBy(k, t){
  if(!CVST) return;
  const avail = CVST.avail, floor = Math.min(MIN_BARS, avail);
  const win = CVST.win, start = CVST.start;
  const anchor = start + t*win;
  const nw = Math.max(floor, Math.min(Math.round(win*k), avail));
  if(nw===win) return;
  setView(nw, anchor + (1-t)*nw);
}
function svgRect(){
  const svg = document.querySelector("#mChart svg");
  return (svg && typeof svg.getBoundingClientRect==="function") ? svg.getBoundingClientRect() : null;
}
function vbScale(){                     /* 客户端像素 → viewBox 单位的换算；测不到时退化为 1 */
  const r = svgRect();
  return (r && r.width>0 && CVST) ? CVST.W/r.width : 1;
}
function anchorT(clientX){
  const r = svgRect();
  if(!r || r.width<=0 || !CVST) return 0.5;   /* 无布局信息（jsdom / 隐藏）时取中点 */
  const vx = (clientX - r.left) * (CVST.W/r.width);
  return Math.max(0, Math.min(1, (vx - CVST.P.l) / (CVST.W - CVST.P.l - CVST.P.r)));
}
function hideTip(){ const t = document.getElementById("tip"); if(t) t.style.display = "none"; }

/* ---------- 区间栏：快捷区间 + 缩放按钮 + 回到最新 + 位置指示 ---------- */
function paintRange(){
  const el = document.getElementById("mRange");
  if(!el) return;
  const kd = chartStock ? klineOf(chartStock.code) : null;
  const avail = kd ? kd.bars.length : 0;
  if(!avail){ el.innerHTML = ""; el.hidden = true; return; }
  el.hidden = false;
  const win = CVST ? CVST.win : avail;
  const start = CVST ? CVST.start : 0, end = CVST ? CVST.end : avail;
  let h = "<span class='mrl'>区间</span>";
  WIN_OPTS.forEach(o=>{
    const w = o[0];
    const on = (w===0) ? (win>=avail) : (win===w && end>=avail);   /* 已经拖到历史里就不再高亮 */
    const dis = (w>0 && avail<=w);
    h += "<button type='button' data-win='"+w+"' aria-pressed='"+(on?"true":"false")+"'"+
         (dis?" disabled title='该股仅 " + avail + " 个交易日，不足 " + w + " 日'":"")+">"+o[1]+"</button>";
  });
  h += "<span class='mrz'>"+
       "<button type='button' data-act='zoomout' aria-label='缩小 K 线（显示更多）' title='缩小（键盘 −）'>－</button>"+
       "<button type='button' data-act='zoomin' aria-label='放大 K 线（显示更少）' title='放大（键盘 ＋）'>＋</button>"+
       (end<avail ? "<button type='button' data-act='latest' class='latest' title='回到最新交易日（双击图表 / Home 亦可）'>↦ 回到最新</button>" : "")+
       "</span>";
  const used = chartStock && (chartStock.streak||0) >= 2
    ? " · 连续断层 "+chartStock.streak+" 期，已自动放宽视窗以覆盖最早一期" : "";
  /* 缺口日被拖出视野时必须提示，否则用户会以为缺口标记丢了 */
  let warn = "";
  const gp = (chartStock && chartStock.gap) || {};
  if(kd && gp.gap_date){
    const giFull = KL_DATES.indexOf(gp.gap_date) - kd.d0;
    if(giFull < 0 || giFull < start || giFull >= end) warn = " · <b>缺口日在窗口外</b>";
  }
  h += "<span class='mrn'>显示 "+(end-start)+" 根 · 第 "+(start+1)+"–"+end+" / 共 "+avail+" 个交易日"+used+warn+"</span>";
  el.innerHTML = h;
}
document.getElementById("mRange").addEventListener("click", e=>{
  const b = e.target.closest("button");
  if(!b || b.disabled) return;
  if(b.dataset.win != null){                    /* 快捷区间：把视窗拉到最新 */
    CHART_WIN = parseInt(b.dataset.win,10)||0;
    CHART_END = null;
    if(chartStock) drawChart(chartStock);
    return;
  }
  const act = b.dataset.act;
  if(act==="zoomin") zoomBy(1/1.25, 0.5);
  else if(act==="zoomout") zoomBy(1.25, 0.5);
  else if(act==="latest" && CVST) setView(CVST.win, CVST.avail);
});

/* ---------- 同花顺式直接操作：滚轮缩放 / 拖动平移 / 捏合 / 双击回到最新 ---------- */
const chartBox = document.getElementById("chartbox");
const ptrs = new Map();
let dragState = null;      /* {x, base}  base = 按下时的右端下标（拖动全程以它为基准，避免累计误差） */
let pinchState = null;     /* {dist, win, start} */

chartBox.addEventListener("wheel", e=>{
  if(!CVST) return;
  e.preventDefault();                            /* 阻止页面滚动，滚轮只用于缩放 */
  zoomBy(e.deltaY>0 ? 1.18 : 1/1.18, anchorT(e.clientX));
}, {passive:false});

chartBox.addEventListener("pointerdown", e=>{
  if(!CVST) return;
  ptrs.set(e.pointerId, {x:e.clientX, y:e.clientY});
  if(typeof chartBox.setPointerCapture === "function"){ try{ chartBox.setPointerCapture(e.pointerId); }catch(_){} }
  if(ptrs.size===1){
    dragState = {x:e.clientX, base:CVST.end};
  } else if(ptrs.size>=2){
    dragState = null;
    const p = Array.from(ptrs.values());
    pinchState = {dist:Math.hypot(p[0].x-p[1].x, p[0].y-p[1].y) || 1, win:CVST.win, start:CVST.start};
  }
});

chartBox.addEventListener("pointermove", e=>{
  if(!CVST) return;
  if(ptrs.has(e.pointerId)) ptrs.set(e.pointerId, {x:e.clientX, y:e.clientY});

  if(pinchState && ptrs.size>=2){                /* 双指捏合：以两指中点为锚点 */
    const p = Array.from(ptrs.values());
    const d = Math.hypot(p[0].x-p[1].x, p[0].y-p[1].y) || 1;
    const floor = Math.min(MIN_BARS, CVST.avail);
    const nw = Math.max(floor, Math.min(Math.round(pinchState.win * (pinchState.dist/d)), CVST.avail));
    const t = anchorT((p[0].x+p[1].x)/2);
    setView(nw, (pinchState.start + t*pinchState.win) + (1-t)*nw);
    return;
  }

  if(!dragState || ptrs.size!==1) return;
  const dx = e.clientX - dragState.x;
  if(Math.abs(dx) > 2 && !dragging){ dragging = true; chartBox.classList.add("dragging"); hideTip(); }
  if(!dragging) return;
  /* 往右拖 = 看更早的历史（内容跟手） */
  setView(CVST.win, dragState.base - dx*vbScale()/(CVST.bw||1));
});

function endPtr(e){
  if(e) ptrs.delete(e.pointerId);
  if(ptrs.size<2) pinchState = null;
  if(ptrs.size===0){
    dragState = null;
    if(dragging){ dragging = false; chartBox.classList.remove("dragging"); }
  }
}
chartBox.addEventListener("pointerup", endPtr);
chartBox.addEventListener("pointercancel", endPtr);
chartBox.addEventListener("pointerleave", e=>{ if(!ptrs.size) endPtr(e); });
chartBox.addEventListener("dblclick", e=>{
  if(!CVST) return;
  e.preventDefault();
  setView(CVST.win, CVST.avail);                 /* 双击 = 回到最新 */
});

let lastFocus = null;

/* ---------- K 线弹窗：上/下一个翻页（按当前清单顺序：含筛选与排序） ---------- */
function buildNav(code){
  let list, scope;
  if(VIEW.some(x=>x.code===code)){ list = VIEW; scope = "当前断层清单（含筛选与排序）"; }
  else { list = rows; scope = "全部断层候选"; }
  navCodes = list.map(x=>x.code);
  navIdx = navCodes.indexOf(code);
  navScope = scope;
  paintNav();
}
function paintNav(){
  const bp = document.getElementById("mPrev"), bn = document.getElementById("mNext"), pos = document.getElementById("mPos");
  const total = navCodes.length;
  if(!total || navIdx<0){
    bp.disabled = true; bn.disabled = true;
    pos.textContent = "—";
    pos.title = "该个股不在可翻页的清单中";
    return;
  }
  bp.disabled = navIdx <= 0;
  bn.disabled = navIdx >= total-1;
  pos.textContent = (navIdx+1)+" / "+total;
  pos.title = "翻页范围："+navScope+" · 快捷键 ↑ / ↓（← / → 用于 K 线平移）";
}
function stepKline(delta){
  const n = navIdx + delta;
  if(!navCodes.length || n < 0 || n >= navCodes.length) return;
  openKline(navCodes[n], true);
}
document.getElementById("mPrev").addEventListener("click", ()=>stepKline(-1));
document.getElementById("mNext").addEventListener("click", ()=>stepKline(1));

function openKline(code, keep){
  const r = ALLROWS.find(x=>x.code===code);
  if(!r) return;
  const modal = document.getElementById("modal");
  const wasOpen = modal.classList.contains("on");
  if(!wasOpen) lastFocus = document.activeElement;   /* 翻页时不要把焦点记在弹窗内的按钮上 */
  const g = r.gap||{};
  document.getElementById("mTitle").innerHTML = esc(r.name)+"<span class='code'>"+r.code+" · "+esc(r.board)+" · "+esc(r.industry||"行业未标注")+"</span>";
  document.getElementById("mSub").innerHTML =
    kindTag(r.source)+" "+r.announce+" 公告 · "+esc(r.tier||"—")+" · 评分 <b>"+fmt(r.score,1)+"</b>"+
    (r.gap_state ? (" · <span class='warnc'>"+esc(r.gap_state)+"</span>") : "")+
    (r.growth_basis?(" · 增速口径 "+esc(r.growth_basis)):"");
  document.getElementById("mMetrics").innerHTML = [
    ["增速", fmt(r.growth,1)+"%", "up"],
    ["口径", r.growth_basis||"—", ""],
    ["加速度", fmt(r.accel,1)+"pct", cls(r.accel)],
    ["连续断层", (r.streak===null||r.streak===undefined)?"—":(r.streak+" 期"), ((r.streak||0)>=3?"up":(r.streak?"":"mut"))],
    ["单季净利", money(r.np_single), ""],
    ["跳空幅度", fmt(g.gap_vs_close,2)+"%", cls(g.gap_vs_close)],
    ["缺口状态", !r.gap?"—":(r.gap.valid?(r.gap.filled?"已回补":"未回补"):"未跳空（<"+meta.thresholds.min_gap+"%）"), r.gap&&r.gap.valid&&!r.gap.filled?"up":"mut"],
    ["缺口价区", (r.gap&&r.gap.valid)?(fmt(r.gap.prev_high,2)+" ~ "+fmt(r.gap.low,2)):"—", ""],
    ["回补日", (g.valid&&g.filled)?(g.fill_date||"—"):"—", ""],
    ["缺口后涨幅", fmt(g.ret_since_gap,2)+"%", cls(g.ret_since_gap)],
    ["流通市值", money(g.mcap), ""]
  ].map(x=>"<div><div class='k'>"+x[0]+"</div><div class='v "+x[2]+"'>"+x[1]+"</div></div>").join("");
  document.getElementById("mStreak").innerHTML = streakLine(r);
  document.getElementById("mHist").innerHTML = histLine(r);
  document.getElementById("mTags").innerHTML = (r.tags||[]).map(t=>"<span class='tag'>"+esc(t)+"</span>").join("")+
    (r.risks||[]).map(t=>"<span class='tag risk'>"+esc(t)+"</span>").join("");
  document.getElementById("mNote").innerHTML = r.reason?("<div class='note' style='max-height:120px'>"+esc(r.reason)+"</div>"):"";
  CHART_END = null;      /* 换成另一只个股时回到最新 */
  CHART_WIN = autoWin(r);/* 连续多期断层的个股自动放宽到能看见最早那一期，单期个股仍是最新 120 根 */
  dragging = false;
  chartBox.classList.remove("dragging");
  drawChart(r);
  modal.classList.add("on");
  document.body.style.overflow = "hidden";
  buildNav(code);
  if(wasOpen){
    const box = modal.querySelector(".mbox");
    if(box && typeof box.scrollTo === "function") box.scrollTo(0,0); else if(box) box.scrollTop = 0;
  } else {
    document.getElementById("mClose").focus();
  }
}
function closeKline(){
  const m = document.getElementById("modal");
  if(!m.classList.contains("on")) return;
  m.classList.remove("on");
  document.body.style.overflow = "";
  if(lastFocus && lastFocus.focus) lastFocus.focus();
}
document.getElementById("mClose").addEventListener("click", closeKline);
document.getElementById("modal").addEventListener("click", e=>{ if(e.target.id==="modal") closeKline(); });
document.addEventListener("keydown", e=>{
  const m = document.getElementById("modal");
  if(!m.classList.contains("on")) return;
  if(e.key==="Escape"){ e.preventDefault(); closeKline(); return; }
  if(e.key==="ArrowDown"){ e.preventDefault(); stepKline(1); return; }
  if(e.key==="ArrowUp"){ e.preventDefault(); stepKline(-1); return; }
  /* ← / → 与同花顺一致：平移 K 线看历史（按住 Shift 加速 5 倍）；翻页只留 ↑ / ↓ */
  if(e.key==="ArrowLeft" || e.key==="ArrowRight"){
    if(!CVST) return;
    e.preventDefault();
    setView(CVST.win, CVST.end + (e.shiftKey ? 25 : 5) * (e.key==="ArrowLeft" ? -1 : 1));
    return;
  }
  if(e.key==="+" || e.key==="="){ if(CVST){ e.preventDefault(); zoomBy(1/1.25, 0.5); } return; }
  if(e.key==="-" || e.key==="_"){ if(CVST){ e.preventDefault(); zoomBy(1.25, 0.5); } return; }
  if(e.key==="Home"){ if(CVST){ e.preventDefault(); setView(CVST.win, CVST.avail); } return; }
  if(e.key==="End"){ if(CVST){ e.preventDefault(); setView(CVST.avail, CVST.avail); } return; }
  if(e.key==="Tab"){
    /* 必须排除 disabled 按钮，否则焦点会从弹窗逃逸 */
    const f = Array.from(m.querySelectorAll("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])")).filter(el=>!el.disabled);
    if(!f.length) return;
    const first = f[0], last = f[f.length-1];
    if(e.shiftKey && document.activeElement===first){ e.preventDefault(); last.focus(); }
    else if(!e.shiftKey && document.activeElement===last){ e.preventDefault(); first.focus(); }
  }
});
/* ---------------- 事件委托：清单 / 板块表 / 分布条 / 卡片都只绑一次 ---------------- */
function initDelegation(){
  /* 断层清单：行与行内「K线」按钮同源，closest 都解析到同一个代码，无需再单独绑按钮 */
  const tbody = document.getElementById("tbl").querySelector("tbody");
  tbody.addEventListener("click", e=>{
    const el = e.target.closest("[data-code]");
    if(el) openKline(el.dataset.code);
  });
  tbody.addEventListener("keydown", e=>{
    if(e.key!=="Enter" && e.key!==" ") return;
    if(e.target.dataset && e.target.dataset.code){ e.preventDefault(); openKline(e.target.dataset.code); }
  });

  /* 清单表头排序：鼠标点击与键盘 Enter / 空格等效 */
  const thead = document.getElementById("tbl").querySelector("thead");
  const fire = th=>{
    const k = th.dataset.k;
    if(!k || th.classList.contains("ns")) return;
    setSort(k, sortKey===k ? !sortAsc : false);
  };
  thead.addEventListener("click", e=>{ const th = e.target.closest("th"); if(th) fire(th); });
  thead.addEventListener("keydown", e=>{
    if(e.key!=="Enter" && e.key!==" ") return;
    const th = e.target.closest("th"); if(!th) return;
    e.preventDefault(); fire(th);
  });

  /* 板块分布条 */
  document.getElementById("sectorbars").addEventListener("click", e=>{
    const b = e.target.closest(".bar");
    if(b && b.dataset.ind) filterByIndustry(b.dataset.ind);
  });

  /* 板块全景表：行（筛选）与表头（排序） */
  const stbl = document.getElementById("stbl");
  const sbody = stbl.querySelector("tbody"), shead = stbl.querySelector("thead");
  sbody.addEventListener("click", e=>{
    const tr = e.target.closest("tr[data-ind]"); if(tr) filterByIndustry(tr.dataset.ind);
  });
  sbody.addEventListener("keydown", e=>{
    if(e.key!=="Enter" && e.key!==" ") return;
    const tr = e.target.closest("tr[data-ind]"); if(!tr || tr!==e.target) return;
    e.preventDefault(); filterByIndustry(tr.dataset.ind);
  });
  shead.addEventListener("click", e=>{ const th = e.target.closest("th"); if(th && th.dataset.k) sectorSort(th.dataset.k); });
  shead.addEventListener("keydown", e=>{
    if(e.key!=="Enter" && e.key!==" ") return;
    const th = e.target.closest("th"); if(!th || !th.dataset.k) return;
    e.preventDefault(); sectorSort(th.dataset.k);
  });

  /* 明细分卡 */
  const cardsBox = document.getElementById("cards");
  cardsBox.addEventListener("click", e=>{ const c = e.target.closest("[data-code]"); if(c) openKline(c.dataset.code); });
  cardsBox.addEventListener("keydown", e=>{
    if(e.key!=="Enter" && e.key!==" ") return;
    const c = e.target.closest("[data-code]"); if(!c || c!==e.target) return;
    e.preventDefault(); openKline(c.dataset.code);
  });

  /* 断层强度分布的气泡：点一下直接打开该股 K 线。
     容器只在初始化时取一次，scatter() 只换 innerHTML、容器本身不重建，委托长期有效。 */
  const scBox = document.getElementById("scatter");
  scBox.addEventListener("click", e=>{
    const c = e.target.closest("circle.pt[data-code]");
    if(c) openKline(c.dataset.code);
  });
}

scatter(); sectorBars(); renderSectors(); fillOptions(); render(); cards();
initDelegation();
["q","find","fboard","fsrc","ftier"].forEach(id=>{ const el=document.getElementById(id); el.addEventListener("input",render); el.addEventListener("change",render); });
document.getElementById("fsort").addEventListener("change", e=>{ if(e.target.value) setSort(e.target.value, false); });
document.getElementById("reset").addEventListener("click", ()=>{
  ["q","find","fboard","fsrc","ftier"].forEach(id=>{ document.getElementById(id).value=""; });
  document.getElementById("fsort").value="score";
  sortKey="score"; sortAsc=false;
  paintHead();
  render();
});
document.getElementById("foot").innerHTML =
  "数据源："+(meta.sources||[]).join(" · ")+"<br>"+
  "生成时间："+meta.generated_at+" · 扫描脚本：src/profit_gap.py · 本页由 src/build_workbench.py 自动生成<br>"+
  "<b>本报告仅供研究参考，不构成个人投资建议。</b>";

/* 深链：利润断层工作台.html#k=300378 直接打开该股 K 线 */
function applyHash(){
  const m = /(?:^|[#&])k=(\d{6})/.exec(location.hash||"");
  if(m) openKline(m[1]);
}
window.addEventListener("hashchange", applyHash);
applyHash();

/* ================= 交易日历 · 外部模块 ==================================
   集成方式：iframe 嵌入 + 全屏覆盖层。
   为什么选它而不是「源码级合并 / 内联」：
     1) 日历是独立部署的三端应用（本机工作台 / GitHub Pages / WorkBuddy 云端，
        还带微信小程序与云函数后端），有自己的发布链路；合并等于每次它更新
        都要重新对齐一遍，且违反「两个模块可独立访问、互不干扰」。
     2) 它是 body{overflow:hidden} + .app{height:100dvh} 的全屏应用，
        内联进本页文档流没有确定高度。
     3) 远端已实测不返回 X-Frame-Options / CSP frame-ancestors，允许被嵌入。
   预留升级位：把 CAL.mode 改成 "api"，并让 calLoad() 改为取数自行渲染，
   下面这层 UI 与交互一行都不用动；#calendar 深链就是将来做独立路由的接缝。
   ======================================================================= */
;(function(){
  var CAL = {
    mode: "iframe",                                   // "iframe"（当前）| "api"（预留）
    url:  "https://market-calendar-71280.app.workbuddy.host/",
    timeout: 12000                                    // ms，超时后给兜底 UI
  };
  function calEl(id){ return document.getElementById(id); }
  var shell = calEl("calShell"), mask = calEl("calMask"), frame = calEl("calFrame"),
      loadBox = calEl("calLoad"), fb = calEl("calFb"), fbMsg = calEl("calFbMsg"),
      tabHome = calEl("tabHome"), tabCal = calEl("tabCal");
  if(!shell || !frame) return;

  var timer = null, loaded = false, lastFocus = null;

  function isOpen(){ return shell.classList.contains("on"); }
  function show(node, v){ if(node) node.classList.toggle("on", !!v); }
  function setTab(isCal){
    if(tabCal)  tabCal.setAttribute("aria-current", isCal ? "true" : "false");
    if(tabHome) tabHome.setAttribute("aria-current", isCal ? "false" : "true");
  }
  function setHash(h){ try { history.replaceState(null, "", h); } catch(e){} }
  function fail(msg){ show(loadBox, false); if(fbMsg) fbMsg.textContent = msg; show(fb, true); }

  function calLoad(){
    loaded = false;
    show(fb, false); show(loadBox, true);
    if(timer) clearTimeout(timer);
    timer = setTimeout(function(){
      if(!loaded){
        fail("加载超时（超过 " + (CAL.timeout / 1000) + " 秒）。可能是网络较慢，或浏览器按第三方站点策略限制了嵌入。可重试，或直接在新窗口打开——功能完全一致。");
      }
    }, CAL.timeout);
    frame.src = CAL.url;
  }

  frame.addEventListener("load", function(){
    if(!isOpen()) return;                      // 页面初始化时的空 load，忽略
    loaded = true;
    if(timer) clearTimeout(timer);
    show(loadBox, false);
    // 跨域时读 location 必然抛错——那恰好证明内容真的加载出来了；
    // 只有同源（about:blank，或被拒绝嵌入后回落）才读得到，此时判定为失败。
    var blocked = false;
    try {
      var href = frame.contentWindow.location.href;
      if(!href || href === "about:blank") blocked = true;
    } catch(e) { /* 跨域 = 正常 */ }
    if(blocked){
      fail("目标站点不允许被嵌入（X-Frame-Options / CSP 限制）。请改用「在新窗口打开」。");
    }
  });
  frame.addEventListener("error", function(){
    loaded = true;
    if(timer) clearTimeout(timer);
    fail("网络异常，无法加载交易日历。请检查网络后重试。");
  });

  function calOpen(){
    if(isOpen()) return;
    lastFocus = document.activeElement;
    shell.classList.add("on");
    if(mask) mask.classList.add("on");
    document.body.style.overflow = "hidden";
    setTab(true);
    if(!frame.getAttribute("src")) calLoad();
    var c = calEl("calClose"); if(c) c.focus();
    setHash("#calendar");
  }
  function calClose(){
    if(!isOpen()) return;
    shell.classList.remove("on");
    if(mask) mask.classList.remove("on");
    document.body.style.overflow = "";
    setTab(false);
    if(timer) clearTimeout(timer);
    show(loadBox, false); show(fb, false);
    frame.removeAttribute("src");              // 彻底停掉，避免后台继续跑
    setHash(location.pathname + location.search);
    if(lastFocus && lastFocus.focus) lastFocus.focus();
  }

  if(tabCal)  tabCal.addEventListener("click", calOpen);
  if(tabHome) tabHome.addEventListener("click", function(){ calClose(); window.scrollTo({top:0, behavior:"smooth"}); });
  if(mask)    mask.addEventListener("click", calClose);
  [["calClose","calClose"],["calRetry","calLoad"],["calFbRetry","calLoad"]].forEach(function(p){
    var el = calEl(p[0]);
    if(!el) return;
    el.addEventListener("click", p[1] === "calClose" ? calClose : calLoad);
  });

  document.addEventListener("keydown", function(e){
    if((e.key === "Escape" || e.key === "Esc") && isOpen()){ e.preventDefault(); calClose(); }
  });
  // 精简焦点陷阱：Tab 只在覆盖层内循环，不会跑到背后的清单表格去
  shell.addEventListener("keydown", function(e){
    if(e.key !== "Tab") return;
    var f = shell.querySelectorAll("button, a[href], iframe, [tabindex]:not([tabindex='-1'])");
    if(!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if(e.shiftKey && document.activeElement === first){ e.preventDefault(); last.focus(); }
    else if(!e.shiftKey && document.activeElement === last){ e.preventDefault(); first.focus(); }
  });

  function calSyncHash(){
    if(location.hash === "#calendar"){ calOpen(); }
    else if(isOpen()){ calClose(); }
  }
  window.addEventListener("hashchange", calSyncHash);
  if(location.hash === "#calendar") calOpen();
})();
</script>
</body>
</html>
"""


def build(json_path: str, out_path: str) -> str:
    with open(json_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    payload.setdefault("meta", {})
    payload["meta"].setdefault("generated_at", dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    payload["meta"].setdefault("thresholds", {})
    payload["meta"]["thresholds"].setdefault("hist_days", None)
    payload.setdefault("summary", {})
    payload.setdefault("candidates", [])
    payload.setdefault("sectors", [])
    payload.setdefault("kline", {"dates": [], "data": {}})
    # 数据以 <script type="application/json"> 承载，再由 JSON.parse 读取。
    # 把「<」转义成 \u003c，彻底杜绝字段里出现 </script> 或 <!-- 截断脚本（\u003c 是合法 JSON 转义）
    data_json = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    html = TPL.replace("__DATA__", data_json)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=os.path.join(ROOT, "data", "scan_latest.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "利润断层工作台.html"))
    a = ap.parse_args()
    print(build(a.json, a.out))


if __name__ == "__main__":
    main()
