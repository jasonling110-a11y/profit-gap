/* 外部模块集成 · 专项自检（交易日历 + 指数看盘）
   用法：NODE_PATH=<含 jsdom 的 node_modules> node tools/check_calendar.js

   2026-10-06：覆盖层从「交易日历单模块」泛化为 MODS 注册表（多模块共用一套壳）。
   本次新增 [8][9] 两节专门测「指数看盘」与「模块互不串」——
   泛化最容易出的错不是新模块打不开，而是**换模块时标题/链接/iframe title 没跟着换**
   （页面写着「指数看盘」、iframe 里却是日历），所以那几条是重点。
*/
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

// 允许用 WB_HTML 指向另一份产物（负向测试要把倒退版指进来）；默认测真实产物。
const HTML = process.env.WB_HTML || path.join(__dirname, "..", "利润断层工作台.html");
const CAL_URL = "https://market-calendar-71280.app.workbuddy.host/";
const IDX_URL = "https://global-market-dashboard-68975.app.workbuddy.host/";

const html = fs.readFileSync(HTML, "utf-8");
const dom = new JSDOM(html, {
  runScripts: "dangerously",
  pretendToBeVisual: true,
  url: "https://jasonling110-a11y.github.io/profit-gap/",
  resources: undefined, // 不加载外部资源，iframe 不会真的去联网
});
const { window } = dom;
const doc = window.document;
const $ = (id) => doc.getElementById(id);

let pass = 0, fail = 0;
function ok(name, cond, extra) {
  if (cond) { pass++; console.log("  ✔ " + name); }
  else { fail++; console.log("  ✘ " + name + (extra !== undefined ? "  → " + extra : "")); }
}
/* 空安全访问器：负向测试会把「整个模块被摘掉」的产物喂进来，此时 $("tabIdx") 是 null。
   直接 .dispatchEvent / .getAttribute 会抛 TypeError 让脚本中途崩掉，
   结果只报出前几条失败 —— 剩下的断言根本没跑，等于没测。
   （2026-10-06 实测：摘掉模块时脚本崩在第 3 条，46 条断言里只报了 3 条。） */
const click = (id) => { const el = $(id); if (el) el.dispatchEvent(new window.MouseEvent("click", { bubbles: true })); };
const attr  = (id, a) => { const el = $(id); return el ? el.getAttribute(a) : null; };
const txt   = (id) => { const el = $(id); return el ? el.textContent : ""; };
const has   = (id, c) => { const el = $(id); return !!el && el.classList.contains(c); };

console.log("=== 外部模块集成自检（交易日历 + 指数看盘）===\n");

// ---------- 1. 静态结构 ----------
console.log("[1] 结构与可用性");
ok("存在模块切换 tabs", !!$("tabHome") && !!$("tabCal"));
ok("存在覆盖层 calShell", !!$("calShell"));
ok("存在 iframe calFrame", !!$("calFrame"));
ok("存在加载态 / 失败兜底", !!$("calLoad") && !!$("calFb"));
ok("role=dialog + aria-modal", $("calShell").getAttribute("role") === "dialog"
   && $("calShell").getAttribute("aria-modal") === "true");
ok("iframe 有 title（无障碍）", !!$("calFrame").getAttribute("title"));
ok("iframe 有 sandbox（禁顶层跳转）",
   /allow-scripts/.test($("calFrame").getAttribute("sandbox") || "")
   && !/allow-top-navigation\b/.test(($("calFrame").getAttribute("sandbox") || "").replace("allow-popups-to-escape-sandbox","")));
ok("覆盖层 DOM 在主脚本之前（节点可被取到）",
   html.indexOf('id="calShell"') < html.indexOf('id="wb-payload"'));
ok("「新窗口打开」始终可达且 rel=noopener",
   ($("calNew") || {}).href === CAL_URL && /noopener/.test(($("calNew") || {}).rel || ""));
ok("iframe 初始无 src（不预加载、不影响本页）", !$("calFrame").getAttribute("src"));

// ---------- 2. 初始状态 ----------
console.log("\n[2] 初始状态");
ok("覆盖层默认关闭", !$("calShell").classList.contains("on"));
ok("默认选中「利润断层」", $("tabHome").getAttribute("aria-current") === "true");
ok("「交易日历」未选中", $("tabCal").getAttribute("aria-current") === "false");

// ---------- 3. 打开 ----------
console.log("\n[3] 点击「交易日历」");
$("tabCal").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
ok("覆盖层打开", $("calShell").classList.contains("on"));
ok("遮罩显示", $("calMask").classList.contains("on"));
ok("iframe src 指向日历站", $("calFrame").getAttribute("src") === CAL_URL,
   $("calFrame").getAttribute("src"));
ok("显示加载态", $("calLoad").classList.contains("on"));
ok("选中态切到「交易日历」", $("tabCal").getAttribute("aria-current") === "true"
   && $("tabHome").getAttribute("aria-current") === "false");
ok("锁定背景滚动", doc.body.style.overflow === "hidden");
ok("写入 #calendar 深链", window.location.hash === "#calendar", window.location.hash);

// ---------- 4. 失败兜底 ----------
console.log("\n[4] 网络异常兜底");
$("calFrame").dispatchEvent(new window.Event("error"));
ok("显示失败卡片", $("calFb").classList.contains("on"));
ok("隐藏加载态", !$("calLoad").classList.contains("on"));
ok("失败文案非空", (($("calFbMsg") || {}).textContent || "").length > 0);
ok("提供「重试」", !!$("calFbRetry"));
ok("兜底里也有「新窗口打开」", ($("calFbNew") || {}).href === CAL_URL);
ok("role=alert（读屏可感知）", $("calFb").getAttribute("role") === "alert");

// 重试应回到加载态
$("calFbRetry").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
ok("重试后回到加载态且不显示失败", $("calLoad").classList.contains("on")
   && !$("calFb").classList.contains("on"));

// ---------- 5. 关闭 ----------
console.log("\n[5] 关闭行为");
doc.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
ok("Esc 可关闭", !$("calShell").classList.contains("on"));
ok("恢复背景滚动", doc.body.style.overflow === "");
ok("关闭后摘掉 src（彻底停掉 iframe）", !$("calFrame").getAttribute("src"));
ok("清除 #calendar 深链", window.location.hash !== "#calendar", window.location.hash);
ok("选中态回到「利润断层」", $("tabHome").getAttribute("aria-current") === "true");

// 遮罩点击关闭
$("tabCal").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
$("calMask").dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
ok("点遮罩可关闭", !$("calShell").classList.contains("on"));

// ---------- 6. 深链直达 ----------
console.log("\n[6] #calendar 深链");
window.location.hash = "#calendar";
window.dispatchEvent(new window.HashChangeEvent("hashchange"));
ok("hash 变为 #calendar 后自动打开", $("calShell").classList.contains("on"));

// ---------- 7. 独立性 ----------
console.log("\n[7] 模块互不干扰");
ok("KPI 区块仍存在", !!$("kpis"));
ok("断层清单仍存在", !!$("tbl"));
ok("筛选工具条仍存在", !!$("q") && !!$("find"));
ok("K线弹窗仍在且默认关闭", !!$("modal") && !$("modal").classList.contains("on"));

// ---------- 8. 指数看盘模块 ----------
console.log("\n[8] 指数看盘模块");
ok("头部模块 tab 恰 3 个", doc.querySelectorAll(".hdr-tab").length === 3,
   doc.querySelectorAll(".hdr-tab").length);
ok("第三个 tab 文案是「指数看盘」", txt("tabIdx").trim() === "指数看盘");
ok("页面里两个外部站点 URL 都在（注册表齐备）",
   html.indexOf(CAL_URL) >= 0 && html.indexOf(IDX_URL) >= 0);

// 此刻正开着交易日历 → 直接点「指数看盘」，顺便测「开着的状态下换模块」
click("tabIdx");
ok("切到指数看盘：覆盖层仍开着", has("calShell", "on"));
ok("iframe src 已换成指数看盘站", attr("calFrame", "src") === IDX_URL, attr("calFrame", "src"));
/* 泛化最容易漏的一条：壳换了、文案没换 —— 页面标题写着「指数看盘」、
   里面却是日历，用户会以为点错了。标题必须同步且不能残留旧模块名。 */
ok("标题已换成「指数看盘」且不残留「交易日历」",
   /指数看盘/.test(txt("calTitle")) && !/交易日历/.test(txt("calTitle")), txt("calTitle"));
ok("覆盖层「新窗口」链接已换", attr("calNewBar", "href") === IDX_URL);
ok("兜底「在新窗口打开」链接已换", attr("calFbNew", "href") === IDX_URL);
ok("iframe title 已换（无障碍）", attr("calFrame", "title") === "指数看盘");
ok("加载文案已换", /正在加载指数看盘/.test(txt("calLoadMsg")), txt("calLoadMsg"));
ok("选中态只在「指数看盘」（其余两个都灭）",
   attr("tabIdx", "aria-current") === "true"
   && attr("tabCal", "aria-current") === "false"
   && attr("tabHome", "aria-current") === "false");
ok("深链换成 #indices", window.location.hash === "#indices", window.location.hash);

// 反向切换：确认不是只写了单向
click("tabCal");
ok("切回交易日历：src 换回日历站", attr("calFrame", "src") === CAL_URL, attr("calFrame", "src"));
ok("切回后标题不再出现「指数看盘」", !/指数看盘/.test(txt("calTitle")), txt("calTitle"));
ok("切回后深链是 #calendar", window.location.hash === "#calendar", window.location.hash);

// 刷新数据：必须带 cache-bust，否则浏览器可能直接吃缓存、读数根本不更新
click("tabIdx");
{
  const before = attr("calFrame", "src");
  ok("存在「刷新数据」按钮", !!$("calRefresh"));
  click("calRefresh");
  const after = attr("calFrame", "src");
  ok("刷新后 src 带 cache-bust 参数（绕过缓存）",
     after !== before && (after || "").indexOf("_r=") >= 0, after);
  ok("刷新后仍指向同一个站点（没串站）", (after || "").indexOf(IDX_URL) === 0, after);
}

// ---------- 9. 关闭复位与深链 ----------
console.log("\n[9] 关闭复位与深链");
doc.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
ok("Esc 可关闭", !has("calShell", "on"));
ok("关闭后摘掉 src（含 cache-bust 版本）", !attr("calFrame", "src"));
ok("关闭后三个 tab 全灭、回到「利润断层」",
   attr("tabHome", "aria-current") === "true"
   && attr("tabCal", "aria-current") === "false"
   && attr("tabIdx", "aria-current") === "false");
ok("关闭后清掉 #indices", window.location.hash !== "#indices", window.location.hash);

window.location.hash = "#indices";
window.dispatchEvent(new window.HashChangeEvent("hashchange"));
ok("#indices 深链直达指数看盘", has("calShell", "on")
   && attr("calFrame", "src") === IDX_URL
   && attr("tabIdx", "aria-current") === "true");

// 手工把地址栏改成非模块深链 → 应自动关闭，不把用户卡在覆盖层里
window.location.hash = "#nothing";
window.dispatchEvent(new window.HashChangeEvent("hashchange"));
ok("深链换成非模块值 → 自动关闭", !has("calShell", "on"));

console.log("\n----------------------------");
console.log(`通过 ${pass} 项，失败 ${fail} 项`);
console.log(fail === 0 ? "✅ 外部模块集成自检通过" : "❌ 存在失败项");
process.exit(fail === 0 ? 0 : 1);
