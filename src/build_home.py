#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
个人投资工作台 · 单文件 HTML 生成器
====================================
把两份数据 + 一个外部应用合成一个带分页侧栏的聚合页：

  页卡 1 · 投资日历（主页）  ← data/calendar_events.json（src/calendar_events.py 产出）
            月历网格 + 按月切换；点某天看当天事件（日期 / 类型 / 关联标的 / 说明）
  页卡 2 · 指数看盘         ← 外部应用（已独立部署），iframe 懒加载
  页卡 3 · 利润断层选股平台  ← data/scan_latest.json（src/profit_gap.py 产出）
            列表：名称与代码 / 断层日期 / 断层幅度 / 连续断层 / 当日涨跌幅 / 成交量 / 所属行业
            支持日期区间筛选与断层幅度排序

产出：个人投资工作台.html（主产物）+ home.html（ASCII 别名，给 GitHub Pages 当入口）

设计约定：
  - 深色主题、配色与「利润断层工作台」完全一致（同一套 CSS 变量）
  - 单文件自包含，不加载任何 CDN，双击即可打开
  - 桌面左侧竖排页卡；≤900px 折叠为顶部固定横条（触屏没有悬停，横条才看得见）
  - 首屏固定落在主页「投资日历」；直达用 URL hash：#calendar / #indices / #picks
  - 红涨绿跌（中国大陆习惯）
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TPL = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>个人投资工作台</title>
<style>
:root{
  color-scheme:dark;
  --bg:#0d1117; --panel:#151b23; --panel2:#1b232d; --line:#242c37; --line2:#3b4557; --ctl:#5a6577;
  --tx:#e6edf3; --tx2:#9aa7b4; --tx3:#8b98a6;
  --up:#f0483e; --upbg:rgba(240,72,62,.12); --down:#22a06b; --downbg:rgba(34,160,107,.12);
  --acc:#63a888; --warn:#d9a13b; --info:#4f8cc9;
  /* 事件类型色（取自同一套色板，保证与看板观感一致） */
  --t0:#4f8cc9; --t1:#f0483e; --t2:#c586c0; --t3:#d9a13b; --t4:#63a888; --t5:#2f9e8f; --t6:#6fa8dc;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-track,::-webkit-scrollbar-corner{background:var(--bg)}
::-webkit-scrollbar-thumb{background:#39424f;border-radius:6px;border:2px solid var(--bg)}
::-webkit-scrollbar-thumb:hover{background:#4c5764}
body{background:var(--bg);color:var(--tx);font:13px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;padding:22px 20px 60px}
.wrap{max-width:1320px;margin:0 auto}
a{color:var(--info)}
.skip{position:absolute;left:-9999px;top:0;background:var(--panel2);border:1px solid var(--ctl);color:var(--tx);padding:8px 14px;border-radius:0 0 8px 0;z-index:99}
.skip:focus{left:0}

/* ---------- 布局：左侧竖排页卡 + 右侧内容 -------------------------------
   2026-10-06 用户要求「把投资日历 / 指数看盘 / 利润断层这三个页卡换到左边竖着排列」。
   桌面：196px 侧栏 + 右侧内容，侧栏 position:sticky 常驻。
   窄屏（≤900px）：侧栏折叠成**顶部固定横条**，三个等宽按钮常驻可见。
   为什么手机上不保持左竖排：375px 下若留一条左栏，正文只剩 ~280px，日历网格和
   选股表都会被挤爆；而用户报的原始问题是「没有找到这 3 个页卡的按钮」——
   原来那排标签在页头最下方、要滚过一屏元信息才看得到。横条常驻顶部才是对症的修法。 */
.shell{display:grid;grid-template-columns:196px minmax(0,1fr);column-gap:22px;
  grid-template-areas:"nav hdr" "nav main" "nav foot";align-items:start}
.sidenav{grid-area:nav;position:sticky;top:22px;display:flex;flex-direction:column;gap:10px}
header{grid-area:hdr;display:flex;flex-wrap:wrap;align-items:flex-end;gap:14px;padding-bottom:14px;border-bottom:1px solid var(--line)}
main{grid-area:main;min-width:0}
footer{grid-area:foot}
h1{font-size:20px;font-weight:600;letter-spacing:.5px}
h1 span{color:var(--up)}
.sub{color:var(--tx2);font-size:13px;line-height:1.9}
.hdr-nav{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.tabs{display:flex;flex-direction:column;gap:4px;background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:5px}
.tab{appearance:none;-webkit-appearance:none;border:0;background:transparent;color:var(--tx2);
  font:600 13px/1.6 inherit;padding:9px 12px;border-radius:7px;cursor:pointer;white-space:nowrap;
  text-align:left;transition:background-color .2s,color .2s}
.tab:hover{color:var(--tx);background:var(--panel2)}
.tab[aria-selected="true"]{background:var(--upbg);color:var(--up);box-shadow:inset 0 0 0 1px rgba(240,72,62,.45)}
.tab:focus-visible{outline:2px solid var(--info);outline-offset:2px}
.tab .dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--line2);margin-right:7px;vertical-align:1px}
.tab[aria-selected="true"] .dot{background:var(--up)}

/* 外部模块（指数看盘）：iframe 必须有确定高度，否则全屏应用会塌陷成 0 */
.ext{background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden;position:relative}
.ext>iframe{display:block;width:100%;height:min(78vh,880px);border:0;background:var(--bg)}
.ext .extload{position:absolute;inset:0;display:none;align-items:center;justify-content:center;
  color:var(--tx2);font-size:13px;gap:10px}
.ext .extload.on{display:flex}
.extops{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 10px}
.extops .hint{color:var(--tx2);font-size:12px;flex:1;min-width:180px}
/* 视图切换：完整应用 / 工作台内建视图。用现成的 .btn + .btn.on（红底=当前视图），
   不再引一套新配色，保证与工作台其余按钮同源。 */
.viewsw{display:inline-flex;gap:4px;flex:0 0 auto}

@media(max-width:900px){
  .shell{grid-template-columns:minmax(0,1fr);column-gap:0;
    grid-template-areas:"hdr" "nav" "main" "foot"}
  /* margin 负值把横条拉满整宽（抵消 body 的 20px 左右内边距），否则两侧会露白 */
  .sidenav{position:sticky;top:0;z-index:30;flex-direction:row;align-items:center;gap:8px;
    background:var(--bg);margin:0 -20px;padding:8px 20px;border-bottom:1px solid var(--line);
    box-shadow:0 6px 14px -10px rgba(0,0,0,.95)}
  .tabs{flex-direction:row;flex:1;padding:3px}
  .tab{flex:1;justify-content:center;text-align:center;padding:8px 6px}
  .ext>iframe{height:min(70vh,680px)}
  /* 工具栏窄屏改成「按钮各占一行、说明独占整行」：
     说明里那句「含『笔记』与『艾丽的总结』」挤在两颗按钮右边只剩 ~120px，
     会变成一根三行窄柱，读起来很费劲。order:9 让说明永远排在按钮后面。 */
  .extops{gap:8px}
  .extops .hint{order:9;flex:1 1 100%;min-width:0}
}

/* ---------- 通用控件 ---------- */
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px}
input,select,button{font-family:inherit}
input[type=search],input[type=date],select{background:var(--panel2);border:1px solid var(--ctl);color:var(--tx);
  border-radius:7px;padding:6px 10px;font-size:13px;outline:none;transition:border-color .2s}
input[type=search]:focus,input[type=date]:focus,select:focus{border-color:var(--acc)}
input[type=search]{min-width:170px}
.btn{background:var(--panel2);border:1px solid var(--ctl);color:var(--tx);border-radius:7px;
  padding:6px 11px;font-size:13px;cursor:pointer;transition:border-color .2s,transform .2s,background-color .2s}
.btn:hover{border-color:var(--acc)}
.btn:active{transform:scale(.96)}
.btn.on{background:var(--upbg);border-color:rgba(240,72,62,.5);color:var(--up)}
:focus-visible{outline:2px solid var(--info);outline-offset:2px}
.tools{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:12px 0}
.tools label{color:var(--tx2);font-size:13px}
.chip{background:var(--panel2);border:1px solid var(--line2);color:var(--tx2);border-radius:20px;
  padding:3px 11px;font-size:12px;cursor:pointer;display:inline-flex;align-items:center;gap:6px;
  transition:border-color .2s,color .2s}
.chip:hover{color:var(--tx);border-color:var(--ctl)}
.chip.on{color:var(--tx);border-color:var(--ctl);background:var(--panel)}
.chip i{width:8px;height:8px;border-radius:50%;display:inline-block}

/* ---------- 投资日历 ---------- */
.calbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:14px 0 10px}
.calbar .m{font-size:17px;font-weight:600;min-width:132px}
.calbar .nav{display:flex;gap:6px}
.grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:1px;background:var(--line);
  border:1px solid var(--line);border-radius:10px;overflow:hidden}
/* minmax(0,1fr) 而非 1fr：后者的隐含最小宽度是 min-content，格子里的「日号 + 事件数」
   撑不住 320px 屏时会把整个网格顶宽 → 页面横向溢出。实测 360px 无事、320px 溢出 36 个节点。 */
.grid .hd{background:var(--panel);color:var(--tx2);font-size:12px;text-align:center;padding:8px 2px}
.cell{background:var(--bg);min-height:78px;padding:6px 7px;cursor:pointer;position:relative;
  display:flex;flex-direction:column;gap:5px;transition:background-color .15s;border:0;text-align:left;
  font:inherit;color:inherit;width:100%;overflow:hidden}
.cell:hover{background:var(--panel)}
.cell.out{background:#0a0e13;color:var(--tx3);cursor:default}
.cell.today{box-shadow:inset 0 0 0 1px rgba(240,72,62,.55)}
.cell.sel{background:var(--panel2);box-shadow:inset 0 0 0 2px var(--acc)}
.cell .d{font-size:13px;font-weight:600;display:flex;align-items:center;justify-content:space-between;gap:4px}
.cell .n{font-size:11px;color:var(--tx2);font-weight:400;font-variant-numeric:tabular-nums}
.cell .dots{display:flex;flex-wrap:wrap;gap:3px}
.cell .dots i{width:7px;height:7px;border-radius:50%;display:inline-block}
.cell .lbl{font-size:11px;color:var(--tx2);line-height:1.35;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cell.out .n,.cell.out .lbl{opacity:.5}
.dayhead{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin:18px 0 8px}
.dayhead h2{font-size:15px;font-weight:600;display:flex;align-items:center;gap:8px}
.dayhead h2:before{content:"";width:3px;height:14px;background:var(--up);border-radius:2px}
.dayhead em{font-style:normal;color:var(--tx2);font-size:12px}
.evlist{max-height:440px;overflow:auto;border:1px solid var(--line);border-radius:10px;background:var(--panel)}
.ev{display:grid;grid-template-columns:88px 1fr;gap:10px;padding:9px 12px;border-bottom:1px solid var(--line)}
.ev:last-child{border-bottom:0}
.ev .tag{font-size:11px;font-weight:600;border-radius:5px;padding:1px 7px;border:1px solid;justify-self:start;white-space:nowrap}
.ev .bd{min-width:0}
.ev .nm{font-size:13px;display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.ev .nm b{font-weight:600}
.ev .nm code{color:var(--tx3);font-size:12px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.ev .ds{color:var(--tx2);font-size:12px;margin-top:1px}
.ev .bdgrp{padding:7px 12px 2px;color:var(--tx3);font-size:12px;background:var(--panel2);
  border-bottom:1px solid var(--line);position:sticky;top:0}
.empty{color:var(--tx2);text-align:center;padding:34px 16px;font-size:13px}

/* ---------- 选股平台 ---------- */
.tblwrap{overflow:auto;border:1px solid var(--line);border-radius:10px;background:var(--panel)}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--tx2);font-weight:500;font-size:12px;cursor:pointer;user-select:none;position:sticky;top:0;
  background:var(--panel);z-index:1;text-align:right}
th:hover{color:var(--tx);background:var(--panel2)}
th.on{color:var(--tx)}
th.l,td.l{text-align:left}
th:not(.ns):after{content:" ⇅";color:var(--tx3);font-size:12px}
th.on:after{content:" ▼";color:var(--acc)}
th.on.asc:after{content:" ▲";color:var(--acc)}
th.ns{cursor:default}
tbody tr:hover{background:var(--panel2)}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.up{color:var(--up)} .down{color:var(--down)} .mut{color:var(--tx3)}
.stk{display:flex;align-items:baseline;gap:8px}
.stk b{font-weight:600}
.stk code{color:var(--tx3);font-size:12px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.stk .tier{font-size:11px;color:var(--tx2);border:1px solid var(--line2);border-radius:5px;padding:0 5px}
.sum{display:flex;gap:18px;flex-wrap:wrap;color:var(--tx2);font-size:13px;margin:10px 0 0}
.sum b{color:var(--tx);font-weight:600;font-variant-numeric:tabular-nums}

footer{margin-top:26px;padding-top:14px;border-top:1px solid var(--line);color:var(--tx3);font-size:12px;line-height:1.9}
footer a{color:var(--tx2);text-decoration:none;border-bottom:1px solid var(--line2)}
footer a:hover{color:var(--tx)}
.warnbox{border:1px solid rgba(217,161,59,.45);background:rgba(217,161,59,.1);color:var(--warn);
  border-radius:9px;padding:9px 12px;font-size:12px;line-height:1.7;margin-top:12px}

/* ---------- 响应式 ---------- */
@media(max-width:820px){
  .cell{min-height:64px;padding:5px}
  .cell .lbl{display:none}
  .cell .dots i{width:6px;height:6px}
}
@media(max-width:560px){
  body{padding:16px 12px 48px}
  h1{font-size:18px}
  .cell{min-height:52px}
  .cell .n{font-size:10px}
  .grid .hd{font-size:11px;padding:6px 0}
  .ev{grid-template-columns:1fr;gap:5px}
  .ev .tag{justify-self:start}
  .btn,.chip{padding:6px 9px}
  .tools{gap:6px}
  /* 选股表：窄屏【不再】转成「标签 : 值」竖排卡片 ——
     那样一只股票要占 6 行、一屏只能看两三只（2026-10-06 用户实测反馈「一格格太大」）。
     改为与电脑端**同一张真表格**：一行一只、字号收紧，横向滑动看
     「断层日期 / 断层幅度 / 当日涨跌幅 / 成交量 / 所属行业」；
     「名称 / 代码」吸附在左侧，滑到右边看行业时也不会忘了在看哪只。 */
  #pTbl{font-size:12px}
  #pTbl th,#pTbl td{padding:7px 9px}
  #pTbl thead th:first-child{position:sticky;left:0;background:var(--panel);z-index:3;
    width:132px;min-width:132px}
  #pTbl td:first-child{position:sticky;left:0;background:var(--bg);z-index:2;
    width:132px;min-width:132px;white-space:normal;
    box-shadow:7px 0 7px -7px rgba(0,0,0,.85)}
  /* .stk 是 flex，默认 nowrap：窄屏不换行的话「核心池·双断层」标签会横向顶出去 */
  #pTbl td:first-child .stk{flex-wrap:wrap;row-gap:2px}
  #pTbl tbody tr:hover td:first-child{background:var(--panel2)}
}
@media(prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}html{scroll-behavior:auto}}
/* 极窄屏（≤380px，如 iPhone SE 一代）：格子里放不下「日号 + 事件数」两段，
   去掉数字角标只留类型色点（信息仍有，且不再撑破网格）。 */
@media(max-width:380px){
  .cell{padding:4px 2px;min-height:46px;gap:3px}
  .cell .d{gap:2px}
  .cell .n{display:none}
  .cell .dots{gap:2px}
  .cell .dots i{width:5px;height:5px}
}
</style>
</head>
<body>
<a class="skip" href="#picks">跳到利润断层选股平台</a>
<div class="wrap">
<div class="shell">
  <header>
    <div style="flex:1;min-width:260px">
      <h1>个人投资<span>工作台</span></h1>
      <div class="sub" id="meta"></div>
    </div>
    <!-- 2026-10-06 用户要求「评估『查看完整 K 线图』这一入口的必要性，并调整为点击页卡后
         直接展示完整页面，无需多余的中间跳转」。
         评估结论：三个页卡现在都直接内嵌完整应用（完整日历 / 指数看盘 / 完整看板），
         那个「完整看板（含 K 线）」就是个多余的中间跳转 —— 已删除。
         每个页卡自己的工具栏里都留了「新窗口打开」，需要独立大屏时仍可一键直达。 -->
  </header>

  <!-- 三个页卡：投资日历（主页）/ 指数看盘 / 利润断层。
       桌面靠左竖排；≤900px 由 CSS 折叠成顶部固定横条（三个等宽按钮常驻可见）。 -->
  <nav class="sidenav" aria-label="分页切换">
    <div class="tabs" role="tablist" aria-orientation="vertical">
      <button type="button" class="tab" id="tabCal" role="tab" aria-selected="true" aria-controls="pgCal"><span class="dot"></span>投资日历</button>
      <button type="button" class="tab" id="tabIdx" role="tab" aria-selected="false" aria-controls="pgIdx"><span class="dot"></span>指数看盘</button>
      <button type="button" class="tab" id="tabPk" role="tab" aria-selected="false" aria-controls="pgPicks"><span class="dot"></span>利润断层</button>
    </div>
  </nav>

  <main>
    <!-- ============ 分页 1：投资日历 ============
         默认直接内嵌**完整的市场日历应用**（它自带「笔记」与「艾丽的总结」——
         2026-10-06 用户明确要求这两项功能「不得删改」，所以这里只是把它嵌进来，
         一行都不去改那个应用；它的云笔记登录在自己那个源上跑，不受父页面影响）。
         「工作台月历」= 本页原有的自建月历（A 股事件 7 类），保留不删，一键可切。 -->
    <section id="pgCal" role="tabpanel" aria-labelledby="tabCal">
      <div class="extops">
        <div class="viewsw" role="group" aria-label="日历视图切换">
          <button type="button" class="btn on" id="calVFull" aria-pressed="true">完整日历</button>
          <button type="button" class="btn" id="calVIn" aria-pressed="false">工作台月历</button>
        </div>
        <span class="hint">完整日历为独立部署应用，含「笔记」与「艾丽的总结」；数据由它自行更新，读数不新时点「重新加载」。</span>
        <a class="btn" id="calNew" href="https://market-calendar-71280.app.workbuddy.host/" target="_blank" rel="noopener noreferrer">新窗口打开</a>
        <button type="button" class="btn" id="calReload">重新加载</button>
      </div>
      <div class="ext" id="calExt">
        <iframe id="calFrame" title="市场日历（含笔记与艾丽的总结）" referrerpolicy="no-referrer-when-downgrade"
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox allow-downloads allow-modals"></iframe>
        <div class="extload" id="calLoad"><span>正在加载完整日历…</span></div>
      </div>

      <div id="calIn" hidden>
      <div class="calbar">
        <div class="nav">
          <button type="button" class="btn" id="mPrev" aria-label="上一月">‹</button>
          <button type="button" class="btn" id="mToday">今天</button>
          <button type="button" class="btn" id="mNext" aria-label="下一月">›</button>
        </div>
        <div class="m" id="mLabel"></div>
        <div id="mTypes" style="display:flex;gap:6px;flex-wrap:wrap"></div>
      </div>
      <div id="cNote" class="warnbox" hidden></div>
      <div class="grid" id="mGrid" role="grid" aria-label="投资日历月视图"></div>
      <div class="dayhead">
        <h2 id="dTitle">当天事件</h2>
        <em id="dCount"></em>
      </div>
      <div id="dFilter" class="tools" style="margin:0 0 8px"></div>
      <div class="evlist" id="dList"></div>
      </div>
    </section>

    <!-- ============ 分页 2：指数看盘（外部模块 · 独立部署） ============
         与看板里的「指数看盘」模块指向同一个已部署应用。
         iframe 走懒加载：src 在首次切到本页时才写入（见 showPage），
         否则首屏要多等一个 117 KB 的外部应用才能看到日历。 -->
    <section id="pgIdx" role="tabpanel" aria-labelledby="tabIdx" hidden>
      <div class="extops">
        <span class="hint">外部模块 · 数据由该应用自行更新；读数不新时点「重新加载」。</span>
        <a class="btn" id="idxNew" href="https://global-market-dashboard-68975.app.workbuddy.host/" target="_blank" rel="noopener noreferrer">新窗口打开</a>
        <button type="button" class="btn" id="idxReload">重新加载</button>
      </div>
      <div class="ext">
        <iframe id="idxFrame" title="指数看盘" referrerpolicy="no-referrer-when-downgrade"
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox allow-downloads"></iframe>
        <div class="extload" id="idxLoad"><span>正在加载指数看盘…</span></div>
      </div>
    </section>

    <!-- ============ 分页 3：利润断层 ============
         默认直接内嵌**完整看板**（K 线弹窗 / 散点图 / 板块全景 / 核心断层区 全在里面），
         所以页头那个「完整看板（含 K 线）」入口已无必要，已删除（见 header 注释）。
         「工作台清单」= 本页原有的选股表（区间筛选 / 搜索 / 排序），保留不删，一键可切。 -->
    <section id="pgPicks" role="tabpanel" aria-labelledby="tabPk" hidden>
      <div class="extops">
        <div class="viewsw" role="group" aria-label="利润断层视图切换">
          <button type="button" class="btn on" id="pkVFull" aria-pressed="true">完整看板</button>
          <button type="button" class="btn" id="pkVIn" aria-pressed="false">工作台清单</button>
        </div>
        <span class="hint">完整看板含 K 线图、散点图、板块全景与核心断层区；点任意个股即可看 K 线。</span>
        <a class="btn" id="pkNew" href="利润断层工作台.html" target="_blank" rel="noopener noreferrer">新窗口打开</a>
        <button type="button" class="btn" id="pkReload">重新加载</button>
      </div>
      <div class="ext" id="pkExt">
        <iframe id="pkFrame" title="利润断层工作台（含 K 线）" referrerpolicy="no-referrer-when-downgrade"></iframe>
        <div class="extload" id="pkLoad"><span>正在加载完整看板…</span></div>
      </div>

      <div id="pkIn" hidden>
      <div class="tools">
        <label for="pFrom">断层日期</label>
        <input type="date" id="pFrom" aria-label="起始日期">
        <span class="mut">~</span>
        <input type="date" id="pTo" aria-label="结束日期">
        <button type="button" class="btn" data-range="7">近 7 天</button>
        <button type="button" class="btn" data-range="30">近 30 天</button>
        <button type="button" class="btn" data-range="0">全部</button>
        <input type="search" id="pQ" placeholder="搜索代码 / 名称 / 行业" aria-label="搜索个股">
        <button type="button" class="btn" id="pReset">重置</button>
      </div>
      <div class="sum" id="pSum"></div>
      <div class="tblwrap">
        <table id="pTbl">
          <caption class="skip">利润断层选股清单</caption>
          <thead>
            <tr>
              <th class="l" id="thName" data-k="n">股票名称 / 代码</th>
              <th data-k="d" id="thDate">断层日期</th>
              <th data-k="g" class="on" id="thGap" aria-sort="descending">断层幅度</th>
              <th data-k="s" id="thStreak">连续断层</th>
              <th data-k="dc" id="thDc">当日涨跌幅</th>
              <th data-k="v" id="thVol">成交量</th>
              <th class="l" id="thInd" data-k="i" style="text-align:left">所属行业</th>
            </tr>
          </thead>
          <tbody id="pBody"></tbody>
        </table>
      </div>
      <div id="pNote" class="warnbox" hidden></div>
      </div>
    </section>
  </main>

  <footer>
    <div id="foot">本页为个人研究工具，数据来自公开接口（东方财富 / 新浪 / 百度财经日历），可能存在延迟或错漏。</div>
    <div>
      <a href="利润断层工作台.html">利润断层工作台（含 K 线图）</a> ·
      <a href="https://market-calendar-71280.app.workbuddy.host/" target="_blank" rel="noopener noreferrer">市场日历</a>
    </div>
    <div>本报告仅供研究参考，不构成个人投资建议。</div>
  </footer>
</div>
</div>

<script type="application/json" id="cal-payload">__CAL__</script>
<script type="application/json" id="pk-payload">__PK__</script>
<script>
const CAL = JSON.parse(document.getElementById("cal-payload").textContent);
const PK  = JSON.parse(document.getElementById("pk-payload").textContent);

const TYPES = (CAL.meta && CAL.meta.types) || [];
const TCOLOR = ["var(--t0)","var(--t1)","var(--t2)","var(--t3)","var(--t4)","var(--t5)","var(--t6)"];
const EV = (CAL.events || []).slice().sort((a,b)=> a.d<b.d?-1:a.d>b.d?1:0);
const BYDAY = {};
EV.forEach(e => { (BYDAY[e.d] || (BYDAY[e.d] = [])).push(e); });

const $ = id => document.getElementById(id);
const esc = s => String(s==null?"":s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const pad = n => (n<10?"0":"")+n;
const ymd = d => d.getFullYear()+"-"+pad(d.getMonth()+1)+"-"+pad(d.getDate());
const today = (CAL.meta && CAL.meta.today) || ymd(new Date());

/* ===================== 分页切换 =====================
   三个页卡：投资日历（主页）/ 指数看盘 / 利润断层。
   首屏固定落在「投资日历」——2026-10-06 用户明确要求「主页设置为投资日历」，
   所以兜底是硬编码的 HOME，不再读 localStorage 的「上次看到哪一页」：
   手机上若带着上次的 picks 记忆值打开，第一眼看到的就不是主页，
   用户会以为页卡又不见了（这正是本次报障的现象）。直达/分享仍走 URL hash。 */
const PAGES = {calendar:{tab:"tabCal", pg:"pgCal", hash:"#calendar", ext:"cal"},
               indices:{tab:"tabIdx", pg:"pgIdx", hash:"#indices", ext:"idx"},
               picks:{tab:"tabPk",  pg:"pgPicks", hash:"#picks", ext:"pk"}};
const HOME = "calendar";
const on = (id, fn) => { const el = $(id); if(el) el.addEventListener("click", fn); };

/* 三个页卡默认都直接内嵌**完整应用**（2026-10-06 用户要求「点击页卡后直接展示完整页面，
   无需多余的中间跳转」）。每个页卡各带一个 iframe + 视图切换：
   - 投资日历：完整日历（市场日历应用，自带笔记 + 艾丽的总结）/ 工作台月历（自建）
   - 利润断层：完整看板（含 K 线）/ 工作台清单（自建）
   自建视图一行没删，只是默认不显示 —— 用户明确说过「不得删改」。
   src 在「首次真正显示该 iframe」时才写入；利润断层的 src 依赖本页所在目录，
   所以用相对路径（在 Pages 与 file:// 下都对）。 */
const EXTS = {
  cal: { frame:"calFrame", load:"calLoad", url:"https://market-calendar-71280.app.workbuddy.host/",
         label:"完整日历", timeout:20000, inBox:"calIn", vFull:"calVFull", vIn:"calVIn",
         inName:"工作台月历" },
  idx: { frame:"idxFrame", load:"idxLoad", url:"https://global-market-dashboard-68975.app.workbuddy.host/",
         label:"指数看盘", timeout:20000 },
  pk:  { frame:"pkFrame",  load:"pkLoad",  url:"利润断层工作台.html",
         label:"完整看板", timeout:20000, inBox:"pkIn",  vFull:"pkVFull",  vIn:"pkVIn",
         inName:"工作台清单" }
};
const EXT_TIMERS = {};

function showPage(name, push){
  if(!PAGES[name]) name = HOME;
  Object.keys(PAGES).forEach(k=>{
    const p = PAGES[k], t = $(p.tab), g = $(p.pg);
    // null 守卫：负向测试会把整个页卡摘掉，直接 .setAttribute 抛 TypeError 会让脚本
    // 崩在中间，后面的断言等于没跑（check_calendar.js 实测吃过这个亏）。
    if(t) t.setAttribute("aria-selected", k===name ? "true":"false");
    if(g) g.hidden = (k!==name);
  });
  if(push !== false){
    try{ history.replaceState(null, "", PAGES[name].hash); }catch(e){}
  }
  if(name==="picks") renderPicks();
  // 懒加载当前页卡自己的完整应用（其他两个的 iframe 保持无 src，首屏只拉一个）
  if(PAGES[name].ext) loadExt(PAGES[name].ext);
}

/* 外部应用 iframe 懒加载：首屏不去拉几 MB 的外部页面，只有真正切到该页卡才写 src。
   已加载过就不再重写 src（重写会把应用里的月份选择、滚动位置一并重置），
   只有点「重新加载」才带 _r= 时间戳强刷。 */
function loadExt(key, bust){
  const m = EXTS[key];
  if(!m) return null;
  const f = $(m.frame);
  if(!f) return null;
  if(f.getAttribute("src") && !bust) return f;
  const box = $(m.load);
  if(box){
    box.classList.add("on");
    const txt = box.querySelector("span");
    if(txt) txt.textContent = (bust ? "正在重新加载" : "正在加载") + m.label + "…";
    if(EXT_TIMERS[key]) clearTimeout(EXT_TIMERS[key]);
    // load 有可能因为对端拒绝嵌入 / 网络慢而永远不来，用 once 监听 + 超时兜底，
    // 别让首屏（默认就是日历页）留一个空洞 —— 至少告诉用户还能走内建视图。
    f.addEventListener("load", ()=>{
      if(EXT_TIMERS[key]) clearTimeout(EXT_TIMERS[key]);
      box.classList.remove("on");
    }, { once:true });
    EXT_TIMERS[key] = setTimeout(()=>{
      box.classList.add("on");
      if(txt) txt.textContent = m.label + "加载较慢或失败 —— 可点「重新加载」重试"
        + (m.inName ? "，或切到「" + m.inName + "」看工作台内建视图。" : "。");
    }, m.timeout);
  }
  // 相对 URL（利润断层看板与被嵌页面同目录）原样使用，只有强刷才加时间戳
  f.setAttribute("src", bust
    ? m.url + (m.url.indexOf("?")>=0 ? "&" : "?") + "_r=" + Date.now()
    : m.url);
  return f;
}

/* 视图切换：完整应用 <-> 工作台内建视图。切到内建视图时把 iframe 的 src 摘掉，
   免得后台那个应用还在跑（和看板模块层的做法一致）。 */
function setView(key, full){
  const m = EXTS[key];
  if(!m || !m.inBox) return;
  const box = $(m.inBox), fb = $(m.vFull), ib = $(m.vIn);
  if(box) box.hidden = full;
  if(fb) { fb.classList.toggle("on", full);  fb.setAttribute("aria-pressed", full ? "true":"false"); }
  if(ib) { ib.classList.toggle("on", !full); ib.setAttribute("aria-pressed", full ? "false":"true"); }
  const wrap = $({cal:"calExt", pk:"pkExt"}[key]);
  if(wrap) wrap.hidden = !full;
  if(full) loadExt(key);
  else { const f = $(m.frame); if(f) f.removeAttribute("src"); }
}
on("tabCal", ()=>showPage("calendar"));
on("tabIdx", ()=>showPage("indices"));
on("tabPk",  ()=>showPage("picks"));
on("idxReload", ()=>loadExt("idx", true));
on("calReload", ()=>loadExt("cal", true));
on("pkReload",  ()=>loadExt("pk",  true));
on("calVFull", ()=>setView("cal", true));
on("calVIn",   ()=>setView("cal", false));
on("pkVFull",  ()=>setView("pk",  true));
on("pkVIn",    ()=>setView("pk",  false));
window.addEventListener("hashchange", ()=>{
  const h = location.hash;
  if(h==="#picks") showPage("picks", false);
  else if(h==="#indices") showPage("indices", false);
  else if(h==="#calendar") showPage("calendar", false);
});

/* ===================== 分页 1：投资日历 ===================== */
let calMonth = today.slice(0,7);
let calSel = today;
let typeOff = new Set();          // 被「关掉」的类型下标（默认全开）

function shiftMonth(n){
  const [y,m] = calMonth.split("-").map(Number);
  const d = new Date(y, m-1+n, 1);
  calMonth = d.getFullYear()+"-"+pad(d.getMonth()+1);
  // 选中日若不在新月份里，落到「今天（若在本月）或本月 1 号」，否则详情面板讲的
  // 是另一天的事件、而网格里没有任何格子处于选中态，很迷惑。
  if(calSel.slice(0,7) !== calMonth){
    dayOff = new Set();
    calSel = (today.slice(0,7)===calMonth) ? today : calMonth+"-01";
    renderCal(); renderDay(); return;
  }
  renderCal();
}
function renderTypes(){
  $("mTypes").innerHTML = TYPES.map((t,i)=>
    '<button type="button" class="chip '+(typeOff.has(i)?"":"on")+'" data-t="'+i+'" aria-pressed="'+(typeOff.has(i)?"false":"true")+'">'+
    '<i style="background:'+TCOLOR[i%TCOLOR.length]+'"></i>'+esc(t)+
    '<span class="mut">'+EV.filter(e=>e.t===i).length+'</span></button>').join("");
  $("mTypes").querySelectorAll(".chip").forEach(b=>{
    b.addEventListener("click", ()=>{
      const i = +b.dataset.t;
      if(typeOff.has(i)) typeOff.delete(i); else typeOff.add(i);
      renderTypes(); renderCal(); renderDay();
    });
  });
}
function evVisible(e){ return !typeOff.has(e.t); }

function renderCal(){
  const [y,m] = calMonth.split("-").map(Number);
  $("mLabel").textContent = y+"年"+m+"月";
  const first = new Date(y, m-1, 1);
  const startWd = (first.getDay()+6)%7;                 // 周一为一周之首
  const days = new Date(y, m, 0).getDate();
  const prevDays = new Date(y, m-1, 0).getDate();
  const weeks = Math.ceil((startWd+days)/7);
  let html = ["一","二","三","四","五","六","日"].map(w=>'<div class="hd">'+w+'</div>').join("");
  const cells = weeks*7;
  for(let i=0;i<cells;i++){
    const dayNo = i-startWd+1;
    if(dayNo<1 || dayNo>days){
      const pd = dayNo<1 ? prevDays+dayNo : dayNo-days;
      html += '<div class="cell out"><span class="d">'+pd+'</span></div>';
      continue;
    }
    const ds = calMonth+"-"+pad(dayNo);
    const list = (BYDAY[ds]||[]).filter(evVisible);
    const cnt = {};
    list.forEach(e=>{ cnt[e.t]=(cnt[e.t]||0)+1; });
    const idx = Object.keys(cnt).map(Number).sort((a,b)=>cnt[b]-cnt[a]);
    const dots = idx.slice(0,4).map(t=>'<i style="background:'+TCOLOR[t%TCOLOR.length]+'"></i>').join("");
    const top = idx.length ? TYPES[idx[0]]+" "+(cnt[idx[0]]>1?cnt[idx[0]]+" 条":"") : "";
    const cls = "cell"+(ds===today?" today":"")+(ds===calSel?" sel":"");
    html += '<button type="button" class="'+cls+'" data-d="'+ds+'" aria-label="'+ds+' 事件 '+list.length+' 条">'
          +   '<span class="d">'+dayNo+(list.length?'<span class="n">'+list.length+'</span>':'')+'</span>'
          +   '<span class="dots">'+dots+'</span>'
          +   (top?'<span class="lbl">'+esc(top)+'</span>':'')
          + '</button>';
  }
  $("mGrid").innerHTML = html;
  $("mGrid").querySelectorAll(".cell[data-d]").forEach(c=>{
    c.addEventListener("click", ()=>selectDay(c.dataset.d));
  });
}

let dayOff = new Set();
// 换一天时清空「当日类型开关」：否则在某天关掉某类型后，走到「只有该类型」的另一天，
// 筛选条不显示，用户就再也点不回来了（列表空着且无从恢复）。
function selectDay(ds){ dayOff = new Set(); calSel = ds; renderCal(); renderDay(); }
function renderDay(){
  const list = (BYDAY[calSel]||[]).filter(e=>!dayOff.has(e.t));
  const [y,m,dd] = calSel.split("-");
  $("dTitle").textContent = y+"年"+Number(m)+"月"+Number(dd)+"日";
  $("dCount").textContent = list.length+" 个事件";
  const all = BYDAY[calSel]||[];
  const kinds = Object.keys(all.reduce((a,e)=>{a[e.t]=1;return a;},{})).map(Number).sort((a,b)=>a-b);
  if(kinds.length>1){
    $("dFilter").innerHTML = kinds.map(t=>
      '<button type="button" class="chip '+(dayOff.has(t)?"":"on")+'" data-dt="'+t+'" aria-pressed="'+(dayOff.has(t)?"false":"true")+'">'
      +'<i style="background:'+TCOLOR[t%TCOLOR.length]+'"></i>'+esc(TYPES[t])
      +'<span class="mut">'+all.filter(e=>e.t===t).length+'</span></button>').join("");
    $("dFilter").querySelectorAll(".chip").forEach(b=>{
      b.addEventListener("click", ()=>{
        const t=+b.dataset.dt;
        if(dayOff.has(t)) dayOff.delete(t); else dayOff.add(t);
        renderDay();
      });
    });
    $("dFilter").style.display="";
  } else {
    // 只有 0 或 1 种类型时不给筛选条（筛了也没得筛），但**必须照常渲染事件列表**。
    // ⚠️ 这里曾经写成 `return`，于是「当天只有一种事件」或「当天无事件」时，
    //    #dList 既不清空也不重绘 → 页面静止显示上一天的内容（或一直空白），
    //    且没有任何提示。属「静默消失」类缺陷，不可改回。
    $("dFilter").innerHTML=""; $("dFilter").style.display="none";
  }
  renderEvList(list, all);
}
function renderEvList(list, all){
  if(all===undefined) all = list;
  if(!list.length){
    // 「本来就没有」和「被筛选关掉了」是两件事，提示要分开，否则用户会以为数据丢了
    $("dList").innerHTML = '<div class="empty">'+(all.length
      ? "这一天的事件都被上方类型筛选关掉了"
      : "这一天没有事件")+'</div>';
    return;
  }
  const groups = {};
  list.forEach(e => (groups[e.t] || (groups[e.t]=[])).push(e));
  let html = "";
  Object.keys(groups).map(Number).sort((a,b)=>groups[b].length-groups[a].length).forEach(t=>{
    html += '<div class="bdgrp">'+esc(TYPES[t])+' · '+groups[t].length+' 条</div>';
    const rows = groups[t].length>200 ? groups[t].slice(0,200) : groups[t];
    rows.forEach(e=>{
      const subj = e.c ? '<b>'+esc(e.n)+'</b><code>'+esc(e.c)+'</code>' : '<b>'+esc(e.n)+'</b>';
      html += '<div class="ev">'
            +   '<span class="tag" style="color:'+TCOLOR[t%TCOLOR.length]+';border-color:'+TCOLOR[t%TCOLOR.length]+'">'+esc(TYPES[t])+'</span>'
            +   '<span class="bd"><span class="nm">'+subj+(e.b?'<span class="mut">'+esc(e.b)+'</span>':'')+'</span>'
            +   (e.x?'<span class="ds">'+esc(e.x)+'</span>':'')+'</span>'
            + '</div>';
    });
    if(groups[t].length>200) html += '<div class="bdgrp">… 仅显示前 200 条，共 '+groups[t].length+' 条</div>';
  });
  $("dList").innerHTML = html;
}
$("mPrev").addEventListener("click", ()=>shiftMonth(-1));
$("mNext").addEventListener("click", ()=>shiftMonth(1));
$("mToday").addEventListener("click", ()=>{ calMonth=today.slice(0,7); selectDay(today); });

/* ===================== 分页 2：利润断层选股平台 ===================== */
const ROWS = (PK.rows||[]);
let sortK = "g", sortDir = -1, rFrom="", rTo="", rQ="";

const VOLFMT = v => {
  if(v==null || v==="") return "—";
  return v>=10000 ? (v/10000).toFixed(v>=100000?0:1)+" 万手" : v+" 手";
};
const pctf = v => (v==null||v==="") ? "—" : (v>0?"+":"")+Number(v).toFixed(2)+"%";

function defaultsForRange(){
  const ds = ROWS.map(r=>r.d).filter(Boolean).sort();
  if(!ds.length) return ["",""];
  return [ds[0], ds[ds.length-1]];
}
function renderPicks(){
  const all = ROWS;
  const filtered = all.filter(r=>{
    if(rFrom && (!r.d || r.d < rFrom)) return false;
    if(rTo   && (!r.d || r.d > rTo))   return false;
    if(rQ){
      const q = rQ.toLowerCase();
      if(!((r.c||"").includes(q) || (r.n||"").toLowerCase().includes(q) || (r.i||"").toLowerCase().includes(q))) return false;
    }
    return true;
  });
  filtered.sort((a,b)=>{
    const va = a[sortK], vb = b[sortK];
    if(va==null) return 1; if(vb==null) return -1;
    if(typeof va === "string") return sortDir*(va<vb?-1:va>vb?1:0);
    return sortDir*(va-vb);
  });
  $("pBody").innerHTML = filtered.map(r=>
      '<tr>'
    +   '<td class="l" data-label="名称"><span class="stk"><b>'+esc(r.n)+'</b><code>'+esc(r.c)+'</code>'
    +     (r.tier?'<span class="tier">'+esc(r.tier)+'</span>':'')+'</span></td>'
    +   '<td class="num" data-label="断层日期">'+esc(r.d||"—")+'</td>'
    +   '<td class="num" data-label="断层幅度"><span class="up">'+pctf(r.g)+'</span></td>'
    /* 连续断层期数：口径与主看板一致 —— n≥1 显示「N 期」（≥2 期标红），n=0 显示裸 0。
       「—」= 历史财报缺失（新股），与「0 期（有数据但本期不达标）」是两回事，不能合并。 */
    +   '<td class="num" data-label="连续断层">'
    +     (r.s == null ? '<span class="mut">—</span>'
         : (r.s >= 2 ? '<span class="up">'+r.s+' 期</span>'
           : (r.s >= 1 ? '<span class="mut">'+r.s+' 期</span>'
                       : '<span class="mut">0</span>')))+'</td>'
    +   '<td class="num" data-label="当日涨跌幅"><span class="'+(r.dc>0?"up":r.dc<0?"down":"mut")+'">'+pctf(r.dc)+'</span></td>'
    +   '<td class="num" data-label="成交量">'+VOLFMT(r.v)+'</td>'
    +   '<td class="l" data-label="所属行业">'+esc(r.i||"—")+'</td>'
    + '</tr>').join("")
    || '<tr><td colspan="6" class="empty">当前筛选条件下没有个股</td></tr>';
  const gaps = filtered.map(r=>r.g).filter(v=>typeof v==="number");
  $("pSum").innerHTML = '<span>清单 <b>'+filtered.length+'</b> 只</span>'
    + '<span>断层幅度中位 <b>'+(gaps.length?gaps.slice().sort((a,b)=>a-b)[Math.floor(gaps.length/2)].toFixed(2)+"%":"—")+'</b></span>'
    + '<span>最大 <b>'+(gaps.length?Math.max.apply(null,gaps).toFixed(2)+"%":"—")+'</b></span>'
    + '<span>连续断层 ≥2 期 <b>'+filtered.filter(r=>typeof r.s === "number" && r.s >= 2).length+'</b> 只</span>'
    + '<span class="mut">全量 '+all.length+' 只</span>';

  // 两个数据源各自的问题都要显示出来：日历的问题挂在日历页，清单的问题挂在选股页。
  // 否则某一路抓取失败时页面上毫无痕迹（「静默失败」）。
  const cprobs = CAL.problems || [];
  $("cNote").hidden = cprobs.length === 0;
  if(cprobs.length) $("cNote").textContent = "投资日历数据完整性提示：" + cprobs.join("；");

  const probs = (PK.problems && PK.problems.length) ? PK.problems : [];
  if(probs.length){ $("pNote").hidden=false; $("pNote").textContent = "数据完整性提示：" + probs.join("；"); }
  else $("pNote").hidden = true;

  document.querySelectorAll("#pTbl th[data-k]").forEach(th=>{
    const on = th.dataset.k===sortK;
    th.classList.toggle("on", on);
    th.classList.toggle("asc", on && sortDir===1);
    if(on) th.setAttribute("aria-sort", sortDir===1?"ascending":"descending");
    else th.removeAttribute("aria-sort");
  });
}
document.querySelectorAll("#pTbl th[data-k]").forEach(th=>{
  th.addEventListener("click", ()=>{
    const k = th.dataset.k;
    if(k===sortK) sortDir = -sortDir;
    else { sortK = k; sortDir = (k==="g"||k==="dc"||k==="v") ? -1 : 1; }
    renderPicks();
  });
});
document.querySelectorAll("[data-range]").forEach(b=>{
  b.addEventListener("click", ()=>{
    const n = +b.dataset.range;
    if(!n){ rFrom=""; rTo=""; }
    else{
      const t = new Date(today+"T00:00:00");
      const s = new Date(t.getTime()-(n-1)*86400000);
      rFrom = ymd(s); rTo = ymd(t);
    }
    $("pFrom").value = rFrom; $("pTo").value = rTo;
    document.querySelectorAll("[data-range]").forEach(x=>x.classList.toggle("on", x===b));
    renderPicks();
  });
});
["pFrom","pTo"].forEach(id=>$(id).addEventListener("change", ()=>{
  rFrom = $("pFrom").value; rTo = $("pTo").value;
  document.querySelectorAll("[data-range]").forEach(x=>x.classList.remove("on"));
  renderPicks();
}));
$("pQ").addEventListener("input", ()=>{ rQ = $("pQ").value.trim(); renderPicks(); });
$("pReset").addEventListener("click", ()=>{
  rQ=""; $("pQ").value="";
  document.querySelectorAll("[data-range]").forEach(x=>x.classList.remove("on"));
  const [a,b] = defaultsForRange(); rFrom=a; rTo=b;
  $("pFrom").value=a; $("pTo").value=b;
  sortK="g"; sortDir=-1;
  renderPicks();
});

/* ===================== 启动 ===================== */
(function boot(){
  const m = CAL.meta||{}, p = PK.meta||{};
  $("meta").innerHTML = "投资日历 "+esc(m.window_start||"")+" ~ "+esc(m.window_end||"")
    + " · 事件 <b>"+EV.length+"</b> 条"
    + " ｜　断层清单 <b>"+ROWS.length+"</b> 只"
    + (p.window_label ? "　·　"+esc(p.window_label) : "");
  $("foot").textContent = "生成于 "+(m.generated_at||p.generated_at||"—")+" · 数据来自公开接口（东方财富 / 新浪 / 百度财经日历），可能存在延迟或错漏。";

  const [ra, rb] = defaultsForRange();
  rFrom = ra; rTo = rb;
  $("pFrom").value = ra; $("pTo").value = rb;

  renderTypes();
  renderCal();
  renderDay();
  renderPicks();

  // 分页：URL hash 直达/分享优先；无 hash 一律落在主页「投资日历」
  let want = null;
  if(location.hash === "#picks") want = "picks";
  else if(location.hash === "#indices") want = "indices";
  else if(location.hash === "#calendar") want = "calendar";
  showPage(want || HOME);
})();
</script>
</body>
</html>
"""


def _vol_of(scan: dict, code: str, gap_date: str):
    """从 K 线里取「断层当日成交量（手）」。取不到返回 None（页面会显示 —）。"""
    k = scan.get("kline") or {}
    dates, data = k.get("dates") or [], k.get("data") or {}
    ent = data.get(code)
    if not ent or not gap_date or gap_date not in dates:
        return None
    i = dates.index(gap_date)
    d0 = ent.get("d0", 0)
    bars = ent.get("bars") or []
    if i < d0 or (i - d0) >= len(bars):
        return None
    try:
        return int(bars[i - d0][4])
    except Exception:
        return None


def build_picks(scan: dict) -> dict:
    rows = []
    for c in scan.get("candidates") or []:
        g = c.get("gap") or {}
        if not g.get("valid"):
            continue
        rows.append({
            "c": c.get("code", ""),
            "n": c.get("name", ""),
            "d": g.get("gap_date") or c.get("announce") or "",
            "g": g.get("gap_vs_close"),
            # 连续断层期数（连续几期单季同比达标）。口径与主看板同一字段，不另算。
            # 允许为 None：新股 / 历史财报缺失时主看板也是显示「—」，不能压成 0。
            "s": c.get("streak"),
            "dc": g.get("day_chg"),
            "v": _vol_of(scan, c.get("code", ""), g.get("gap_date") or ""),
            "a": g.get("amount"),
            "i": c.get("industry") or "",
            "b": c.get("board") or "",
            "tier": c.get("tier") or "",
        })
    return {
        "meta": {
            "generated_at": (scan.get("meta") or {}).get("generated_at", ""),
            "window_label": (scan.get("meta") or {}).get("window_label", ""),
        },
        "problems": (scan.get("audit") or {}).get("problems") or [],
        "rows": rows,
    }


def build(scan_path: str, cal_path: str, out_path: str, alias_path: str | None = None) -> str:
    with open(scan_path, "r", encoding="utf-8") as f:
        scan = json.load(f)
    if os.path.exists(cal_path):
        with open(cal_path, "r", encoding="utf-8") as f:
            cal = json.load(f)
    else:
        cal = {"meta": {"types": [], "generated_at": "", "today": dt.date.today().isoformat(),
                        "window_start": "", "window_end": ""},
               "sources": [], "problems": ["未找到 calendar_events.json，投资日历为空"], "events": []}

    pk = build_picks(scan)

    def dump(o):
        return json.dumps(o, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")

    html = TPL.replace("__CAL__", dump(cal)).replace("__PK__", dump(pk))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    if alias_path:
        with open(alias_path, "w", encoding="utf-8") as f:
            f.write(html)
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", default=os.path.join(ROOT, "data", "scan_latest.json"))
    ap.add_argument("--cal", default=os.path.join(ROOT, "data", "calendar_events.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "个人投资工作台.html"))
    ap.add_argument("--alias", default=os.path.join(ROOT, "home.html"),
                    help="ASCII 文件名别名（GitHub Pages 用；传空字符串可禁用）")
    args = ap.parse_args()
    p = build(args.scan, args.cal, args.out, args.alias or None)
    print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
