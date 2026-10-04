/**
 * 利润断层工作台 · 无头渲染自检
 * ================================
 * 用 jsdom 加载生成的 HTML，验证渲染结果与交互（无需浏览器）。
 *
 * 用法：
 *   NODE_PATH=/Users/jason/.workbuddy/binaries/node/workspace/node_modules \
 *   /Users/jason/.workbuddy/binaries/node/versions/22.22.2-3/bin/node tools/check_workbench.js [html路径]
 *
 * 通过标准：无运行时错误；清单行数 = summary.total；板块表行数 = sectors 数量；
 *           已剔除表行数 = summary.dropped_filled；点击行能打开含 K 线的弹窗；Esc 能关闭；
 *           点击板块能筛选清单；重置能恢复。
 */
const fs = require('fs');
const JSDOM_PATH = '/Users/jason/.workbuddy/binaries/node/workspace/node_modules/jsdom';
const { JSDOM, VirtualConsole } = require(JSDOM_PATH);
const file = process.argv[2] || '/Users/jason/Desktop/利润断层/利润断层工作台.html';

const html = fs.readFileSync(file, 'utf8');
const errs = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => errs.push('jsdomError: ' + e.message));
vc.on('error', e => errs.push('error: ' + e));
const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true, virtualConsole: vc });

setTimeout(() => {
  const d = dom.window.document, q = s => d.querySelector(s), qa = s => d.querySelectorAll(s);
  const out = {
    'KPI 卡数': qa('#kpis .kpi').length,
    'KPI 副标题数': qa('#kpis .kpi .d').length,
    '残留说明区块': ['#rules', '#listnote', '#qual', '#kpinote', '#secnote', '#cardnote', '#meta2']
      .filter(s => q(s)).join(',') || '无（已按用户要求全部移除）',
    '残留说明文案数': ['判定口径', '判定门槛', '数据质量与口径', '使用建议', '本清单把',
      '滚轮缩放 · 拖动看历史', 'K 线回溯']
      .filter(t => new RegExp(t).test(d.body.textContent)).length,
    '清单行数': qa('#tbl tbody tr').length,
    '清单表头列数': qa('#tbl thead th').length,
    '板块表行数': qa('#stbl tbody tr').length,
    '板块表列数': qa('#stbl thead th').length,
    '板块分布条数': qa('#sectorbars .bar').length,
    '行业下拉选项': qa('#find option').length,
    '已剔除区块': q('#dropbox') ? '仍存在' : '已彻底移除',
    '已剔除表': q('#dtbl') ? '仍存在' : '已彻底移除',
    'payload含dropped键': /"dropped"/.test(html) ? '是' : '否',
    '明细卡数': qa('#cards .card').length,
    '散点气泡': qa('#scatter circle').length,
    '散点气泡(可点击)': qa('#scatter circle.pt[data-code]').length,
    '散点图例项': qa('#scatter .sclegend span').length,
    // 气泡半径（成交额平方根映射）。用户 2026-10-04 反馈「太大了」，需锁住上界防回弹
    '气泡半径范围': (() => {
      const rs = Array.from(qa('#scatter circle.pt')).map(c => parseFloat(c.getAttribute('r'))).filter(n => !isNaN(n));
      return rs.length ? [Math.min.apply(null, rs).toFixed(1), Math.max.apply(null, rs).toFixed(1)] : [];
    })(),
    '计数文案': q('#cnt').textContent,
    '地标 main': q('main') ? '有' : '无',
    '地标 nav': q('nav.tools') ? '有' : '无',
    '跳转链接': q('a.skip') ? '有' : '无',
    '折叠区块数': qa('details').length,
    '表头可聚焦数': qa('#tbl thead th[tabindex="0"]').length,
    '表头不可排序列': qa('#tbl thead th.ns').length,
    '初始排序语义': (q('#tbl thead th[aria-sort]') || {}).dataset ? q('#tbl thead th[aria-sort]').dataset.k + '=' + q('#tbl thead th[aria-sort]').getAttribute('aria-sort') : '无',
    '表格 caption 数': qa('table caption').length,
    'scope=col 数': qa('th[scope="col"]').length,
    'CSS color-scheme': /color-scheme:dark/.test(html) ? '有' : '无',
    'CSS reduced-motion': /prefers-reduced-motion/.test(html) ? '有' : '无',
    'payload 走 JSON.parse': /JSON\.parse\(document\.getElementById\("wb-payload"\)/.test(html) ? '是' : '否',
    'payload 内已转义 <': /\\u003c/.test(html) ? '是' : '否',
  };
  // 连续断层期数列
  const si = Array.from(qa('#tbl thead th')).findIndex(t => t.dataset.k === 'streak');
  out['连续期数列序号'] = si;
  const svals = Array.from(qa('#tbl tbody tr')).map(tr => ((tr.children[si] || {}).textContent || '').trim());
  out['连续期数取值(去重)'] = Array.from(new Set(svals)).sort();
  out['连续期数合法'] = si >= 0 && svals.every(v => v === '—' || v === '0' || /^\d+ 期$/.test(v));
  out['连续期数非零条数'] = svals.filter(v => /^\d+ 期$/.test(v)).length;
  const row = q('#tbl tbody tr');
  if (row) {
    row.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    out['弹窗已打开'] = q('#modal').classList.contains('on');
    out['弹窗标题'] = (q('#mTitle').textContent || '').slice(0, 24);
    out['弹窗指标格数'] = qa('#mMetrics > div').length;
    out['K线图形元素'] = qa('#mChart rect').length;
    out['均线路径数'] = qa('#mChart path').length;
    out['图例项'] = qa('#mLegend span').length;
    d.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    out['Esc 已关闭'] = !q('#modal').classList.contains('on');
  } else {
    out['弹窗已打开'] = '无行可点';
  }
  const bar = q('#sectorbars .bar');
  if (bar) {
    bar.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    out['板块点击筛选值'] = q('#find').value;
    out['筛选后行数'] = qa('#tbl tbody tr').length;
    q('#reset').dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    out['重置后行数'] = qa('#tbl tbody tr').length;
  }

  // ---- 散点图气泡：点一下应直接打开该股 K 线弹窗 ----
  const bubble = q('#scatter circle.pt[data-code]');
  if (bubble) {
    const want = bubble.getAttribute('data-code');
    out['气泡点击_目标代码'] = want;
    bubble.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    out['气泡点击_弹窗已打开'] = q('#modal').classList.contains('on');
    out['气泡点击_标题含该代码'] = (q('#mTitle').textContent || '').indexOf(want) >= 0;
    out['气泡点击_已画出K线'] = qa('#mChart rect').length > 0;
    d.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    out['气泡点击_Esc已关闭'] = !q('#modal').classList.contains('on');
  } else {
    out['气泡点击'] = '无气泡可点';
  }

  // 清单必须只含「有效跳空」个股：缺口列不得出现「未跳空」或「—」
  const fillIdx = Array.from(qa('#tbl thead th')).findIndex(t => t.dataset.k === 'fill');
  const fillVals = Array.from(qa('#tbl tbody tr')).map(tr => ((tr.children[fillIdx] || {}).textContent || '').trim());
  out['缺口列取值'] = Array.from(new Set(fillVals)).sort();
  out['缺口列取值计数'] = fillVals.reduce((m, v) => { m[v] = (m[v] || 0) + 1; return m; }, {});

  // 弹窗内「上一个 / 下一个」翻页（含键盘 ↑ / ↓）
  const codeOf = () => ((q('#mTitle .code') || {}).textContent || '').trim().slice(0, 6);
  const trs = qa('#tbl tbody tr');
  if (trs.length >= 2) {
    trs[0].dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    const nav0 = { 代码: codeOf(), 位置: q('#mPos').textContent, 上一个禁用: q('#mPrev').disabled, 下一个禁用: q('#mNext').disabled, 行1代码: trs[0].dataset.code };
    q('#mNext').click();
    const nav1 = { 代码: codeOf(), 位置: q('#mPos').textContent, 行2代码: trs[1].dataset.code };
    q('#mPrev').click();
    const navBack = { 代码: codeOf(), 位置: q('#mPos').textContent };
    d.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    const navKeyDown = { 代码: codeOf(), 位置: q('#mPos').textContent };
    d.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true }));
    const navKeyUp = { 代码: codeOf(), 位置: q('#mPos').textContent };
    out['弹窗翻页'] = { 起始: nav0, 下一个: nav1, 回退: navBack, 键盘下: navKeyDown, 键盘上: navKeyUp };
    d.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  }

  // 表头排序：点击列头 → 降序；再次点击 → 升序
  const headK = k => {
    const ths = Array.from(qa('#tbl thead th'));
    return { th: q("#tbl thead th[data-k='" + k + "']"), idx: ths.findIndex(t => t.dataset.k === k) };
  };
  const colTop = (k, n) => {
    const { idx } = headK(k);
    return Array.from(qa('#tbl tbody tr')).slice(0, n)
      .map(tr => parseFloat((tr.children[idx] || {}).textContent));
  };
  const clickHead = k => {
    const { th } = headK(k);
    if (th) th.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    return th;
  };
  const sorts = {};
  [['price', '最新价'], ['growth', '增速'], ['daychg', '当日涨幅'], ['accel', '加速度'], ['streak', '连续期数']].forEach(([k, label]) => {
    const th = clickHead(k);
    if (!th) return;
    const desc = colTop(k, 5);
    clickHead(k);
    const asc = colTop(k, 5);
    sorts[label] = { desc: desc, asc: asc, ascFlag: th.classList.contains('asc'), 下拉同步: q('#fsort').value };
  });
  out['表头排序'] = sorts;
  out['表头列数'] = qa('#tbl thead th').length;

  // 表头键盘可达：聚焦后按 Enter 应切换排序并同步 aria-sort
  const kth = q("#tbl thead th[data-k='score']");
  if (kth) {
    const before = kth.getAttribute('aria-sort');
    kth.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    out['键盘排序'] = { 前: before, 后: kth.getAttribute('aria-sort'), 已切换: before !== kth.getAttribute('aria-sort'), 行数: qa('#tbl tbody tr').length };
  }
  out['不可排序列可聚焦'] = Array.from(qa('#tbl thead th.ns')).filter(t => t.hasAttribute('tabindex')).length;
  out['可排序表头数'] = qa('#tbl thead th:not(.ns)').length;

  // 连续断层期数在弹窗里应有序列条（挑一只确实有期数的个股）
  const siTxt = tr => (((tr.children[si] || {}).textContent) || '').trim();
  const streakRow = Array.from(qa('#tbl tbody tr')).find(tr => /^\d+ 期$/.test(siTxt(tr)));
  if (streakRow) {
    streakRow.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    out['弹窗指标格数'] = qa('#mMetrics > div').length;
    out['弹窗序列条'] = qa('#mStreak .streakline .cell').length;
    out['弹窗标题'] = (q('#mTitle').textContent || '').slice(0, 24);
    d.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  }

  // ---- K 线回顾区间：连续断层个股应拿到更长历史，区间切换可用 ----
  // 只数蜡烛影线（data-wick）。历史断层虚线也是 <line stroke-width="1">，
  // 若按 stroke-width 统计，多期断层个股的根数会凭空多出几根。
  const wickCount = () => qa('#mChart svg line[data-wick]').length;
  const streakRows = Array.from(qa('#tbl tbody tr'))
    .map(tr => ({ tr, n: parseInt((siTxt(tr).match(/^(\d+) 期$/) || [])[1], 10) }))
    .filter(x => x.n > 0)
    .sort((a, b) => b.n - a.n);
  if (streakRows.length) {
    out['最长连续期数(清单)'] = streakRows[0].n;
    streakRows[0].tr.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    const rb = qa('#mRange button[data-win]');
    const mrn = ((q('#mRange .mrn') || {}).textContent || '').replace(/\s+/g, ' ').trim();
    const m = /共 (\d+) 个交易日/.exec(mrn);
    out['K线区间按钮数'] = rb.length;
    out['K线区间可用交易日'] = m ? parseInt(m[1], 10) : -1;
    out['K线默认根数'] = wickCount();
    out['K线区间按压态数'] = Array.from(rb).filter(b => b.getAttribute('aria-pressed') === 'true').length;
    const pressed = Array.from(rb).filter(b => b.getAttribute('aria-pressed') === 'true')[0];
    out['K线默认按压项'] = pressed ? pressed.getAttribute('data-win') : null;
    out['K线默认位置'] = mrn.slice(0, 70);
    // 默认视窗必须已经覆盖到历史各期断层，否则用户打开图只看到最近一段，等于没标
    out['默认视图历史期标签数'] = Array.from(qa('#mChart svg text'))
      .filter(t => /^(≈)?\d{2}(一季报|半年报|三季报|年报)/.test((t.textContent || '').trim())).length;
    const clickWin = w => {                       // 每次重绘后 #mRange 的按钮都是新节点，必须重新查询
      const b = qa('#mRange button[data-win="' + w + '"]')[0];
      if (b && !b.disabled) b.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
      return !!b;
    };
    if (clickWin(120)) {
      out['K线切换后按压'] = (q('#mRange button[data-win="120"]') || {}).getAttribute('aria-pressed');
      out['K线切换后根数'] = wickCount();
      clickWin(0);
      out['K线还原后根数'] = wickCount();
      clickWin(120);
      out['K线复位后根数'] = wickCount();
    }
    d.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  }

  // ---- 同花顺式交互：滚轮缩放 / 拖动看历史 / 双击回到最新 ----
  const posTxt = () => (((q('#mRange .mrn') || {}).textContent) || '').replace(/\s+/g, ' ').trim();
  const posEnd = () => { const m = /第 \d+–(\d+) \//.exec(posTxt()); return m ? parseInt(m[1], 10) : -1; };
  const latestBtn = () => q('#mRange button[data-act="latest"]');
  const zoomBtn = a => q('#mRange button[data-act="' + a + '"]');
  const cb = d.getElementById('chartbox');
  const ptr = (type, x) => {
    const ev = new dom.window.MouseEvent(type, { bubbles: true, clientX: x, clientY: 200 });
    try { Object.defineProperty(ev, 'pointerId', { value: 1, configurable: true }); } catch (_) {}
    cb.dispatchEvent(ev);
  };
  if (streakRows && streakRows.length && cb) {
    out['区间默认位置'] = posTxt();
    // 先把窗口切到「全部」再测交互，得到确定的起点
    const bAll2 = qa('#mRange button[data-win="0"]')[0];
    if (bAll2) bAll2.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    const full = wickCount();
    out['全览根数'] = full;
    out['区间完整位置'] = posTxt();
    out['K线区间可用交易日'] = (() => { const m = /共 (\d+) 个交易日/.exec(posTxt()); return m ? parseInt(m[1], 10) : -1; })();
    out['全览历史期标签数'] = Array.from(qa('#mChart svg text'))
      .filter(t => /^(≈)?\d{2}(一季报|半年报|三季报|年报)/.test((t.textContent || '').trim())).length;
    out['全览历史期清单条数'] = Array.from(qa('#mHist .histline .cell')).length;
    if (typeof dom.window.WheelEvent === 'function') {
      const wh = dy => cb.dispatchEvent(new dom.window.WheelEvent('wheel', { bubbles: true, cancelable: true, deltaY: dy, clientX: 400 }));
      wh(-120);                                  // 向上滚 = 放大 = 可见根数变少
      out['滚轮放大后根数'] = wickCount();
      out['滚轮放大后出现回到最新'] = !!latestBtn();
      wh(120); wh(120);                          // 向下滚 = 缩小 = 根数变多（到顶即全览）
      out['滚轮缩小后根数'] = wickCount();
    }
    // 放大按钮 / 缩小按钮
    if (zoomBtn('zoomin')) {
      zoomBtn('zoomin').dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
      out['按钮放大后根数'] = wickCount();
    }
    // 回到最新
    if (latestBtn()) {
      latestBtn().dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
      out['回到最新_点击后仍存在'] = !!latestBtn();
      out['回到最新_根数'] = wickCount();
    }
    // 拖动平移：往右拖 = 看更早的历史
    const endBefore = posEnd();
    ptr('pointerdown', 400); ptr('pointermove', 520); ptr('pointerup', 520);
    out['拖动前右端'] = endBefore;
    out['拖动后右端'] = posEnd();
    out['拖动后位置'] = posTxt().slice(0, 46);
    out['拖动后出现回到最新'] = !!latestBtn();
    out['拖动后数据仍在'] = wickCount();
    // 双击 = 回到最新
    cb.dispatchEvent(new dom.window.MouseEvent('dblclick', { bubbles: true, cancelable: true }));
    out['双击后右端'] = posEnd();
    out['双击后根数'] = wickCount();
    d.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  }

  // ---- 数据侧：历史各期断层（period_gaps）----
  const bad = [];
  const shortOf = lab => String(lab || '').replace(/^\d{2}(\d{2})年/, '$1');
  let PAY = null;
  try { PAY = JSON.parse(d.getElementById('wb-payload').textContent); } catch (_) {}
  const cands = (PAY && PAY.candidates) || [];
  out['候选数(payload)'] = cands.length;
  out['含多期断层个股'] = cands.filter(r => (r.period_gaps || []).length >= 2).length;
  out['多期有效跳空合计'] = cands.reduce((s, r) => s + (r.period_gaps || []).filter(x => x.valid).length, 0);
  out['长期历史最长'] = cands.reduce((s, r) => Math.max(s, (r.kline_days || 0)), 0);
  const pgSample = cands.filter(r => (r.period_gaps || []).length >= 2)[0];
  if (pgSample) {
    out['多期样例'] = pgSample.name + ' ' + (pgSample.period_gaps || [])
      .map(x => shortOf(x.label) + (x.valid ? '(跳' + x.gap_pct + '%)' : '(未跳空)')).join(' ');
  }
  const badPg = cands.filter(r => (r.period_gaps || []).some(x => x.valid && !x.gap_date));
  if (badPg.length) bad.push(badPg.length + ' 只个股的有效跳空期次缺 gap_date');
  // 历史期公告日合理性：数据源的「最新公告日期」会被后续公告刷新，必须被引擎拦住
  const bounds = per => {
    const y = +per.slice(0, 4), m = +per.slice(4, 6), dd = +per.slice(6, 8);
    const e = Date.UTC(y, m - 1, dd);
    return [e - 20 * 864e5, e + 200 * 864e5];
  };
  const badAnn = [];
  cands.forEach(r => (r.period_gaps || []).forEach(x => {
    if (!x.ann) return;
    const t = Date.parse(x.ann + 'T00:00:00Z'), b = bounds(x.period);
    if (t < b[0] || t > b[1]) badAnn.push(r.code + ' ' + x.label + ' ' + x.ann);
  }));
  out['公告日越界期次'] = badAnn.length;
  if (badAnn.length) bad.push(badAnn.length + ' 条历史期公告日越界（前 3：' + badAnn.slice(0, 3).join('; ') + '）');

  // ---- 清单混排：业绩预告 / 业绩快报 / 正式财报 合到同一张表，用「类型」列区分 ----
  const pre = (PAY && PAY.pre_pool) || [];
  const RANK = { "业绩预告": 0, "业绩快报": 1, "正式财报": 2 };
  const kindRank = k => RANK[k] === undefined ? 9 : RANK[k];
  out['预告(payload)'] = pre.length;
  out['预告_尚未跳空'] = pre.filter(r => r.gap_state === '尚未跳空').length;
  out['预告_已回补'] = pre.filter(r => r.gap_state === '已回补').length;
  out['预告_口径豁免'] = pre.filter(r => r.pre_tier === '口径豁免').length;
  out['清单合计(payload)'] = cands.length + pre.length;

  const mainCodes = new Set(cands.map(r => r.code));
  const dup = pre.filter(r => mainCodes.has(r.code));
  if (dup.length) bad.push(dup.length + ' 只个股同时出现在主清单与预告清单：' + dup.map(r => r.code).join(','));
  const badPre = pre.filter(r => r.source !== '业绩预告' || !r.profit_gap);
  if (badPre.length) bad.push(badPre.length + ' 只预告个股来源不是业绩预告或利润断层未成立');
  if (pre.length && (out['预告_尚未跳空'] + out['预告_已回补'] !== pre.length)) {
    bad.push('预告行的 gap_state 取值出现第三种（应只有「尚未跳空 / 已回补」）');
  }

  // 旧的独立「预告池」区块必须彻底消失（已并入主清单）
  out['旧预告池区块(#pre)'] = d.getElementById('pre') ? '仍存在' : '已彻底移除';
  out['旧预告池表(#ptbl)'] = q('#ptbl') ? '仍存在' : '已彻底移除';
  out['旧预告池表行数'] = qa('#ptbl tbody tr').length;
  if (out['旧预告池区块(#pre)'] !== '已彻底移除') bad.push('独立预告池区块 #pre 仍在页面上（应与主清单合并）');
  if (out['旧预告池表(#ptbl)'] !== '已彻底移除') bad.push('独立预告池表 #ptbl 仍在页面上');

  // DOM 行数必须等于 payload 两段之和
  const trAll = Array.from(qa('#tbl tbody tr'));
  out['清单行数'] = trAll.length;
  if (trAll.length !== out['清单合计(payload)']) {
    bad.push('清单 DOM 行数（' + trAll.length + '）与 payload 合计（' + out['清单合计(payload)'] +
      ' = ' + cands.length + '+' + pre.length + '）不一致');
  }

  // 「类型」列：取值必须是 预告 / 快报 / 财报；行内 data-kind 决定分类，两者必须一致
  const kindIdx = Array.from(qa('#tbl thead th')).findIndex(t => t.dataset.k === 'source');
  out['类型列序号'] = kindIdx;
  const legalKinds = new Set(['业绩预告', '业绩快报', '正式财报']);
  out['类型列取值'] = Array.from(new Set(trAll.map(tr => ((tr.children[kindIdx] || {}).textContent || '').trim()))).sort();
  out['类型列行分布'] = trAll.reduce((m, tr) => { const s = tr.dataset.kind || '(空)'; m[s] = (m[s] || 0) + 1; return m; }, {});
  if (kindIdx < 0) bad.push('清单缺少「类型」列');
  const badKind = trAll.filter(tr => !legalKinds.has(tr.dataset.kind));
  if (badKind.length) bad.push(badKind.length + ' 行的类型不在 {业绩预告/业绩快报/正式财报} 内：' +
    badKind.slice(0, 3).map(t => t.dataset.kind || '(空)').join(','));
  if ((out['类型列行分布']['业绩预告'] || 0) !== pre.length) {
    bad.push('清单里「业绩预告」行数（' + (out['类型列行分布']['业绩预告'] || 0) +
      '）与 payload 预告数（' + pre.length + '）不一致');
  }
  // 每行的类型短标签必须与 data-kind 对应（预告 / 快报 / 财报）
  const SHORT = { "业绩预告": "预告", "业绩快报": "快报", "正式财报": "财报" };
  if (kindIdx >= 0) {
    const mismatch = trAll.filter(tr => {
      const cell = ((tr.children[kindIdx] || {}).textContent || '').trim();
      return SHORT[tr.dataset.kind] !== cell;
    });
    if (mismatch.length) bad.push(mismatch.length + ' 行的「类型」列文案与行分类不符（前 3：' +
      mismatch.slice(0, 3).map(t => (t.dataset.kind || '?') + '→' + (((t.children[kindIdx] || {}).textContent) || '').trim()).join('; ') + '）');
  }

  // 缺口列与类型必须自洽：财报 / 快报只能是 未回补|已回补；预告可以是 尚未跳空|已回补
  const fillIdx2 = Array.from(qa('#tbl thead th')).findIndex(t => t.dataset.k === 'fill');
  const fillByKind = { "业绩预告": [], "业绩快报": [], "正式财报": [] };
  trAll.forEach(tr => {
    const v = ((tr.children[fillIdx2] || {}).textContent || '').trim();
    if (fillByKind[tr.dataset.kind]) fillByKind[tr.dataset.kind].push(v);
  });
  out['预告行缺口列取值'] = Array.from(new Set(fillByKind['业绩预告'])).sort();
  out['财报行缺口列取值'] = Array.from(new Set(fillByKind['正式财报'])).sort();
  fillByKind['业绩预告'].forEach(v => {
    if (v !== '尚未跳空' && v !== '已回补') bad.push('业绩预告行的缺口列出现 "' + v + '"（应只有 尚未跳空/已回补）');
  });
  fillByKind['正式财报'].forEach(v => {
    if (v !== '未回补' && v !== '已回补') bad.push('正式财报行的缺口列出现 "' + v + '"（应只有 未回补/已回补）');
  });

  // 「类型」列排序：预告(0) → 快报(1) → 财报(2) 必须单调
  const clickTypeHead = () => {
    const th = q("#tbl thead th[data-k='source']");
    if (th) th.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
    return !!th;
  };
  const seqRows = () => Array.from(qa('#tbl tbody tr')).map(tr => kindRank(tr.dataset.kind));
  if (kindIdx >= 0) {
    clickTypeHead();                      // 第 1 击 = 降序：财报 → 快报 → 预告
    const seqDesc = seqRows();
    clickTypeHead();                      // 第 2 击 = 升序：预告 → 快报 → 财报
    const seqAsc = seqRows();
    const isMono = (a, dir) => a.every((v, i) => i === 0 || (dir === 'desc' ? a[i - 1] >= v : a[i - 1] <= v));
    out['类型列排序'] = {
      降序前缀: seqDesc.slice(0, 6).join(''),
      升序前缀: seqAsc.slice(0, 6).join(''),
      降序单调: isMono(seqDesc, 'desc'),
      升序单调: isMono(seqAsc, 'asc'),
    };
    if (!isMono(seqDesc, 'desc')) bad.push('「类型」列降序未按 财报→快报→预告 排列');
    if (!isMono(seqAsc, 'asc')) bad.push('「类型」列升序未按 预告→快报→财报 排列');
    // 恢复默认：按评分
    const sc = q("#tbl thead th[data-k='score']");
    if (sc) sc.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true }));
  }

  // 「来源」下拉：条数必须与混排后的清单（candidates + pre_pool）对得上，并且实际筛得出来
  const fsrc = qa('#fsrc option');
  out['来源筛选项数'] = fsrc.length;
  out['来源筛选文案'] = Array.from(fsrc).map(o => o.textContent).join(' | ');
  out['来源筛选条数与清单对账'] = (() => {
    const want = {};
    cands.concat(pre).forEach(r => { want[r.source] = (want[r.source] || 0) + 1; });
    return Array.from(fsrc).slice(1).map(o => (want[o.value] || 0)).join(',');
  })();
  const fsrcSel = d.getElementById('fsrc');
  if (fsrcSel) {
    // 无结果时 render() 会插入一行 .empty-row 占位，统计时必须剔除
    const realRows = () => Array.from(qa('#tbl tbody tr')).filter(tr => !tr.classList.contains('empty-row')).length;
    const per = {};
    Array.from(fsrcSel.options).slice(1).forEach(o => {
      fsrcSel.value = o.value;
      fsrcSel.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
      per[o.value] = realRows();
    });
    fsrcSel.value = '';
    fsrcSel.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
    out['来源筛选实测行数'] = per;
    Array.from(fsrcSel.options).slice(1).forEach(o => {
      if (per[o.value] !== (out['类型列行分布'][o.value] || 0)) {
        bad.push('来源筛选「' + o.value + '」实测 ' + per[o.value] + ' 行，与清单分布 ' +
          (out['类型列行分布'][o.value] || 0) + ' 不符');
      }
    });
    if (realRows() !== trAll.length) bad.push('来源筛选归零后清单行数未复原（' + realRows() + ' vs ' + trAll.length + '）');
  }

  // 分层（tier）：v1.12 起利润侧不设门槛，tier 只是「描述性标签」，不再淘汰任何个股。
  // 三档之和必须等于清单行数，且清单里绝不能出现「剔除」——只要有跳空就该被列出来。
  const tiIdx = Array.from(qa('#tbl thead th')).findIndex(t => t.dataset.k === 'tier');
  out['分层列序号'] = tiIdx;
  if (tiIdx >= 0) {
    const tierCount = {};
    trAll.forEach(tr => {
      const v = ((tr.children[tiIdx] || {}).textContent || '').trim();
      tierCount[v] = (tierCount[v] || 0) + 1;
    });
    out['分层分布'] = tierCount;
    const tierSum = Object.keys(tierCount).reduce((a, k) => a + tierCount[k], 0);
    if (tierSum !== trAll.length) bad.push('分层分布合计（' + tierSum + '）与清单行数（' + trAll.length + '）不一致');
    if (tierCount['剔除']) bad.push('清单里出现了「剔除」层级的行（' + tierCount['剔除'] + ' 行）——有跳空就不该被淘汰');
    ['核心池·双断层', '观察池·低基数断层', '跟踪·仅价格缺口'].forEach(v => {
      if (tierCount[v] && !Object.prototype.hasOwnProperty.call(tierCount, v)) bad.push('分层取值异常：' + v);
    });
    Object.keys(tierCount).forEach(v => {
      if (['核心池·双断层', '观察池·低基数断层', '跟踪·仅价格缺口'].indexOf(v) < 0) {
        bad.push('出现未知层级："' + v + '"');
      }
    });
    if (!((tierCount['核心池·双断层'] || 0) > 0)) bad.push('核心池为空，分层口径疑似被改坏');
  }

  // 预告个股的 K 线可用性：接口对次新股可能无日线（数据源边界，只报告不当失败）
  const missingK = pre.filter(r => !((PAY.kline || {}).data || {})[r.code]);
  out['预告_缺行情'] = missingK.map(r => r.code).join(',') || '无';
  if (missingK.length && missingK.length < pre.length) {
    console.log('提示：' + missingK.length + ' 只预告个股行情接口无返回（次新股/未上市），页面上已标「无行情」');
  }
  if (pre.length && missingK.length === pre.length) {
    bad.push('预告个股全部取不到行情，疑似阶段二 K 线未覆盖预告');
  }

  console.log(JSON.stringify(out, null, 1));
  console.log('运行时错误:', errs.length ? errs.slice(0, 5) : '无');
  if (errs.length) bad.push('存在运行时错误');
  if (out['清单行数'] === 0) bad.push('清单为空');
  if (out['已剔除区块'] !== '已彻底移除') bad.push('「已剔除：缺口回补个股」区块仍在页面上');
  if (out['已剔除表'] !== '已彻底移除') bad.push('已剔除表 #dtbl 仍在页面上');
  if (out['payload含dropped键'] !== '否') bad.push('payload 里仍带着 dropped 数据');
  // 缺口列只允许三种取值：正式财报/快报为 未回补|已回补；业绩预告可为 尚未跳空|已回补
  (out['缺口列取值'] || []).forEach(v => {
    if (v !== '未回补' && v !== '已回补' && v !== '尚未跳空') bad.push('清单缺口列出现非法取值："' + v + '"');
  });
  if (!/^共 \d+ 只$/.test((out['计数文案'] || '').trim())) bad.push('#cnt 计数文案异常：' + out['计数文案']);
  if (/缺口已回补|已剔除：缺口回补/.test(q('#tbl') ? q('#tbl').textContent : '')) bad.push('清单里仍出现「缺口已回补」文案');
  if (out['弹窗已打开'] !== true) bad.push('K 线弹窗未打开');
  if (!out['K线图形元素']) bad.push('K 线未绘制');
  // K 线可回溯深度：必须明显大于默认视窗（120 根），否则「往前拖不动」
  if (!(out['K线区间可用交易日'] > 200)) bad.push('K 线可用交易日过少（' + out['K线区间可用交易日'] + '），往前拖不动');
  if (!(out['含多期断层个股'] > 0)) bad.push('payload 里没有多期断层个股，历史断层无从验证');
  if (!(out['全览历史期标签数'] > 0)) bad.push('全览视图没有任何历史期标签，历史断层未画到图上');
  if (!(out['全览历史期清单条数'] > 0)) bad.push('弹窗缺少「历史各期断层」清单');
  const mono = (a, dir) => a.every((v, i) => i === 0 || isNaN(v) || isNaN(a[i - 1]) || (dir === 'desc' ? a[i - 1] >= v : a[i - 1] <= v));
  Object.keys(out['表头排序'] || {}).forEach(label => {
    const s = out['表头排序'][label];
    if (!mono(s.desc, 'desc')) bad.push(label + ' 降序排序异常');
    if (!mono(s.asc, 'asc')) bad.push(label + ' 升序排序异常');
    if (s.desc[0] !== undefined && s.asc[0] !== undefined && !isNaN(s.desc[0]) && !isNaN(s.asc[0]) && s.desc[0] < s.asc[0]) {
      bad.push(label + ' 升降序未翻转');
    }
  });
  const nav = out['弹窗翻页'];
  if (!nav) bad.push('弹窗翻页未测试');
  else {
    if (nav['起始']['代码'] !== nav['起始']['行1代码']) bad.push('翻页起始个股与首行不一致');
    if (!nav['起始']['上一个禁用']) bad.push('首条「上一个」按钮未禁用');
    if (nav['下一个']['代码'] !== nav['下一个']['行2代码']) bad.push('「下一个」未跳到第 2 行个股');
    if (nav['回退']['代码'] !== nav['起始']['代码']) bad.push('「上一个」未回到原个股');
    if (nav['键盘下']['代码'] !== nav['下一个']['代码']) bad.push('键盘 ↓ 翻页异常');
    if (nav['键盘上']['代码'] !== nav['起始']['代码']) bad.push('键盘 ↑ 翻页异常');
    if (!/^\d+ \/ \d+$/.test(nav['起始']['位置'] || '')) bad.push('翻页位置文案异常：' + nav['起始']['位置']);
  }
  // 缺失值必须恒排最后（否则按「最新价」升序会把无行情行顶到最前）
  ['最新价', '当日涨幅'].forEach(label => {
    const s = (out['表头排序'] || {})[label];
    if (!s) return;
    if (s.asc[0] === null || isNaN(s.asc[0])) bad.push(label + ' 升序时缺失值未沉底');
  });
  // ---- 本轮新增：信息层级 / 可访问性 / 连续断层期数 / 注入安全 ----
  if (out['KPI 卡数'] !== 3) bad.push('概览主指标应为 3 张，实际 ' + out['KPI 卡数']);
  // 用户已明确要求删掉页面上所有解释性文案
  if (out['KPI 副标题数'] !== 0) bad.push('KPI 卡仍带口径副标题 ' + out['KPI 副标题数'] + ' 个，解释文案未删净');
  if (out['残留说明区块'] !== '无（已按用户要求全部移除）') bad.push('仍残留说明区块：' + out['残留说明区块']);
  if (out['残留说明文案数'] !== 0) bad.push('页面仍残留解释文案（命中 ' + out['残留说明文案数'] + ' 类）');
  // 散点图：气泡必须可点击并真的能打开 K 线
  if (!(out['散点气泡(可点击)'] > 0)) bad.push('散点图没有可点击的气泡（circle.pt[data-code] 数量为 0）');
  if (!(out['散点图例项'] >= 7)) bad.push('散点图例不完整（强弱 4 档 + 分层 3 种，实际 ' + out['散点图例项'] + '）');
  // 气泡尺寸是用户调过的：上限锁 10（旧值 14 被用户嫌太大），下限锁 3（半径=点击热区，太小点不中）
  (() => {
    const br = out['气泡半径范围'];
    if (!br || !br.length) { bad.push('散点气泡没有半径'); return; }
    if (parseFloat(br[1]) > 10) bad.push('气泡半径过大（最大 ' + br[1] + '，上限 10；用户明确要求做小）');
    if (parseFloat(br[0]) < 3) bad.push('气泡半径过小（最小 ' + br[0] + '，下限 3，再小就点不中了）');
  })();
  if (out['气泡点击_弹窗已打开'] !== true) bad.push('点击散点气泡未打开 K 线弹窗');
  if (out['气泡点击_标题含该代码'] !== true) bad.push('气泡点击打开的弹窗不是被点的那只个股');
  if (out['气泡点击_已画出K线'] !== true) bad.push('气泡点击后 K 线未绘制');
  if (out['气泡点击_Esc已关闭'] !== true) bad.push('气泡打开的弹窗 Esc 关不掉');
  if (out['地标 main'] !== '有') bad.push('缺少 <main> 地标');
  if (out['地标 nav'] !== '有') bad.push('筛选区缺少 <nav> 地标');
  if (out['跳转链接'] !== '有') bad.push('缺少「跳到断层清单」skip link');
  if (out['折叠区块数'] !== 2) bad.push('板块全景 / 明细分卡 应为 2 个 <details>（判定口径区块已按用户要求删除），实际 ' + out['折叠区块数']);
  if (out['表头可聚焦数'] !== out['清单表头列数'] - 1) {
    bad.push('可排序表头未全部键盘可达（应 ' + (out['清单表头列数'] - 1) + ' 个，实际 ' + out['表头可聚焦数'] + '）');
  }
  if (out['表头不可排序列'] !== 1) bad.push('K线列应且仅应标记为 .ns（实际 ' + out['表头不可排序列'] + '）');
  if (!/^[a-z_]+=(ascending|descending)$/.test(out['初始排序语义'] || '')) bad.push('首屏表头缺少静态 aria-sort（' + out['初始排序语义'] + '）');
  if (out['不可排序列可聚焦'] !== 0) bad.push('不可排序的 K线列表头不应可聚焦');
  if (out['表格 caption 数'] < 2) bad.push('表格缺少 <caption>（实际 ' + out['表格 caption 数'] + '）');
  if (out['scope=col 数'] < out['清单表头列数']) bad.push('表头缺少 scope="col"（实际 ' + out['scope=col 数'] + '）');
  if (out['CSS color-scheme'] !== '有') bad.push('CSS 缺少 color-scheme:dark');
  if (out['CSS reduced-motion'] !== '有') bad.push('CSS 缺少 prefers-reduced-motion 支持');
  if (out['payload 走 JSON.parse'] !== '是') bad.push('数据未通过 JSON.parse 注入');
  if (out['payload 内已转义 <'] !== '是') bad.push('注入数据未转义 "<"，仍存在 </script> 截断白屏风险');
  if (out['连续期数列序号'] < 0) bad.push('清单缺少「连续期数」列');
  if (!out['连续期数合法']) bad.push('连续期数列取值非法：' + JSON.stringify(out['连续期数取值(去重)']));
  if (out['连续期数非零条数'] === 0) bad.push('连续期数列全部为 0 / —，疑似未取到数据');
  const kb = out['键盘排序'];
  if (!kb) bad.push('表头键盘排序未测试');
  else {
    if (!kb['已切换']) bad.push('表头按 Enter 未切换排序（aria-sort 未变）');
    if (kb['行数'] === 0) bad.push('键盘排序后清单为空');
  }
  if (out['弹窗序列条'] === 0) bad.push('弹窗未渲染单季同比序列条');
  if (out['弹窗指标格数'] !== undefined && out['弹窗指标格数'] < 11) bad.push('弹窗指标格数不足（应含「连续断层」格，实际 ' + out['弹窗指标格数'] + '）');

  // ---- K 线视窗：默认窗口 / 区间切换 / 按连续断层自动放宽 ----
  if (out['K线区间按钮数'] !== 4) bad.push('K 线回顾区间按钮应为 4 个，实际 ' + out['K线区间按钮数']);
  if (!(out['K线区间可用交易日'] > 0)) bad.push('K 线区间缺少「共 N 个交易日」文案');
  if (out['K线区间按压态数'] !== 1) bad.push('K 线区间同一时刻应恰有 1 个按钮被按下，实际 ' + out['K线区间按压态数']);
  if (!['0', '120', '250'].includes(out['K线默认按压项'])) {
    bad.push('默认视窗应停在某个标准档位（120 / 250 / 全部），实际 data-win=' + out['K线默认按压项']);
  }
  if (!(out['默认视图历史期标签数'] >= 2)) {
    bad.push('默认视窗只画出 ' + out['默认视图历史期标签数'] + ' 个历史期标记（应 ≥2，否则「之前的断层」看不见）');
  }
  if (!(out['K线区间可用交易日'] > 200)) bad.push('历史 K 线未加长（最长连续期数个股应 > 200 个交易日，实际 ' + out['K线区间可用交易日'] + '，连续 ' + out['最长连续期数(清单)'] + ' 期）');
  // 切回「全部」应与首次「全部」一致（同口径自比，不受停牌影响）
  if (out['K线还原后根数'] !== out['全览根数']) {
    bad.push('切回「全部」后根数与首次「全部」不一致（' + out['K线还原后根数'] + ' vs ' + out['全览根数'] + '）');
  }
  // 蜡烛数 ≤ 交易日数：个股停牌日没有 K 线，属正常（如 688313 仕佳光子有 9 个停牌缺口）。
  // 不能用「相等」断言——2026-10-04 加入 603259 后最长连续期数个股变成 688313，
  // 它有 9 天停牌，旧断言于是误报「438 vs 447」。
  if (out['全览根数'] > out['K线区间可用交易日']) {
    bad.push('全览根数多于可用交易日（' + out['全览根数'] + ' > ' + out['K线区间可用交易日'] + '），日期轴或 bars 错位');
  }
  out['停牌缺口(交易日-蜡烛)'] = out['K线区间可用交易日'] - out['全览根数'];
  if (out['停牌缺口(交易日-蜡烛)'] > out['K线区间可用交易日'] * 0.1) {
    bad.push('停牌缺口异常大：' + out['停牌缺口(交易日-蜡烛)'] + ' 天，疑似 K 线缺失而非停牌');
  }
  if (out['K线复位后根数'] !== 120) bad.push('切回「近 120 日」应回到 120 根，实际 ' + out['K线复位后根数']);
  if (out['K线切换后按压'] !== 'true') bad.push('K 线区间切换到「近 120 日」后 aria-pressed 未更新');
  // 停牌日无 K 线，根数允许略少于窗口（但不得多于 120、也不得少得离谱）
  if (!(out['K线切换后根数'] <= 120 && out['K线切换后根数'] >= 110)) {
    bad.push('切换「近 120 日」后 K 线应重绘为 ~120 根，实际 ' + out['K线切换后根数']);
  }

  // ---- 同花顺式交互断言 ----
  if (!/第 \d+–\d+ \//.test(out['区间完整位置'] || '')) bad.push('区间栏缺少「第 a–b / 共 N」位置指示：' + out['区间完整位置']);
  if (out['区间默认位置'] !== undefined && !/第 \d+–\d+ \/ 共 \d+/.test(out['区间默认位置'])) bad.push('默认位置文案异常：' + out['区间默认位置']);
  if (out['滚轮放大后根数'] === undefined) bad.push('滚轮缩放未测试（jsdom 无 WheelEvent？）');
  else {
    if (!(out['滚轮放大后根数'] < out['全览根数'])) bad.push('向上滚未放大：' + out['滚轮放大后根数'] + ' 应小于全览 ' + out['全览根数']);
    if (out['滚轮放大后出现回到最新'] !== true) bad.push('放大翻看历史后未出现「回到最新」按钮');
    if (out['滚轮缩小后根数'] !== out['全览根数']) bad.push('向下滚未缩回全览：' + out['滚轮缩小后根数'] + ' 应为 ' + out['全览根数']);
  }
  if (!(out['按钮放大后根数'] < out['滚轮缩小后根数'])) bad.push('＋按钮未放大 K 线');
  if (out['回到最新_点击后仍存在'] !== false) bad.push('点「回到最新」后按钮未消失（end 未回到最新）');
  if (!(out['拖动后右端'] < out['拖动前右端'])) bad.push('向右拖动未回看更早历史：' + out['拖动前右端'] + ' → ' + out['拖动后右端']);
  if (out['拖动后出现回到最新'] !== true) bad.push('拖动进入历史后未出现「回到最新」按钮');
  if (!(out['拖动后数据仍在'] > 0)) bad.push('拖动后 K 线数据丢失');
  if (out['双击后右端'] !== out['K线区间可用交易日']) bad.push('双击未回到最新：右端 ' + out['双击后右端'] + ' 应为 ' + out['K线区间可用交易日']);
  if (!(out['双击后根数'] > 0)) bad.push('双击后 K 线数据丢失');

  console.log(bad.length ? '❌ 未通过：' + bad.join('、') : '✅ 自检通过');
  dom.window.close();
}, 2000);
