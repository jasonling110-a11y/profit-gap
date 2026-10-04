/* 交易日历集成 · 专项自检
   用法：NODE_PATH=<含 jsdom 的 node_modules> node tools/check_calendar.js
*/
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const HTML = path.join(__dirname, "..", "利润断层工作台.html");
const CAL_URL = "https://market-calendar-71280.app.workbuddy.host/";

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

console.log("=== 交易日历集成自检 ===\n");

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

console.log("\n----------------------------");
console.log(`通过 ${pass} 项，失败 ${fail} 项`);
console.log(fail === 0 ? "✅ 交易日历集成自检通过" : "❌ 存在失败项");
process.exit(fail === 0 ? 0 : 1);
