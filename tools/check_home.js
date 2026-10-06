/* 「个人投资工作台」聚合页 · 专项自检
   用法：NODE_PATH=<含 jsdom 的 node_modules> node tools/check_home.js

   覆盖：分页切换与状态保持、月历切换、事件渲染（含「单类型/零事件日」回归）、
        选股表六字段、日期区间筛选、断层幅度排序、响应式与交叉链接、注入防护。
*/
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const HTML = process.env.HOME_HTML || path.join(__dirname, "..", "个人投资工作台.html");
const CAL_URL = "https://market-calendar-71280.app.workbuddy.host/";
const LSKEY = "pgwb.page";

const html = fs.readFileSync(HTML, "utf-8");

let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log("  ✔ " + name); }
  else { fail++; console.log("  ✘ " + name + (extra !== undefined ? "  → " + extra : "")); }
}
function payload(src, id) {
  const re = new RegExp('<script[^>]*id="' + id + '"[^>]*>([\\s\\S]*?)</script>');
  const m = src.match(re);
  return m ? JSON.parse(m[1]) : null;
}
function boot(opts) {
  const o = Object.assign({
    runScripts: "dangerously",
    pretendToBeVisual: true,
    url: "https://jasonling110-a11y.github.io/profit-gap/home.html",
    resources: undefined,
  }, opts || {});
  const dom = new JSDOM(html, o);
  return { dom, window: dom.window, doc: dom.window.document };
}
const click = (w, el) => el.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));

/* ============ 数据侧（直接从 HTML 里的 JSON 读，不信任页面 DOM） ============ */
const CAL = payload(html, "cal-payload");
const PK = payload(html, "pk-payload");
const EV = CAL.events;
const ROWS = PK.rows;
const TYPES = CAL.meta.types;
const TODAY = CAL.meta.today;

console.log("=== 「个人投资工作台」聚合页自检 ===\n");
console.log(`（数据：事件 ${EV.length} 条 / 清单 ${ROWS.length} 只 / 类型 ${TYPES.length} 类 / 今天 ${TODAY}）\n`);

/* ================= 1. 静态结构 ================= */
console.log("[1] 结构与可用性");
{
  const { window: w, doc } = boot();
  const $ = (id) => doc.getElementById(id);

  ok("存在 tablist", !!doc.querySelector('[role="tablist"]') &&
     doc.querySelectorAll('[role="tab"]').length === 2);
  ok("两个分页标签 id 正确", !!$("tabCal") && !!$("tabPk"));
  ok("两个 tabpanel 且 aria-labelledby 齐全",
     $("pgCal").getAttribute("role") === "tabpanel" &&
     $("pgPicks").getAttribute("role") === "tabpanel" &&
     $("pgCal").getAttribute("aria-labelledby") === "tabCal" &&
     $("pgPicks").getAttribute("aria-labelledby") === "tabPk");
  ok("日历页骨架：月切按钮 / 月标签 / 网格 / 事件列表",
     !!$("mPrev") && !!$("mNext") && !!$("mToday") && !!$("mLabel") && !!$("mGrid") && !!$("dList"));
  ok("选股页骨架：区间 / 快捷 / 搜索 / 重置 / 表体 / 汇总",
     !!$("pFrom") && !!$("pTo") && !!$("pQ") && !!$("pReset") && !!$("pBody") && !!$("pSum"));
  ok("表格 6 列表头齐备",
     doc.querySelectorAll("#pTbl th[data-k]").length === 6);
  ok("表头字段名与需求一致（名称代码/断层日期/断层幅度/当日涨跌幅/成交量/行业）",
     ["n","d","g","dc","v","i"].join(",") ===
     Array.from(doc.querySelectorAll("#pTbl th[data-k]")).map(t => t.dataset.k).join(","));
  ok("表格有 caption（无障碍）", !!doc.querySelector("#pTbl caption"));
  ok("跳转主看板的链接可达",
     !!Array.from(doc.querySelectorAll("footer a")).find(a => a.getAttribute("href") === "利润断层工作台.html"));
  ok("页头有显眼的「完整看板」入口（K 线/散点图都在那边）",
     ($("goFull") || {}).getAttribute && $("goFull").getAttribute("href") === "利润断层工作台.html");
  ok("市场日历外链带 rel=noopener",
     Array.from(doc.querySelectorAll("footer a")).some(a => a.href === CAL_URL && /noopener/.test(a.rel || "")));
  ok("含免责声明", /不构成个人投资建议/.test(doc.body.textContent));
  ok("viewport meta 存在（响应式前提）",
     !!doc.querySelector('meta[name="viewport"]'));
  ok("零外部依赖（无 <script src> / 无远程样式表）",
     doc.querySelectorAll("script[src]").length === 0 &&
     !/<link[^>]+rel=["']?stylesheet/i.test(html));
}

/* ================= 2. 分页切换 ================= */
console.log("\n[2] 分页切换");
{
  const { window: w, doc } = boot();
  const $ = (id) => doc.getElementById(id);

  ok("默认停在「投资日历」",
     $("tabCal").getAttribute("aria-selected") === "true" &&
     $("tabPk").getAttribute("aria-selected") === "false");
  ok("默认日历页可见、选股页 hidden", !$("pgCal").hidden && $("pgPicks").hidden === true);

  click(w, $("tabPk"));
  ok("点标签切到选股平台",
     $("tabPk").getAttribute("aria-selected") === "true" &&
     $("tabCal").getAttribute("aria-selected") === "false");
  ok("选股页显示、日历页隐藏", $("pgCal").hidden === true && !$("pgPicks").hidden);
  ok("hash 写为 #picks", w.location.hash === "#picks", w.location.hash);
  ok("localStorage 记住分页", w.localStorage.getItem(LSKEY) === "picks",
     w.localStorage.getItem(LSKEY));

  click(w, $("tabCal"));
  ok("切回日历页", !$("pgCal").hidden && $("pgPicks").hidden === true);
  ok("hash 更新为 #calendar", w.location.hash === "#calendar", w.location.hash);
  ok("localStorage 同步为 calendar", w.localStorage.getItem(LSKEY) === "calendar");
}

/* ================= 3. 分页状态保持（三种进入方式） ================= */
console.log("\n[3] 分页状态保持");
{
  // 3a. 带 #picks 深链直接打开
  const a = boot({ url: "https://jasonling110-a11y.github.io/profit-gap/home.html#picks" });
  ok("深链 #picks 打开即停在选股平台",
     !a.doc.getElementById("pgPicks").hidden && a.doc.getElementById("pgCal").hidden === true);

  // 3b. 无 hash，但上次选的是 picks → 落到 localStorage
  const b = boot({
    beforeParse(win) { try { win.localStorage.setItem(LSKEY, "picks"); } catch (e) {} },
  });
  ok("无 hash 时按 localStorage 恢复到选股平台",
     !b.doc.getElementById("pgPicks").hidden,
     "localStorage=" + b.window.localStorage.getItem(LSKEY));

  // 3c. hash 与 localStorage 冲突 → hash 优先
  const c = boot({
    url: "https://jasonling110-a11y.github.io/profit-gap/home.html#calendar",
    beforeParse(win) { try { win.localStorage.setItem(LSKEY, "picks"); } catch (e) {} },
  });
  ok("hash 优先于 localStorage（显式 #calendar 覆盖记忆值）",
     !c.doc.getElementById("pgCal").hidden && c.doc.getElementById("pgPicks").hidden === true);

  // 3d. 会话内切换后再切回，日历选中日不丢
  const d = boot();
  const wd = d.window, dd = d.doc;
  const evDay = Object.keys(EV.reduce((m, e) => (m[e.d] = 1, m), {})).sort()
    .find(x => x.slice(0, 7) === TODAY.slice(0, 7)) || TODAY;
  const cell = dd.querySelector('.cell[data-d="' + evDay + '"]');
  click(wd, cell);
  const beforeTitle = dd.getElementById("dTitle").textContent;
  click(wd, dd.getElementById("tabPk"));
  click(wd, dd.getElementById("tabCal"));
  ok("跨分页切换后日历选中日保持",
     dd.getElementById("dTitle").textContent === beforeTitle && beforeTitle.length > 0,
     beforeTitle + " → " + dd.getElementById("dTitle").textContent);
}

/* ================= 4. 投资日历：月份切换 ================= */
console.log("\n[4] 投资日历 · 月份切换");
{
  const { window: w, doc } = boot();
  const $ = (id) => doc.getElementById(id);
  const label0 = $("mLabel").textContent;

  ok("月标签非空且含年月", /年\d+月/.test($("mLabel").textContent), label0);
  ok("默认月 = 数据里的今天所在月", label0 === Number(TODAY.slice(0, 4)) + "年" + Number(TODAY.slice(5, 7)) + "月",
     label0);

  click(w, $("mNext"));
  ok("下一月生效", $("mLabel").textContent !== label0, $("mLabel").textContent);
  const label1 = $("mLabel").textContent;
  click(w, $("mPrev"));
  ok("上一月可回到原月", $("mLabel").textContent === label0, $("mLabel").textContent);
  click(w, $("mPrev"));
  click(w, $("mToday"));
  ok("「今天」回到当月", $("mLabel").textContent === label0);
  ok("月份切换后网格重新渲染（周首行 7 格）",
     doc.querySelectorAll("#mGrid .hd").length === 7 &&
     doc.querySelectorAll("#mGrid .cell").length % 7 === 0);
  ok("网格周首为「一」（周一起始）",
     Array.from(doc.querySelectorAll("#mGrid .hd")).map(e => e.textContent).join("") === "一二三四五六日");
}

/* ================= 5. 投资日历：事件渲染（含回归） ================= */
console.log("\n[5] 投资日历 · 事件渲染");
{
  const { window: w, doc } = boot();
  const $ = (id) => doc.getElementById(id);

  const byDay = EV.reduce((m, e) => ((m[e.d] || (m[e.d] = [])).push(e), m), {});
  const inMonth = Object.keys(byDay).filter(d => d.slice(0, 7) === TODAY.slice(0, 7)).sort();
  const multiDay = inMonth.filter(d => new Set(byDay[d].map(e => e.t)).size >= 2)[0];
  const singleDay = inMonth.filter(d => new Set(byDay[d].map(e => e.t)).size === 1)[0];
  const zeroDay = (() => {
    const [y, m] = TODAY.split("-").map(Number);
    const n = new Date(y, m, 0).getDate();
    for (let d = 1; d <= n; d++) {
      const ds = TODAY.slice(0, 7) + "-" + String(d).padStart(2, "0");
      if (!byDay[ds]) return ds;
    }
    return null;
  })();

  ok("存在多类型日（用于验证筛选条）", !!multiDay, multiDay);
  ok("月视图内格子上有事件数角标", doc.querySelectorAll("#mGrid .cell .n").length > 0);
  ok("月视图有类型色点", doc.querySelectorAll("#mGrid .cell .dots i").length > 0);

  // --- 多类型日：出现类型筛选条 ---
  click(w, doc.querySelector('.cell[data-d="' + multiDay + '"]'));
  ok("选中日高亮（.sel 唯一）",
     doc.querySelectorAll("#mGrid .cell.sel").length === 1 &&
     doc.querySelector('#mGrid .cell.sel').dataset.d === multiDay);
  ok("详情标题为该日", $("dTitle").textContent.includes(String(Number(multiDay.slice(8, 10)))));
  ok("事件数文案正确", $("dCount").textContent === byDay[multiDay].length + " 个事件",
     $("dCount").textContent);
  ok("多类型日出现类型筛选条", $("dFilter").style.display !== "none" &&
     doc.querySelectorAll("#dFilter .chip").length >= 2);
  ok("事件列表按类型分组", doc.querySelectorAll("#dList .bdgrp").length >= 2);
  const firstOfMulti = byDay[multiDay][0].n;
  ok("事件列表渲染出具体标的", $("dList").textContent.includes(firstOfMulti), firstOfMulti);
  ok("事件行含类型标签", doc.querySelectorAll("#dList .ev .tag").length > 0);

  // 关掉一个类型应减少条目
  const cntBefore = doc.querySelectorAll("#dList .ev").length;
  const chip = doc.querySelector("#dFilter .chip");
  click(w, chip);
  ok("关掉某类型后条目减少", doc.querySelectorAll("#dList .ev").length < cntBefore,
     cntBefore + " → " + doc.querySelectorAll("#dList .ev").length);
  click(w, chip); // 还原

  // --- 回归：单类型日必须照常渲染列表（曾因 early-return 而整块空白） ---
  if (singleDay) {
    const stale = $("dList").innerHTML;
    click(w, doc.querySelector('.cell[data-d="' + singleDay + '"]'));
    const nm = byDay[singleDay][0].n;
    ok("【回归】单类型日的事件列表被重绘（不是上一天残留）",
       $("dList").innerHTML !== stale);
    ok("【回归】单类型日渲染出该日标的", $("dList").textContent.includes(nm), nm);
    ok("【回归】单类型日不给筛选条（且已隐藏）", $("dFilter").style.display === "none");
    ok("【回归】单类型日事件数文案正确",
       $("dCount").textContent === byDay[singleDay].length + " 个事件", $("dCount").textContent);
  } else {
    ok("【回归】单类型日：本月无此类日期（跳过）", true);
  }

  // --- 回归：零事件日必须给出空态，且不能留上一天的内容 ---
  if (zeroDay) {
    const stale = $("dList").innerHTML;
    click(w, doc.querySelector('.cell[data-d="' + zeroDay + '"]'));
    ok("【回归】零事件日列表已重绘", $("dList").innerHTML !== stale);
    ok("【回归】零事件日给出「没有事件」空态",
       /这一天没有事件/.test($("dList").textContent), $("dList").textContent.trim().slice(0, 40));
    ok("【回归】零事件日事件数为 0", $("dCount").textContent === "0 个事件", $("dCount").textContent);
  } else {
    ok("【回归】零事件日：本月每天都有事件（跳过）", true);
  }

  // 筛选条被关掉后换日 → 开关应被重置（否则可能无法恢复）
  click(w, doc.querySelector('.cell[data-d="' + multiDay + '"]'));
  if (doc.querySelectorAll("#dFilter .chip").length) {
    click(w, doc.querySelectorAll("#dFilter .chip")[0]);      // 关掉一个
    const off = doc.querySelectorAll("#dFilter .chip:not(.on)").length;
    const other = multiDay === singleDay ? null : multiDay;
    click(w, doc.querySelector('.cell[data-d="' + (singleDay || zeroDay || multiDay) + '"]'));
    click(w, doc.querySelector('.cell[data-d="' + other + '"]'));
    ok("换日后当日类型开关被重置（不会卡在无法恢复的状态）",
       doc.querySelectorAll("#dFilter .chip:not(.on)").length === 0,
       "关掉的 chip 数 " + off + " → " + doc.querySelectorAll("#dFilter .chip:not(.on)").length);
  } else {
    ok("换日后当日类型开关被重置（本月无多类型日，跳过）", true);
  }
}

/* ================= 6. 选股平台：字段与初值 ================= */
console.log("\n[6] 利润断层选股平台 · 字段");
{
  const { doc } = boot();
  const body = doc.getElementById("pBody");
  const trs = body.querySelectorAll("tr");
  const dataTrs = Array.from(trs).filter(t => !t.querySelector(".empty"));

  ok("默认区间 = 全量（不隐藏任何个股）", dataTrs.length === ROWS.length,
     dataTrs.length + " / " + ROWS.length);
  ok("每行 6 个单元格", dataTrs.every(t => t.children.length === 6));
  ok("每格带 data-label（列名基线；窄屏已改为真表格，该属性留作兜底）",
     dataTrs.every(t => Array.from(t.children).every(td => td.dataset.label)));
  ok("首列含股票名称与代码",
     /<b>/.test(body.innerHTML) && /<code>/.test(body.innerHTML));
  ok("含分层标签", doc.querySelectorAll("#pBody .tier").length > 0);
  const first = ROWS.find(r => r.g != null);
  ok("断层幅度按 +x.xx% 展示", body.textContent.includes(first.g.toFixed(2) + "%"));
  ok("成交量已格式化（手 / 万手）", /(手)/.test(body.textContent), body.textContent.slice(0, 60));
  ok("涨跌用红涨绿跌（中国习惯）",
     /class="up"/.test(body.innerHTML) || /class="down"/.test(body.innerHTML));
  ok("汇总行给出清单数", doc.getElementById("pSum").textContent.includes(ROWS.length + ""));
  ok("行业列有值", ROWS.every(r => r.i && String(r.i).length > 0));
}

/* ================= 7. 选股平台：排序 ================= */
console.log("\n[7] 利润断层选股平台 · 排序");
{
  const { window: w, doc } = boot();
  const $ = (id) => doc.getElementById(id);
  // 从 DOM 反读每行的断层幅度（%），用于验证真实排序结果
  const gapsInDom = () => Array.from($("pBody").querySelectorAll("tr"))
    .map(t => t.children[2] && t.children[2].textContent)
    .filter(x => x && x !== "—")
    .map(x => parseFloat(String(x).replace("%", "")));

  ok("默认按断层幅度降序（表头 aria-sort=descending）",
     $("thGap").getAttribute("aria-sort") === "descending" &&
     $("thGap").classList.contains("on") && !$("thGap").classList.contains("asc"),
     $("thGap").outerHTML.slice(0, 120));
  let g = gapsInDom();
  ok("首列确实递减", g.every((v, i) => i === 0 || g[i - 1] >= v), g.slice(0, 6).join(","));
  ok("最大值 = 数据里的最大断层幅度",
     Math.abs(g[0] - Math.max(...ROWS.map(r => r.g))) < 1e-6, g[0]);

  click(w, $("thGap"));
  g = gapsInDom();
  ok("再点一次转升序", g.every((v, i) => i === 0 || g[i - 1] <= v), g.slice(0, 6).join(","));
  ok("升序时表头升序态", $("thGap").classList.contains("asc") &&
     $("thGap").getAttribute("aria-sort") === "ascending");

  const datesInDom = () => Array.from($("pBody").querySelectorAll("tr"))
    .map(t => t.children[1] && t.children[1].textContent).filter(x => x && x !== "—");
  click(w, $("thDate"));
  let d = datesInDom();
  ok("点「断层日期」首点升序", d.every((v, i) => i === 0 || d[i - 1] <= v), d.slice(0, 4).join(","));
  click(w, $("thDate"));
  d = datesInDom();
  ok("再点转降序", d.every((v, i) => i === 0 || d[i - 1] >= v), d.slice(0, 4).join(","));
  ok("换列排序后原列高亮被移除",
     !$("thGap").classList.contains("on") && !$("thGap").hasAttribute("aria-sort"));
}

/* ================= 8. 选股平台：日期区间筛选 ================= */
console.log("\n[8] 利润断层选股平台 · 日期区间筛选");
{
  const { window: w, doc } = boot();
  const $ = (id) => doc.getElementById(id);
  const nRows = () => $("pBody").querySelectorAll("tr:not(:has(.empty))").length;
  const domDates = () => Array.from($("pBody").querySelectorAll("tr"))
    .map(t => t.children[1] && t.children[1].textContent).filter(x => x && x !== "—");

  const ds = ROWS.map(r => r.d).filter(Boolean).sort();
  const lo = ds[0], hi = ds[ds.length - 1];
  ok("默认填入了完整区间", $("pFrom").value === lo && $("pTo").value === hi,
     $("pFrom").value + " ~ " + $("pTo").value);

  // 手填一个中段区间
  const mid = ds[Math.floor(ds.length / 2)];
  $("pFrom").value = mid; $("pTo").value = hi;
  $("pFrom").dispatchEvent(new w.Event("change", { bubbles: true }));
  const expect = ROWS.filter(r => r.d >= mid && r.d <= hi).length;
  ok("区间收窄后条数正确", nRows() === expect, nRows() + " vs 期望 " + expect);
  ok("区间内所有日期都落在区间内",
     domDates().every(x => x >= mid && x <= hi), mid + " ~ " + hi);
  ok("区间收窄确实少于全量", nRows() < ROWS.length);

  // 快捷「近 7 天」
  const btn7 = doc.querySelector('[data-range="7"]');
  click(w, btn7);
  ok("快捷按钮置为选中态", btn7.classList.contains("on"));
  ok("快捷按钮写回了输入框", $("pTo").value === TODAY, $("pTo").value);
  const exp7 = ROWS.filter(r => r.d >= null || true).filter(r => {
    const t = new Date(TODAY + "T00:00:00");
    const s = new Date(t.getTime() - 6 * 86400000);
    const ymd = s.getFullYear() + "-" + String(s.getMonth() + 1).padStart(2, "0") + "-" + String(s.getDate()).padStart(2, "0");
    return r.d >= ymd && r.d <= TODAY;
  }).length;
  ok("近 7 天条数正确", nRows() === exp7, nRows() + " vs 期望 " + exp7);

  // 全部
  click(w, doc.querySelector('[data-range="0"]'));
  ok("「全部」恢复全量", nRows() === ROWS.length, nRows() + " / " + ROWS.length);
  ok("「全部」清空输入框", $("pFrom").value === "" && $("pTo").value === "");

  // 搜索
  const code = ROWS[0].c;
  $("pQ").value = code;
  $("pQ").dispatchEvent(new w.Event("input", { bubbles: true }));
  ok("按代码搜索命中该股", nRows() === 1 && $("pBody").textContent.includes(code),
     nRows() + " 行");
  $("pQ").value = ROWS[0].n;
  $("pQ").dispatchEvent(new w.Event("input", { bubbles: true }));
  ok("按名称搜索可命中", nRows() >= 1 && $("pBody").textContent.includes(ROWS[0].n));
  $("pQ").value = "zzz不存在zzz";
  $("pQ").dispatchEvent(new w.Event("input", { bubbles: true }));
  ok("无命中时给出空态行", !!$("pBody").querySelector(".empty") && nRows() === 0);

  // 重置
  click(w, $("pReset"));
  ok("重置恢复全量", nRows() === ROWS.length, nRows() + " / " + ROWS.length);
  ok("重置清空搜索框", $("pQ").value === "");
  ok("重置回到断层幅度降序",
     $("thGap").classList.contains("on") && $("thGap").getAttribute("aria-sort") === "descending");

  // 汇总随筛选变化
  $("pFrom").value = ds[ds.length - 1]; $("pTo").value = ds[ds.length - 1];
  $("pFrom").dispatchEvent(new w.Event("change", { bubbles: true }));
  ok("汇总数字跟随筛选更新", $("pSum").textContent.includes("全量 " + ROWS.length + " 只"),
     $("pSum").textContent.trim().slice(0, 80));
}

/* ================= 9. 数据完整性提示 ================= */
console.log("\n[9] 数据完整性提示");
{
  const { doc } = boot();
  const note = doc.getElementById("pNote");
  const cnote = doc.getElementById("cNote");
  const hasPk = (PK.problems || []).length > 0;
  const hasCal = (CAL.problems || []).length > 0;
  ok("清单问题：有则显示、无则隐藏",
     hasPk ? note.hidden === false : note.hidden === true,
     "PK.problems=" + JSON.stringify(PK.problems));
  ok("日历问题：有则显示、无则隐藏（两路失败都不能静默）",
     hasCal ? cnote.hidden === false : cnote.hidden === true,
     "CAL.problems=" + JSON.stringify(CAL.problems));
  ok("当前数据无 problems（事件 16151 条 / 清单 91 只）", !hasPk && !hasCal);
  ok("日历抓取来源全部有状态登记（无来源被吞掉）",
     Array.isArray(CAL.sources) && CAL.sources.length >= 5 &&
     CAL.sources.every(s => s.name && s.status),
     (CAL.sources || []).map(s => s.name + ":" + s.status).join(" / "));
}

/* ================= 10. 响应式与注入防护 ================= */
console.log("\n[10] 响应式与安全");
{
  const style = (html.match(/<style>([\s\S]*?)<\/style>/) || [, ""])[1];
  ok("有 820px 断点（隐藏格子文案）", /@media\(max-width:820px\)/.test(style));
  ok("有 560px 断点", /@media\(max-width:560px\)/.test(style));
  // 窄屏策略 2026-10-06 由「转竖排卡片」改为「保留真表格 + 横向滚动 + 名称列吸附」：
  // 卡片版一只股票占 6 行、一屏只看得到两三只，用户实测后要求「像电脑端一样做一个完整的列表」。
  // 这两条是反向断言——一旦有人把 td:before/thead 隐藏那套写回来，这里必须失败。
  ok("窄屏保留真表格（不再转竖排卡片）",
     !/table thead\{display:none\}/.test(style) && !/td:before\{content:attr\(data-label\)/.test(style));
  ok("窄屏选股表「名称 / 代码」列吸附左侧（横向滑动不迷失）",
     /#pTbl td:first-child\{position:sticky;left:0/.test(style));
  ok("窄屏选股表字号收紧到 12px（一行一只仍可读）", /#pTbl\{font-size:12px\}/.test(style));
  ok("标签栏在窄屏铺满", /\.tabs\{flex:1\}/.test(style));
  // 月历网格必须用 minmax(0,1fr)：用 1fr 时列的最小宽度是 min-content，
  // 320px 屏上「日号 + 事件数」会把网格顶宽 → 页面横向溢出（实测溢出 36 个节点）。
  ok("月历网格列可压缩（minmax(0,1fr)，防极窄屏横向溢出）",
     /grid-template-columns:repeat\(7,minmax\(0,1fr\)\)/.test(style));
  ok("格子有 overflow:hidden（内容不顶破网格）", /\.cell\{[^}]*overflow:hidden/.test(style));
  ok("有 ≤380px 极窄屏规则（隐藏数字角标只留色点）", /@media\(max-width:380px\)/.test(style));
  ok("尊重 prefers-reduced-motion", /prefers-reduced-motion:reduce/.test(style));
  ok("JSON 已转义 <（防 </script> 提前闭合）",
     !/<\/script>/.test(html.slice(html.indexOf('id="cal-payload"'), html.indexOf('id="cal-payload"') + 400)));
  ok("payload JSON 可被 JSON.parse", !!CAL && !!PK && Array.isArray(ROWS) && Array.isArray(EV));

  // 事件类型色板齐全
  ok("7 种事件类型全部有颜色变量",
     TYPES.every((_, i) => new RegExp("--t" + (i % 7) + ":").test(style)), TYPES.join("/"));
  ok("沿用主看板深色变量（--bg/--up/--down）",
     /--bg:#0d1117/.test(style) && /--up:#f0483e/.test(style) && /--down:#22a06b/.test(style));
}

console.log("\n----------------------------");
console.log(`通过 ${pass} 项，失败 ${fail} 项`);
console.log(fail === 0 ? "✅ 个人投资工作台自检通过" : "❌ 存在失败项");
process.exit(fail === 0 ? 0 : 1);
