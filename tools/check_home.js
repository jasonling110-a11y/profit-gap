/* 「个人投资工作台」聚合页 · 专项自检
   用法：NODE_PATH=<含 jsdom 的 node_modules> node tools/check_home.js

   覆盖：分页切换与状态保持、月历切换、事件渲染（含「单类型/零事件日」回归）、
        选股表七字段、日期区间筛选、断层幅度排序、响应式与交叉链接、注入防护。
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
/* 空安全：负向测试会把「指数看盘」整个模块摘掉，此时 $("tabIdx") / $("idxFrame") 是 null。
   直接 .dispatchEvent / .getAttribute 抛 TypeError 会让脚本崩在中间，后面的断言根本不会跑
   （等于没测）—— check_calendar.js 实测吃过这个亏，只报了 46 条里的 3 条。 */
const click = (w, el) => { if (el) el.dispatchEvent(new w.MouseEvent("click", { bubbles: true })); };
const attrOf = (doc, id, a) => { const el = doc.getElementById(id); return el ? el.getAttribute(a) : null; };
const hiddenOf = (doc, id) => { const el = doc.getElementById(id); return el ? el.hidden : null; };

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

  ok("存在 tablist，且三个页卡", !!doc.querySelector('[role="tablist"]') &&
     doc.querySelectorAll('[role="tab"]').length === 3);
  ok("三个分页标签 id 正确", !!$("tabCal") && !!$("tabIdx") && !!$("tabPk"));
  ok("三个 tabpanel 且 aria-labelledby 齐全",
     attrOf(doc, "pgCal", "role") === "tabpanel" &&
     attrOf(doc, "pgIdx", "role") === "tabpanel" &&
     attrOf(doc, "pgPicks", "role") === "tabpanel" &&
     attrOf(doc, "pgCal", "aria-labelledby") === "tabCal" &&
     attrOf(doc, "pgIdx", "aria-labelledby") === "tabIdx" &&
     attrOf(doc, "pgPicks", "aria-labelledby") === "tabPk");
  // 用户要求「三个页卡换到左边竖着排列」：侧栏必须存在于 DOM 且在 <main> 之前，
  // 否则 CSS 就算写了 column 方向，视觉上页卡也还是落在正文里。
  ok("页卡位于左侧竖排侧栏（.sidenav 在 <main> 之前，且含 tablist）",
     !!doc.querySelector("nav.sidenav") &&
     !!doc.querySelector("nav.sidenav [role=tablist]") &&
     (doc.querySelector("nav.sidenav").compareDocumentPosition(doc.querySelector("main")) &
      doc.defaultView.Node.DOCUMENT_POSITION_FOLLOWING) !== 0);
  const navTl = doc.querySelector("nav.sidenav [role=tablist]");
  ok("侧栏 tablist 声明竖排（aria-orientation=vertical）",
     !!navTl && navTl.getAttribute("aria-orientation") === "vertical");
  ok("页卡顺序 = 投资日历 / 指数看盘 / 利润断层",
     Array.from(doc.querySelectorAll("nav.sidenav [role=tab]")).map(b => b.textContent.trim()).join(",") ===
     "投资日历,指数看盘,利润断层");
  ok("指数看盘面板骨架：iframe / 加载遮罩（工具栏按钮已按要求删除）",
     !!$("idxFrame") && !!$("idxLoad"));
  // 懒加载前提：首屏不得带 src，否则等于白等一个 117 KB 的外部应用
  ok("指数看盘 iframe 首屏无 src（懒加载）",
     !!$("idxFrame") && !attrOf(doc, "idxFrame", "src"));
  /* ---- 2026-10-06：三个页卡直接内嵌「完整应用」，工具栏整排按钮删除 -------------
     用户两轮要求：①「点击页卡后直接展示完整页面，无需多余的中间跳转」；
     ②「把完整日历/工作台月历/新窗口打开/重新加载这几个按钮都去掉，指数看盘和利润断层页同理」。
     所以现在每个页卡只剩 .ext > iframe + 加载遮罩，页面干净；
     自建月历/自建选股表的 DOM 仍保留在页内（hidden，已无入口）。 */
  ok("三个页卡的工具栏按钮已全部删除（viewsw / 新窗口打开 / 重新加载）",
     !doc.querySelector(".extops") && !doc.querySelector(".viewsw") &&
     !$("calVFull") && !$("calVIn") && !$("pkVFull") && !$("pkVIn") &&
     !$("calNew") && !$("pkNew") && !$("idxNew") &&
     !$("calReload") && !$("pkReload") && !$("idxReload"));
  ok("页内不再有工具栏/提示文案（连 .hint 一并去掉）",
     !/class="hint"/.test(html) && !/extops/.test(html));
  ok("三个页卡各有内嵌 iframe（完整应用）",
     !!$("calFrame") && !!$("pkFrame") && !!$("idxFrame"));
  // 懒加载 = 首屏只拉「当前页卡」那一个 iframe。默认页是投资日历，所以 calFrame 该有 src，
  // 而另外两个（指数看盘 / 利润断层）必须是空的 —— 首屏白等两个几 MB 的外部应用才是 bug。
  ok("首屏只拉当前页卡的 iframe：指数看盘 / 利润断层仍无 src",
     !attrOf(doc, "idxFrame", "src") && !attrOf(doc, "pkFrame", "src") &&
     /^https:\/\/market-calendar-71280\.app\.workbuddy\.host\//.test(attrOf(doc, "calFrame", "src") || ""),
     "idx=" + attrOf(doc, "idxFrame", "src") + " pk=" + attrOf(doc, "pkFrame", "src"));
  // 云笔记要走它自己那个源的登录流程，sandbox 必须放行弹窗 / 模态 / 同源 / 表单，
  // 少一个 allow-same-origin，笔记的云端读写就会静默失效。
  ok("日历 iframe 的 sandbox 放行脚本/同源/表单/弹窗/模态（云笔记登录要用）", (() => {
     const sb = attrOf(doc, "calFrame", "sandbox") || "";
     return ["allow-scripts", "allow-same-origin", "allow-forms", "allow-popups", "allow-modals"]
       .every(x => sb.includes(x));
  })(), attrOf(doc, "calFrame", "sandbox"));
  ok("日历页 = 完整日历（内嵌应用直接可见，无中间层）",
     hiddenOf(doc, "calExt") === false && hiddenOf(doc, "calIn") === true);
  ok("利润断层页 = 完整看板（内嵌应用直接可见，无中间层）",
     hiddenOf(doc, "pkExt") === false && hiddenOf(doc, "pkIn") === true);
  /* 自建月历 / 自建选股表没有入口了，但节点仍保留在页内（用户只要求删按钮）。
     这两条是存在性断言 —— 如果将来要彻底删掉它们，先改这里再删 DOM。 */
  ok("自建月历节点仍保留（无入口，仅隐藏）",
     !!$("calIn") && !!$("calIn").querySelector("#mGrid") && !!$("calIn").querySelector("#dList") &&
     !!$("calIn").querySelector("#mPrev") && !!$("calIn").querySelector("#mToday") &&
     !!$("calIn").querySelector("#mLabel"));
  ok("自建选股表节点仍保留（无入口，仅隐藏）",
     !!$("pkIn") && !!$("pkIn").querySelector("#pTbl") && !!$("pkIn").querySelector("#pBody") &&
     !!$("pkIn").querySelector("#pFrom") && !!$("pkIn").querySelector("#pSum"));
  ok("日历页骨架：月切按钮 / 月标签 / 网格 / 事件列表",
     !!$("mPrev") && !!$("mNext") && !!$("mToday") && !!$("mLabel") && !!$("mGrid") && !!$("dList"));
  ok("选股页骨架：区间 / 快捷 / 搜索 / 重置 / 表体 / 汇总",
     !!$("pFrom") && !!$("pTo") && !!$("pQ") && !!$("pReset") && !!$("pBody") && !!$("pSum"));
  ok("表格 7 列表头齐备",
     doc.querySelectorAll("#pTbl th[data-k]").length === 7);
  ok("表头字段名与需求一致（名称代码/断层日期/断层幅度/连续断层/当日涨跌幅/成交量/行业）",
     ["n","d","g","s","dc","v","i"].join(",") ===
     Array.from(doc.querySelectorAll("#pTbl th[data-k]")).map(t => t.dataset.k).join(","));
  ok("表格有 caption（无障碍）", !!doc.querySelector("#pTbl caption"));
  ok("跳转主看板的链接可达",
     !!Array.from(doc.querySelectorAll("footer a")).find(a => a.getAttribute("href") === "利润断层工作台.html"));
  /* 2026-10-06 用户要求「评估『查看完整 K 线图』这一入口的必要性，并调整为点击页卡后
     直接展示完整页面，无需多余的中间跳转」。三个页卡现在都直接内嵌完整应用，页头那个
     「完整看板（含 K 线）」(#goFull → 利润断层工作台.html) 就成了多余的中间跳转 —— 已删除。
     这是反向断言：谁把它加回来，这里必须先红。 */
  ok("页头的「完整看板（含 K 线）」中间跳转入口已删除",
     !$("goFull") && !/id="goFull"/.test(html) && !/完整看板（含 K 线）<\/a>/.test(html));
  /* 2026-10-06 二次要求：工具栏整排按钮（含「新窗口打开」）全部删除，只留内嵌应用。
     这是反向断言：谁把按钮加回来，这里必须先红。独立大屏需求由页脚的既有链接承接。 */
  ok("页卡上的「新窗口打开」按钮已删除（大屏需求走页脚链接）",
     !$("calNew") && !$("pkNew") && !$("idxNew") && !/id="(calNew|pkNew|idxNew)"/.test(html));
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

  ok("默认停在「投资日历」（主页）",
     attrOf(doc, "tabCal", "aria-selected") === "true" &&
     attrOf(doc, "tabIdx", "aria-selected") === "false" &&
     attrOf(doc, "tabPk", "aria-selected") === "false");
  ok("默认日历页可见、另外两页 hidden",
     hiddenOf(doc, "pgCal") === false && hiddenOf(doc, "pgIdx") === true && hiddenOf(doc, "pgPicks") === true);

  click(w, $("tabIdx"));
  ok("点「指数看盘」切到该页",
     attrOf(doc, "tabIdx", "aria-selected") === "true" &&
     attrOf(doc, "tabCal", "aria-selected") === "false" &&
     attrOf(doc, "tabPk", "aria-selected") === "false");
  ok("指数看盘页显示、其余隐藏",
     hiddenOf(doc, "pgIdx") === false && hiddenOf(doc, "pgCal") === true && hiddenOf(doc, "pgPicks") === true);
  ok("hash 写为 #indices", w.location.hash === "#indices", w.location.hash);
  const src1 = attrOf(doc, "idxFrame", "src");
  ok("首次切到指数看盘才写入 iframe src",
     src1 === "https://global-market-dashboard-68975.app.workbuddy.host/", src1);
  ok("首次加载不带缓存戳（便于断言与复用浏览器缓存）", !/_r=/.test(src1 || ""), src1);

  // 来回切一次：不应重写 src，否则页面里的月份选择 / 滚动位置每次回来都被重置。
  // 只比较 src 的「值」是测不出问题的——重写成同一个 URL 值不变，照样是一次真实导航。
  // 所以这里在 iframe 上挂个探针，直接数「产品代码有没有再调 setAttribute('src')」。
  let srcWrites = 0;
  const frame = $("idxFrame");                       // 负向测试里可能是 null
  const origSet = frame ? frame.setAttribute.bind(frame) : null;
  if (frame) frame.setAttribute = function (n, v) { if (n === "src") srcWrites++; return origSet(n, v); };
  click(w, $("tabCal"));
  click(w, $("tabIdx"));
  if (frame) frame.setAttribute = origSet;
  ok("来回切换不重写已加载的 iframe src",
     !!src1 && srcWrites === 0, "src=" + src1 + " 重写次数=" + srcWrites);

  /* 「重新加载」按钮已删，重试能力收进加载遮罩：jsdom 里 load 事件不会来，
     所以遮罩一直处于 .on 态 —— 点它一下应当带时间戳强刷（绕缓存）。 */
  ok("加载遮罩处于显示态（jsdom 无 load 事件，属预期）",
     !!$("idxLoad") && $("idxLoad").classList.contains("on"));
  click(w, $("idxLoad"));
  const src2 = attrOf(doc, "idxFrame", "src");
  ok("点加载遮罩重试 = 加时间戳强刷（绕缓存，隐形兜底不占版面）",
     /^https:\/\/global-market-dashboard-68975\.app\.workbuddy\.host\/\?_r=\d+$/.test(src2 || ""), src2);
  ok("重试后 src 与首次不同（确实重新发起了请求）", src2 !== src1);
  // jsdom 的 20s 超时定时器在同步断言里还没触发，所以「点这里重试」那句只能做静态检查；
  // 动态部分（点了遮罩真的会重写 src）上面两条已经验过。
  ok("超时文案写明「点这里重试」（源码静态检查）", /点这里重试/.test(html));

  click(w, $("tabPk"));
  ok("点标签切到选股平台",
     attrOf(doc, "tabPk", "aria-selected") === "true" &&
     attrOf(doc, "tabCal", "aria-selected") === "false");
  ok("选股页显示、其余隐藏",
     hiddenOf(doc, "pgCal") === true && hiddenOf(doc, "pgIdx") === true && hiddenOf(doc, "pgPicks") === false);
  ok("hash 写为 #picks", w.location.hash === "#picks", w.location.hash);

  click(w, $("tabCal"));
  ok("切回日历页", hiddenOf(doc, "pgCal") === false && hiddenOf(doc, "pgPicks") === true);
  ok("hash 更新为 #calendar", w.location.hash === "#calendar", w.location.hash);
  // 2026-10-06 起首屏固定主页，不再用 localStorage 记忆「上次看到哪页」：
  // 手机上带着上次的 picks 记忆值打开，第一眼不是主页，用户会以为页卡丢了。
  ok("不再写 localStorage（首屏恒定落在主页）",
     w.localStorage.getItem(LSKEY) === null, String(w.localStorage.getItem(LSKEY)));
}

/* ================= 3. 分页状态保持（三种进入方式） ================= */
console.log("\n[3] 分页状态保持");
{
  // 3a. 带 #picks 深链直接打开
  const a = boot({ url: "https://jasonling110-a11y.github.io/profit-gap/home.html#picks" });
  ok("深链 #picks 打开即停在选股平台",
     hiddenOf(a.doc, "pgPicks") === false && hiddenOf(a.doc, "pgCal") === true);

  // 3a2. 带 #indices 深链直接打开，且此时才拉 iframe
  const a2 = boot({ url: "https://jasonling110-a11y.github.io/profit-gap/home.html#indices" });
  ok("深链 #indices 打开即停在指数看盘",
     hiddenOf(a2.doc, "pgIdx") === false && hiddenOf(a2.doc, "pgCal") === true);
  ok("深链 #indices 时才写 iframe src",
     /^https:\/\/global-market-dashboard-68975\.app\.workbuddy\.host\//.test(
       attrOf(a2.doc, "idxFrame", "src") || ""));

  // 3b. 无 hash，即使残留了「上次看到 picks」的记忆值，也必须落在主页
  //     （2026-10-06 用户明确要求「主页设置为投资日历」；旧版本会恢复到 picks）
  const b = boot({
    beforeParse(win) { try { win.localStorage.setItem(LSKEY, "picks"); } catch (e) {} },
  });
  ok("无 hash 时无视 localStorage 残留，仍落在主页「投资日历」",
     hiddenOf(b.doc, "pgCal") === false && hiddenOf(b.doc, "pgPicks") === true,
     "localStorage=" + b.window.localStorage.getItem(LSKEY));

  // 3c. 有 hash 时一律听 hash
  const c = boot({
    url: "https://jasonling110-a11y.github.io/profit-gap/home.html#indices",
    beforeParse(win) { try { win.localStorage.setItem(LSKEY, "picks"); } catch (e) {} },
  });
  ok("hash 优先于 localStorage（#indices 覆盖记忆值）",
     hiddenOf(c.doc, "pgIdx") === false &&
     hiddenOf(c.doc, "pgCal") === true && hiddenOf(c.doc, "pgPicks") === true);

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
  ok("每行 7 个单元格", dataTrs.every(t => t.children.length === 7));
  /* 连续断层期数列（第 4 格）：三种形态必须齐全才算真的接上了数据 ——
     「N 期」= 连续 N 期达标 / 「0」= 有历史数据但本期不达标 / 「—」= 历史财报缺失。
     只断言「有内容」是不够的：整列渲染成「—」也能通过。 */
  {
    const cells = dataTrs.map(t => t.children[3]).filter(Boolean);
    ok("连续断层列有「N 期」取值", cells.some(c => /\d+\s*期/.test(c.textContent)),
       cells.filter(c => /\d+\s*期/.test(c.textContent)).length + " 只");
    ok("连续断层列含「≥2 期」的个股（该指标本身有区分度）",
       cells.some(c => /([2-9]|\d\d)\s*期/.test(c.textContent)));
    ok("连续断层列三种形态可分辨（N 期 / 0 / —）",
       cells.every(c => /^(\d+\s*期|0|—)$/.test(c.textContent.trim())),
       Array.from(new Set(cells.map(c => c.textContent.trim()))).slice(0, 6).join(" / "));
    ok("连续断层列有 data-label（窄屏兜底）", cells.every(c => c.dataset.label === "连续断层"));
    ok("汇总行含「连续断层 ≥2 期」计数",
       /连续断层\s*≥2\s*期/.test(doc.getElementById("pSum").textContent));
  }
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
  // ---- 三页卡侧栏：桌面竖排 / 窄屏顶部横条（2026-10-06）----
  // 这一组是「反向断言」：谁要是把 .tabs 改回横排、或把窄屏那段删掉，
  // 用户报的「手机上找不到 3 个页卡按钮」就会复发，这里必须先红。
  ok("桌面布局是 侧栏 + 内容 两列网格",
     /\.shell\{display:grid;grid-template-columns:196px minmax\(0,1fr\)/.test(style));
  ok("桌面页卡竖排（.tabs 为 column）", /\.tabs\{[^}]*flex-direction:column/.test(style));
  ok("侧栏常驻（position:sticky）", /\.sidenav\{[^}]*position:sticky/.test(style));
  ok("≤900px 折叠为单列（侧栏不再占宽度，否则正文只剩 ~280px）",
     /@media\(max-width:900px\)\{[\s\S]*?\.shell\{grid-template-columns:minmax\(0,1fr\)/.test(style));
  ok("≤900px 侧栏转为顶部横条且三键等宽常驻可见",
     /@media\(max-width:900px\)\{[\s\S]*?\.sidenav\{[^}]*flex-direction:row/.test(style) &&
     /@media\(max-width:900px\)\{[\s\S]*?\.tabs\{flex-direction:row;flex:1/.test(style) &&
     /@media\(max-width:900px\)\{[\s\S]*?\.tab\{flex:1/.test(style));
  ok("≤900px 横条吸顶（top:0 + z-index）",
     /@media\(max-width:900px\)\{[\s\S]*?\.sidenav\{[^}]*top:0[^}]*z-index:30/.test(style));
  ok("外部模块 iframe 有确定高度（全屏应用内联会塌成 0）",
     /\.ext>iframe\{[^}]*height:min\(/.test(style));
  ok("外部模块加载遮罩有 on 态", /\.ext \.extload\{[\s\S]*?\}\s*\.ext \.extload\.on\{display:flex\}/.test(style) ||
     /\.ext\.extload\.on\{display:flex\}/.test(style) || /\.extload\.on\{display:flex\}/.test(style));
  // 工具栏已整排删除（2026-10-06 用户要求），相关 CSS 一并清理 —— 谁把 .extops/.viewsw 写回来这里先红。
  ok("工具栏相关 CSS 已清理（.extops / .viewsw / .hint 不再存在）",
     !/\.extops\{/.test(style) && !/\.viewsw\{/.test(style) && !/\.extops \.hint\{/.test(style));
  // 加载遮罩现在是「点一下重试」的隐形兜底，必须可点（cursor:pointer 提示可交互）。
  ok("加载遮罩可点（cursor:pointer，重试兜底不占版面）",
     /\.ext \.extload\{[^}]*cursor:pointer/.test(style));
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

/* ================= 11. 工具栏删除后的行为兜底 =================
   2026-10-06 二次要求：把三个页卡上的「完整日历/工作台月历/完整看板/工作台清单/
   新窗口打开/重新加载」整排按钮全删，页面只留内嵌完整应用。
   按钮没了不等于没行为 —— 这一节盯住三件事：
     a) 首屏仍只写**当前页卡**的 iframe src（另外两个保持懒加载）；
     b) 「重新加载」按钮删掉后，重试能力收进加载遮罩：点遮罩 = 带 _r= 强刷（隐形兜底）；
     c) 自建月历 / 选股表节点仍保留（用户只要求删按钮，没要求删视图）。
   注意 b)：jsdom 不发 load 事件，遮罩会一直显示 —— 正好用它来验证「点一下重试」。 */
console.log("\n[11] 工具栏删除后的行为兜底");
{
  const { window: w, doc } = boot();
  const $ = (id) => doc.getElementById(id);
  const srcOf = (id) => attrOf(doc, id, "src");

  ok("首屏只写当前页卡的 iframe src（日历已拉，看板还没）",
     /^https:\/\/market-calendar-71280\.app\.workbuddy\.host\//.test(srcOf("calFrame") || "") &&
     !srcOf("pkFrame"),
     "calFrame=" + srcOf("calFrame") + " / pkFrame=" + srcOf("pkFrame"));

  // --- 切到利润断层页：懒加载仍然生效（没有按钮也不该提前拉） ---
  click(w, $("tabPk"));
  ok("切到利润断层页才写 pkFrame 的 src（懒加载不受工具栏删除影响）",
     srcOf("pkFrame") === "利润断层工作台.html", srcOf("pkFrame"));

  // --- 遮罩点一下 = 带时间戳强刷（「重新加载」的隐形替代） ---
  const probe = (id) => {
    const f = $(id); if (!f) return { n: () => -1, restore: () => {} };
    let n = 0;
    const orig = f.setAttribute.bind(f);
    f.setAttribute = function (a, v) { if (a === "src") n++; return orig(a, v); };
    return { n: () => n, restore: () => { f.setAttribute = orig; } };
  };
  const pkP = probe("pkFrame");
  click(w, $("pkLoad"));
  pkP.restore();
  ok("点看板加载遮罩 = 加时间戳强刷（绕缓存）",
     /^利润断层工作台\.html\?_r=\d+$/.test(srcOf("pkFrame") || ""), srcOf("pkFrame"));

  const calP = probe("calFrame");
  click(w, $("tabCal"));
  click(w, $("calLoad"));
  calP.restore();
  ok("点日历加载遮罩 = 加时间戳强刷",
     /^https:\/\/market-calendar-71280\.app\.workbuddy\.host\/\?_r=\d+$/.test(srcOf("calFrame") || ""),
     srcOf("calFrame"));

  // --- 三个遮罩都在，且文案带应用名（避免负向测试整块摘掉还全绿） ---
  ok("三个页卡各有加载遮罩，文案标明是哪个应用",
     !!$("calLoad") && !!$("idxLoad") && !!$("pkLoad") &&
     /完整日历/.test($("calLoad").textContent) &&
     /指数看盘/.test($("idxLoad").textContent) &&
     /完整看板/.test($("pkLoad").textContent),
     JSON.stringify($("calLoad").textContent) + " / " + JSON.stringify($("pkLoad").textContent));

  // --- 自建视图节点仍在（只删了按钮，视图本身保留在页内） ---
  ok("自建月历 / 选股表节点仍保留（hidden，无入口）",
     !!$("calIn") && !!$("pkIn") &&
     hiddenOf(doc, "calIn") === true && hiddenOf(doc, "pkIn") === true);
}

console.log("\n----------------------------");
console.log(`通过 ${pass} 项，失败 ${fail} 项`);
console.log(fail === 0 ? "✅ 个人投资工作台自检通过" : "❌ 存在失败项");
process.exit(fail === 0 ? 0 : 1);
