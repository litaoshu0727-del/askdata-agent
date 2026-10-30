"use strict";
// AskData 工作台：会话列表 + 对话流。一轮对话 = 你的问题 + 链路的每一步（可展开的工具调用行）+ 回答和结果。
// 接口一次返回整条链路，页面不模拟逐步进度：等待时只显示真实耗时。

const $ = id => document.getElementById(id);
const esc = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[ch]));
const icon = (name, extra = "") => `<svg class="icon ${extra}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const uid = () => typeof crypto.randomUUID === "function" ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36);
const DATASETS = {ecommerce: "电商分析", ecommerce_big: "电商大库", chinook: "音乐商店", sakila: "DVD 租赁", trade: "交易分析"};
const MAX_SESSIONS = 20;
const MAX_TURNS = 30;

const state = {
  health: null, schema: null, ready: false, busy: false, page: "chat",
  sessions: [], current: null, userId: `web-user-${uid()}`,
  pane: {open: false, tab: "overview", turnId: null},
  pending: null, started: 0, timer: null,
  views: {},   // "轮次-步骤" → {view, metric}：重绘对话流时保留表格 / 图表的选择
};
let toastTimer;

function datasetName() { return DATASETS[state.health?.dataset] || state.health?.dataset || "数据源"; }
function toast(message) {
  $("toast").textContent = message; $("toast").hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { $("toast").hidden = true; }, 3200);
}
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {cache: "no-store"} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  let payload;
  try { payload = await response.json(); } catch { throw new Error("服务返回了无法读取的响应，请检查后台日志。"); }
  if (!response.ok) throw new Error([payload.error, payload.hint].filter(Boolean).join("\n") || `请求失败（${response.status}）`);
  return payload;
}

/* ---------- 会话存储：只存在当前标签页（sessionStorage），读写失败不影响使用 ---------- */
function storageKey() { return `askdata-ui-v2:${state.health?.dataset || "default"}`; }
function save() {
  try {
    sessionStorage.setItem(storageKey(), JSON.stringify({sessions: state.sessions, currentId: state.current?.id, userId: state.userId}));
  } catch { /* 存不下就只留在内存里 */ }
}
function load() {
  try {
    const stored = JSON.parse(sessionStorage.getItem(storageKey()) || "null");
    if (!stored || !Array.isArray(stored.sessions)) return;
    state.sessions = stored.sessions.filter(s => s && typeof s.id === "string" && Array.isArray(s.turns) && s.turns.length).slice(0, MAX_SESSIONS);
    if (typeof stored.userId === "string") state.userId = stored.userId;
    state.current = state.sessions.find(s => s.id === stored.currentId) || null;
  } catch { state.sessions = []; }
}
function freshSession(id) { return {id: id || `web-${uid()}`, title: "", turns: [], updated: Date.now()}; }
function relativeTime(time) {
  const minutes = Math.round((Date.now() - time) / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const date = new Date(time);
  return date.toDateString() === new Date().toDateString()
    ? date.toLocaleTimeString("zh-CN", {hour: "2-digit", minute: "2-digit"})
    : date.toLocaleDateString("zh-CN", {month: "numeric", day: "numeric"});
}

/* ---------- 侧栏 ---------- */
function renderSidebar() {
  const list = [...state.sessions].sort((a, b) => b.updated - a.updated);
  $("sessions").innerHTML = list.length
    ? list.map(s => `<button class="session ${state.page === "chat" && s.id === state.current?.id ? "active" : ""}" data-session="${esc(s.id)}" title="${esc(s.title)}" ${state.busy ? "disabled" : ""}><span class="session-name">${esc(s.title)}</span><span class="session-meta">${s.turns.length} 轮 · ${esc(relativeTime(s.updated))}</span></button>`).join("")
    : '<p class="sessions-empty">还没有会话。<br>问的问题会按会话留在这里。</p>';
  for (const page of ["chat", "source"]) {
    if (state.page === page) $("nav-" + page).setAttribute("aria-current", "page"); else $("nav-" + page).removeAttribute("aria-current");
  }
  $("new-session").disabled = state.busy;
}

/* ---------- SQL 高亮 ---------- */
const SQL_WORDS = /('(?:''|[^'])*'|\b(?:SELECT|FROM|JOIN|LEFT|RIGHT|INNER|OUTER|CROSS|ON|WHERE|AND|OR|GROUP|BY|ORDER|LIMIT|OFFSET|DESC|ASC|AS|SUM|COUNT|AVG|MAX|MIN|DISTINCT|WITH|CASE|WHEN|THEN|ELSE|END|HAVING|IS|NOT|NULL|IN|EXISTS|OVER|PARTITION|ROW_NUMBER|RANK|LAG|LEAD|UNION|ALL|BETWEEN|LIKE|ROUND|CAST|COALESCE|STRFTIME|DATE)\b)/gi;
function highlightSQL(sql) {
  return String(sql).split(SQL_WORDS).map((part, i) => i % 2 ? `<span class="${part.startsWith("'") ? "sql-str" : "sql-kw"}">${esc(part)}</span>` : esc(part)).join("");
}
function oneLine(text, max = 90) {
  const line = String(text || "").replace(/\s+/g, " ").trim();
  return line.length > max ? line.slice(0, max - 1) + "…" : line;
}

/* ---------- 工具调用行：把链路的每一步摊开 ---------- */
function toolRow({name, detail, dot = "", body = "", open = false}) {
  return `<details class="tool"${open ? " open" : ""}><summary><span class="tool-dot ${dot}"></span><span class="tool-name">${esc(name)}</span><span class="tool-detail">${esc(detail)}</span>${icon("chevron", "tool-chev")}</summary>${body ? `<div class="tool-body">${body}</div>` : ""}</details>`;
}
function toolsHTML(d) {
  if (!d.queried_database) {
    return toolRow({name: "会话问答", detail: "用会话里已有的结果回答，没有查询数据库", dot: "ok",
      body: `<p>路由：${esc(d.route || "")}</p>${d.route_reason ? `<p>${esc(d.route_reason)}</p>` : ""}`});
  }
  const rows = [];
  if (d.rewritten_query) {
    rows.push(toolRow({name: "改写问题", detail: d.rewritten_query, dot: "ok", body: `<p>结合上一轮，把指代换成了具体对象：</p><pre class="code wrap">${esc(d.rewritten_query)}</pre>`}));
  }
  const tables = d.schema_tables.map(t => t.name);
  rows.push(toolRow({
    name: "检索 Schema", detail: `${tables.length} 张表 · ${d.keywords.length} 个关键词`, dot: tables.length ? "ok" : "warn",
    body: `${d.keywords.length ? `<p>关键词</p><div class="chips">${d.keywords.map(k => `<span class="kw">${esc(k)}</span>`).join("")}</div>` : ""}${tables.length ? `<p style="margin-top:8px">命中的表</p><div class="chips">${tables.map(t => `<span class="kw"><code>${esc(t)}</code></span>`).join("")}</div>` : ""}`,
  }));
  const noSQL = !d.steps.length, refused = isRefusal(d);
  // 拒答的原因已经写在回答里，规划就不用自动展开；别的“没有 SQL”说不清原因，展开给人看
  rows.push(toolRow({
    name: "规划查询", detail: refused ? "判定库里缺数据，没有生成 SQL" : noSQL ? "没有生成 SQL" : `${d.steps.length} 个执行步骤`,
    dot: noSQL ? "warn" : "ok", open: noSQL && !refused, body: planHTML(d),
  }));
  d.steps.forEach((step, i) => {
    const out = step.success
      ? `<div class="out-line">⎿ 返回 ${step.row_count || 0} 行${step.truncated ? "（已截断）" : ""}</div>`
      : `<div class="out-line err">⎿ ${esc(step.error || "执行失败")}</div>`;
    rows.push(toolRow({name: d.steps.length > 1 ? `执行 SQL ${i + 1}` : "执行 SQL", detail: oneLine(step.sql), dot: step.success ? "ok" : "err",
      body: `<pre class="code">${highlightSQL(step.sql || "")}</pre>${out}`}));
  });
  // 拒答本身记一条 SCHEMA_INSUFFICIENT，回答里已经说清楚了，对话里不再重复；运行详情里照常列出
  const diags = refused ? d.diagnostics.filter(item => item.code !== "SCHEMA_INSUFFICIENT") : d.diagnostics;
  if (diags.length) {
    rows.push(toolRow({name: "降级记录", detail: `${diags.length} 条`, dot: "warn",
      body: diags.map(item => `<div class="diag"><code>${esc(item.code)}</code>${esc(item.text.replace(/^\[[^\]]+\]\s*/, ""))}</div>`).join("")}));
  }
  return rows.join("");
}

/* ---------- 规划与拒答 ---------- */
const PLAN_FIELDS = [["database", "数据库"], ["objects", "处理对象"], ["instruction", "操作指令"], ["output", "输出目标"]];
let nameCache = {schema: null, names: new Set()};
function schemaNames() {
  if (nameCache.schema !== state.schema) {
    const names = new Set();
    for (const t of state.schema?.tables || []) {
      names.add(t.name.toLowerCase());
      for (const c of t.columns) { names.add(c.name.toLowerCase()); names.add(`${t.name}.${c.name}`.toLowerCase()); }
    }
    nameCache = {schema: state.schema, names};
  }
  return nameCache.names;
}
// 把文字里出现的表名、字段名套上 code，读起来能一眼分清哪些是库里的东西
function withCode(text) {
  const names = schemaNames();
  return String(text).split(/([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)/)
    .map((part, i) => i % 2 && names.has(part.toLowerCase()) ? `<code>${esc(part)}</code>` : esc(part)).join("");
}
function planHTML(d) {
  // 旧会话没有 plan 字段，或者四元组没解析出来，就退回原文
  if (!d.plan?.length) return d.cot ? `<pre class="code wrap">${esc(d.cot.trim())}</pre>` : "<p>没有返回规划内容。</p>";
  return d.plan.map(s => `<div class="plan-step"><div class="plan-no">步骤 ${esc(s.step)}${s.missing ? '<span class="plan-flag">缺数据</span>' : ""}</div><dl class="plan-kv">${PLAN_FIELDS.map(([key, label]) => s[key] ? `<dt>${label}</dt><dd>${withCode(s[key])}</dd>` : "").join("")}</dl></div>`).join("");
}
function isRefusal(d) { return !d.steps.length && (d.plan || []).some(s => s.missing); }
function refusalReasons(d) {
  return d.plan.filter(s => s.missing)
    .flatMap(s => String(s.objects || "").split(/[；;]\s*/))
    .map(s => s.trim().replace(/[，,。.]+$/, "")).filter(Boolean);
}
// 原因里点到的表优先；一张都没点到，就给检索命中的第一张
function refusalTables(d, reasons) {
  const text = reasons.join(" ").toLowerCase();
  const named = (state.schema?.tables || []).map(t => t.name).filter(name => text.includes(name.toLowerCase()));
  return (named.length ? named : d.schema_tables.map(t => t.name)).slice(0, 2);
}
function refusalHTML(d) {
  const reasons = refusalReasons(d);
  return `<div class="answer">这个问题答不了：库里没有回答它需要的数据。所以这次没有生成 SQL，也没有拿意思相近的字段凑一个数。</div>${reasons.length ? `<div class="refusal"><div class="refusal-label">缺的数据</div><ul>${reasons.map(r => `<li>${withCode(r)}</li>`).join("")}</ul></div>` : ""}`;
}

/* ---------- 回答与结果 ---------- */
function summary(d) {
  if (!d.queried_database) return d.answer || "";
  if (!d.steps.length) return "这次没有生成 SQL：规划没有给出能执行的步骤，规划内容见上面的「规划查询」。";
  const ok = d.steps.filter(s => s.success);
  if (!ok.length) return "SQL 执行失败，修正之后仍然失败。报错见上面的「执行 SQL」。";
  const rows = ok.reduce((sum, s) => sum + (s.row_count || 0), 0);
  const failed = d.steps.length - ok.length;
  return `查询完成，返回 ${rows} 行${failed ? `；另有 ${failed} 个步骤执行失败` : ""}。`;
}
function columnsOf(step) { return step.columns?.length ? step.columns : Object.keys(step.rows?.[0] || {}); }
function numericColumns(step) {
  return columnsOf(step).filter(c => {
    const values = (step.rows || []).map(r => r[c]).filter(v => v !== null && v !== undefined);
    return values.length && values.every(v => typeof v === "number" && Number.isFinite(v));
  });
}
// 只去掉二进制浮点的噪声（58312.979999999996 → 58312.98），有效数字不动；导出 CSV 用原值。
function cell(value) {
  if (value === null || value === undefined) return '<span class="null">NULL</span>';
  if (typeof value === "number" && Number.isFinite(value) && !Number.isInteger(value)) return esc(String(Number(value.toPrecision(12))));
  return esc(value);
}
function tableHTML(step) {
  if (!step.rows?.length) return '<div class="empty-result">查询完成，没有匹配的数据。</div>';
  const cols = columnsOf(step);
  return `<div class="table-wrap"><table><thead><tr><th class="num">#</th>${cols.map(c => `<th scope="col">${esc(c)}</th>`).join("")}</tr></thead><tbody>${step.rows.map((row, i) => `<tr><td class="num">${i + 1}</td>${cols.map(c => `<td>${cell(row[c])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}
function chartSVG(step, metric, dimension) {
  const valid = step.rows.filter(r => typeof r[metric] === "number" && Number.isFinite(r[metric]));
  const rows = valid.slice(0, 15), width = 640, left = 140, right = 80, top = 14, rowH = 30, height = top + rows.length * rowH + 22;
  const values = rows.map(r => r[metric]), min = Math.min(0, ...values), max = Math.max(0, ...values), span = max - min || 1, plot = width - left - right;
  const x = v => left + (v - min) / span * plot, zero = x(0);
  const fmt = v => new Intl.NumberFormat("zh-CN", {maximumFractionDigits: 2}).format(v);
  const grid = Array.from({length: 5}, (_, i) => { const v = min + span * i / 4, p = x(v); return `<line class="chart-grid" x1="${p}" y1="${top - 6}" x2="${p}" y2="${height - 18}"/><text class="chart-tick" x="${p}" y="${height - 4}" text-anchor="middle" font-size="10">${esc(fmt(v))}</text>`; }).join("");
  const bars = rows.map((r, i) => {
    const v = values[i], label = String(dimension ? r[dimension] ?? "NULL" : `第 ${i + 1} 行`), y = top + i * rowH;
    return `<g><title>${esc(label)}：${esc(fmt(v))}</title><text class="chart-label" x="${left - 10}" y="${y + 14}" text-anchor="end" font-size="11">${esc(label.length > 14 ? label.slice(0, 13) + "…" : label)}</text><rect class="chart-bar${i === 0 ? " primary" : ""}" x="${Math.min(zero, x(v))}" y="${y}" width="${Math.max(Math.abs(x(v) - zero), 1)}" height="20" rx="4"/><text class="chart-value" x="${v < 0 ? x(v) - 6 : x(v) + 6}" y="${y + 14}" text-anchor="${v < 0 ? "end" : "start"}" font-size="11">${esc(fmt(v))}</text></g>`;
  }).join("");
  return `<svg class="data-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(metric)} 柱状图，前 ${rows.length} 行">${grid}<line class="chart-axis" x1="${zero}" y1="${top - 6}" x2="${zero}" y2="${height - 18}"/>${bars}</svg><p class="chart-caption">${esc(metric)} · 按结果顺序${valid.length > 15 ? "，只画前 15 行" : ""}${valid.length < step.rows.length ? `，${step.rows.length - valid.length} 行空值没画` : ""}</p>`;
}
function resultsHTML(turn) {
  const d = turn.data;
  return d.steps.map((step, i) => {
    if (!step.success) return "";
    const shown = step.rows?.length || 0, total = step.row_count || 0;
    const chartable = shown > 1 && numericColumns(step).length > 0;
    const foot = step.truncated ? `结果超过 ${total} 行上限，已截断；页面拿到前 ${shown} 行。`
      : shown < total ? `共 ${total} 行，页面和导出只含接口返回的前 ${shown} 行。` : `${total} 行 · ${columnsOf(step).length} 列`;
    const chart = chartable && state.views[`${turn.id}-${i}`]?.view === "chart";
    const segButton = (view, label, name) => `<button class="${chart === (view === "chart") ? "active" : ""}" data-view="${view}" data-turn="${esc(turn.id)}" data-step="${i}" aria-pressed="${chart === (view === "chart")}">${icon(name)}${label}</button>`;
    return `<section class="result"><div class="result-head"><div class="result-title">${icon("table")}${d.steps.length > 1 ? `结果 ${i + 1}` : "结果"}</div><div class="result-actions">${chartable ? `<div class="seg" role="group" aria-label="显示方式">${segButton("table", "表格", "table")}${segButton("chart", "图表", "chart")}</div>` : ""}${shown ? `<button class="ghost" data-action="export" data-turn="${esc(turn.id)}" data-step="${i}">${icon("down")}CSV</button>` : ""}</div></div><div id="view-${esc(turn.id)}-${i}">${chart ? chartBlock(turn.id, i, step) : tableHTML(step)}</div><div class="result-foot">${esc(foot)}</div></section>`;
  }).join("");
}
function turnHTML(turn) {
  const user = `<div class="user-row"><div class="bubble">${esc(turn.query)}</div></div>`;
  if (turn.error) {
    return `<div class="turn" data-turn-id="${esc(turn.id)}">${user}<div class="assistant"><div class="error-box" role="alert"><strong>这次没有完成</strong>${esc(turn.error)}</div><div class="turn-meta"><button class="ghost" data-action="retry" data-turn="${esc(turn.id)}">重试</button></div></div></div>`;
  }
  const d = turn.data, firstSQL = d.steps.findIndex(s => s.sql), refused = isRefusal(d);
  const answer = refused ? refusalHTML(d) : `<div class="answer">${esc(summary(d))}</div>`;
  const tableLinks = refused ? refusalTables(d, refusalReasons(d)).map(name => `<button class="ghost" data-action="table" data-table="${esc(name)}">${icon("table")}看 ${esc(name)} 有哪些字段</button>`).join("") : "";
  return `<div class="turn" data-turn-id="${esc(turn.id)}">${user}<div class="assistant"><div class="tools">${toolsHTML(d)}</div>${answer}${resultsHTML(turn)}<div class="turn-meta"><span class="meta-text">${esc(d.elapsed)}s</span>${firstSQL >= 0 ? `<button class="ghost" data-action="copy" data-turn="${esc(turn.id)}" data-step="${firstSQL}">${icon("copy")}复制 SQL</button>` : ""}${tableLinks}<button class="ghost" data-action="details" data-turn="${esc(turn.id)}">${icon("panel")}运行详情</button></div></div></div>`;
}
function pendingHTML() {
  return `<div class="turn"><div class="user-row"><div class="bubble">${esc(state.pending)}</div></div><div class="assistant"><div class="thinking"><span class="spark" aria-hidden="true">✻</span><span>正在检索、规划并执行查询…</span><span class="elapsed" id="elapsed">0.0s</span></div></div></div>`;
}
function welcomeHTML() {
  const samples = (state.health?.samples || []).filter(q => !/^它们/.test(q)).slice(0, 4);
  const h = state.health;
  const note = q => q === h?.refusal_sample ? '<span class="sample-note">库里没有这项数据，用来看它怎么拒答</span>' : "";
  return `<div class="welcome"><div class="welcome-mark">${icon("db")}</div><h2>今天想查点什么？</h2><p>用中文提问，系统自己找表、写 SQL、执行，并把每一步摊开给你看。</p></div><div class="welcome-dock" id="welcome-dock"></div>${samples.length ? `<div class="samples">${samples.map(q => `<button class="sample" data-sample="${esc(q)}">${esc(q)}${note(q)}</button>`).join("")}</div>` : ""}${h ? `<p class="source-line">${esc(datasetName())} · ${esc(h.tables)} 张表 · ${esc(h.columns)} 个字段</p>` : ""}`;
}

/* ---------- 主区域 ---------- */
function renderThread() {
  const dock = $("composer-dock"), hadFocus = document.activeElement === $("q");
  $("chat-view").appendChild(dock);
  const turns = state.current?.turns || [];
  const empty = !turns.length && !state.busy;
  $("chat-view").classList.toggle("empty", empty);
  $("thread").innerHTML = empty ? welcomeHTML() : turns.map(turnHTML).join("") + (state.busy ? pendingHTML() : "");
  if (empty) $("welcome-dock").appendChild(dock);
  $("q").rows = empty ? 2 : 1;
  if (hadFocus) $("q").focus();
  $("session-title").textContent = state.page === "source" ? "数据源" : state.current?.title || (state.busy ? state.pending : "新会话");
  autosize();
}
function scrollToBottom() { const s = $("scroll"); s.scrollTop = s.scrollHeight; }
function showPage(page) {
  state.page = page;
  $("chat-view").hidden = page !== "chat";
  $("source-view").hidden = page !== "source";
  if (page === "source") renderSource();
  renderThread(); renderSidebar(); closeNav();
}

/* ---------- 数据源 ---------- */
function schemaTables(tables, openFirst = false) {
  return tables.map((t, i) => `<details class="schema-table"${openFirst && i === 0 ? " open" : ""}><summary>${icon("table")}${esc(t.name)}<span>${t.columns.length} 列</span></summary>${t.summary ? `<p class="schema-desc">${esc(t.summary)}</p>` : ""}${t.columns.map(c => `<div class="schema-col"><div><code>${esc(c.name)}</code>${c.primary_key ? '<span class="pk">主键</span>' : ""}${c.desc ? `<p>${esc(c.desc)}</p>` : ""}</div><span class="type">${esc(c.type || c.role || "")}</span></div>`).join("")}</details>`).join("");
}
function matchTables(term) {
  const q = term.trim().toLowerCase();
  return (state.schema?.tables || []).filter(t => !q || [t.name, t.summary, ...(t.aliases || []), ...t.columns.flatMap(c => [c.name, c.desc])].join(" ").toLowerCase().includes(q));
}
function renderSource() {
  const h = state.health;
  if (!h || !state.schema) { $("source-view").innerHTML = '<div class="source-inner"><h2>数据源</h2><p class="source-intro">元数据暂时读不到，刷新页面再试。</p></div>'; return; }
  $("source-view").innerHTML = `<div class="source-inner"><h2>${esc(datasetName())}</h2><p class="source-intro">当前连接的 SQLite 库。提问时，系统会从这些表和字段里检索相关的部分。</p><div class="stats"><div class="stat"><span>表</span><b>${esc(h.tables)}</b></div><div class="stat"><span>字段</span><b>${esc(h.columns)}</b></div><div class="stat"><span>关联</span><b>${state.schema.relations.length}</b></div></div><label class="search">${icon("search")}<span class="sr-only">搜索表或字段</span><input id="schema-search" type="search" placeholder="搜索表名、字段或业务含义…"></label><div id="source-tables">${schemaTables(state.schema.tables)}</div></div>`;
}
// 拒答下面的“看某张表有哪些字段”：跳到数据源页，搜这张表并展开它
function openSourceTable(name) {
  showPage("source");
  const input = $("schema-search");
  if (!input) return;
  input.value = name;
  const tables = matchTables(name).sort((a, b) => (b.name === name) - (a.name === name));
  $("source-tables").innerHTML = schemaTables(tables, true);
}

/* ---------- 运行详情 ---------- */
function paneTurn() {
  const turns = (state.current?.turns || []).filter(t => t.data);
  return turns.find(t => t.id === state.pane.turnId) || turns[turns.length - 1] || null;
}
function setPane(open, tab) {
  state.pane.open = open;
  if (tab) state.pane.tab = tab;
  $("pane").hidden = !open;
  $("pane-toggle").setAttribute("aria-expanded", String(open));
  renderPane();
}
function renderPane() {
  if (!state.pane.open) return;
  document.querySelectorAll("[data-tab]").forEach(b => b.setAttribute("aria-selected", String(b.dataset.tab === state.pane.tab)));
  const turn = paneTurn(), d = turn?.data, h = state.health;
  $("pane-sub").textContent = turn ? turn.query : "这个会话还没有提问";
  let html = "";
  if (state.pane.tab === "sql") {
    const plan = d && (d.cot || d.plan?.length) ? `<div class="pane-section"><div class="pane-label">规划</div>${planHTML(d)}</div>` : "";
    html = (d?.steps?.length
      ? d.steps.map((s, i) => `<div class="pane-section"><div class="step-head"><span>步骤 ${i + 1} · <span class="${s.success ? "good" : "bad"}">${s.success ? `成功，${s.row_count || 0} 行` : "失败"}</span></span><button class="ghost" data-action="copy" data-turn="${esc(turn.id)}" data-step="${i}">${icon("copy")}复制</button></div><pre class="code">${highlightSQL(s.sql || "")}</pre>${s.error ? `<div class="out-line err">${esc(s.error)}</div>` : ""}</div>`).join("")
      : `<div class="blank">${d ? "这一轮没有执行 SQL。" : "提问之后，生成的 SQL 会出现在这里。"}</div>`) + plan;
  } else if (state.pane.tab === "schema") {
    const hit = d?.schema_tables?.length;
    const tables = hit ? d.schema_tables : state.schema?.tables || [];
    const relations = hit ? d.relations || [] : state.schema?.relations || [];
    html = `<div class="pane-section"><div class="pane-label"><span>${hit ? "这一轮命中的表" : "全部表"}</span><span>${tables.length}</span></div>${tables.length ? schemaTables(tables, true) : '<div class="blank">没有可展示的 Schema。</div>'}</div>${relations.length ? `<div class="pane-section"><div class="pane-label">关联关系</div><div class="relations">${relations.map(esc).join("<br>")}</div></div>` : ""}`;
  } else {
    const run = d ? `<div class="pane-section"><div class="pane-label">这一轮</div><dl class="kv"><dt>路由</dt><dd>${d.queried_database ? "查询数据库" : "会话问答"}</dd><dt>耗时</dt><dd>${esc(d.elapsed)}s</dd><dt>相关表</dt><dd>${d.schema_tables.length}</dd><dt>SQL 步骤</dt><dd>${d.steps.length}</dd>${d.rewritten_query ? `<dt>改写后</dt><dd>${esc(d.rewritten_query)}</dd>` : ""}</dl></div>${d.keywords.length ? `<div class="pane-section"><div class="pane-label">检索关键词</div><div class="chips">${d.keywords.map(k => `<span class="kw">${esc(k)}</span>`).join("")}</div></div>` : ""}<div class="pane-section"><div class="pane-label"><span>降级记录</span><span>${d.diagnostics.length}</span></div>${d.diagnostics.length ? d.diagnostics.map(item => `<div class="diag"><code>${esc(item.code)}</code>${esc(item.text.replace(/^\[[^\]]+\]\s*/, ""))}</div>`).join("") : '<div class="diag ok">这一轮没有降级记录。</div>'}</div>` : '<div class="blank">提问之后，这里会列出路由、耗时、检索关键词和降级记录。</div>';
    const env = h ? `<div class="pane-section"><div class="pane-label">运行环境</div><dl class="kv"><dt>数据源</dt><dd>${esc(datasetName())}（${esc(h.tables)} 表 / ${esc(h.columns)} 字段）</dd><dt>模型</dt><dd>${esc(h.provider === "mock" ? "Mock 演示模式" : h.model || h.provider)}</dd><dt>向量与精排</dt><dd>${h.local_models ? "本地 BGE 模型" : "未启用本地模型"}</dd></dl>${h.provider === "mock" ? '<p class="pane-note">没有配置模型密钥：只有内置示例能跑通，结果不代表真实问数能力。</p>' : ""}${(h.setup_diagnostics || []).map(item => `<div class="diag">${esc(item)}</div>`).join("")}</div>` : "";
    html = run + env;
  }
  $("pane-body").innerHTML = html;
}

/* ---------- 输入框 ---------- */
function autosize() {
  const field = $("q");
  $("send").disabled = !state.ready || state.busy || !field.value.trim();
  // 空的时候按 rows 的自然高度；有内容才量。量要等布局稳定：输入框刚挪位置时宽度还不对，会量出好几倍的高度。
  if (!field.value) { field.style.height = ""; return; }
  requestAnimationFrame(() => {
    field.style.height = "auto";
    field.style.height = Math.min(field.scrollHeight, 220) + "px";
  });
}
function setQuery(query) { if (state.page !== "chat") showPage("chat"); $("q").value = query; autosize(); $("q").focus(); }
function setBusy(value) {
  state.busy = value;
  $("q").disabled = value;
  // 等待时转圈，不画"停止"方块：接口不支持中途打断，画了会让人以为能停。
  $("send").innerHTML = value ? '<span class="ring" aria-hidden="true"></span>' : icon("arrow");
  $("send").setAttribute("aria-label", value ? "正在查询" : "发送");
  renderSidebar(); autosize();
}

/* ---------- 提问 ---------- */
async function ask(queryText) {
  const query = (queryText ?? $("q").value).trim();
  if (!query || state.busy || !state.ready) return;
  if (!state.current) state.current = freshSession();
  const session = state.current;
  state.pending = query; state.started = Date.now();
  $("q").value = "";
  setBusy(true); renderThread(); scrollToBottom();
  state.timer = setInterval(() => { const el = $("elapsed"); if (el) el.textContent = ((Date.now() - state.started) / 1000).toFixed(1) + "s"; }, 100);
  let turn;
  try {
    const data = await api("/api/ask", {query, session_id: session.id, user_id: state.userId});
    for (const field of ["keywords", "schema_tables", "relations", "plan", "steps", "diagnostics"]) if (!Array.isArray(data[field])) data[field] = [];
    turn = {id: uid(), query, data, time: Date.now()};
  } catch (error) {
    turn = {id: uid(), query, error: error.message, time: Date.now()};
  } finally {
    clearInterval(state.timer);
  }
  session.turns = [...session.turns, turn].slice(-MAX_TURNS);
  session.title = session.title || query;
  session.updated = Date.now();
  if (!state.sessions.includes(session)) state.sessions = [session, ...state.sessions].slice(0, MAX_SESSIONS);
  state.pending = null; state.pane.turnId = turn.data ? turn.id : state.pane.turnId;
  save(); setBusy(false); renderThread(); renderPane(); scrollToBottom();
  if (turn.error) $("q").value = query;
  autosize(); $("q").focus();
}
async function newSession() {
  if (state.busy) return;
  let id;
  try { id = (await api("/api/reset", {})).session_id; } catch { id = undefined; }
  state.current = freshSession(id); state.pane.turnId = null;
  save(); showPage("chat"); renderPane(); $("q").focus();
}
function selectSession(id) {
  if (state.busy) return;
  const session = state.sessions.find(s => s.id === id);
  if (!session) return;
  state.current = session; state.pane.turnId = null;
  save(); showPage("chat"); renderPane(); scrollToBottom();
}
function findTurn(id) { return state.current?.turns.find(t => t.id === id); }

/* ---------- 结果操作 ---------- */
function chartDimension(step, metric) {
  const metrics = numericColumns(step);
  return columnsOf(step).find(c => !metrics.includes(c)) || columnsOf(step).find(c => c !== metric) || "";
}
function chartBlock(turnId, index, step) {
  const metrics = numericColumns(step);
  const saved = state.views[`${turnId}-${index}`]?.metric;
  const metric = metrics.includes(saved) ? saved : metrics.find(c => !/(^id$|_id$)/i.test(c)) || metrics[0];
  return `<div class="chart-wrap"><div class="chart-controls"><label for="metric-${esc(turnId)}-${index}">指标</label><select id="metric-${esc(turnId)}-${index}" data-metric data-turn="${esc(turnId)}" data-step="${index}">${metrics.map(c => `<option value="${esc(c)}"${c === metric ? " selected" : ""}>${esc(c)}</option>`).join("")}</select></div><div id="chart-${esc(turnId)}-${index}">${chartSVG(step, metric, chartDimension(step, metric))}</div></div>`;
}
function showView(turnId, index, view) {
  const step = findTurn(turnId)?.data?.steps[index];
  if (!step) return;
  const key = `${turnId}-${index}`;
  state.views[key] = {...state.views[key], view};
  document.querySelectorAll(`[data-view][data-turn="${CSS.escape(turnId)}"][data-step="${index}"]`).forEach(b => { const on = b.dataset.view === view; b.classList.toggle("active", on); b.setAttribute("aria-pressed", String(on)); });
  $(`view-${turnId}-${index}`).innerHTML = view === "chart" ? chartBlock(turnId, index, step) : tableHTML(step);
}
function csvCell(value) {
  let text = value === null || value === undefined ? "" : String(value);
  if (typeof value === "string" && /^\s*[=+\-@]/.test(text)) text = "'" + text;   // 防止表格软件把它当公式执行
  return '"' + text.replace(/"/g, '""') + '"';
}
function exportCSV(turnId, index) {
  const step = findTurn(turnId)?.data?.steps[index];
  if (!step) return;
  const cols = columnsOf(step);
  const csv = [cols.map(csvCell).join(","), ...(step.rows || []).map(r => cols.map(c => csvCell(r[c])).join(","))].join("\r\n");
  const url = URL.createObjectURL(new Blob(["﻿" + csv], {type: "text/csv;charset=utf-8"}));
  const link = document.createElement("a");
  link.href = url; link.download = `AskData_${state.health.dataset}_${new Date().toISOString().slice(0, 10)}_${index + 1}.csv`;
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
  toast(`已导出 ${step.rows.length} 行`);
}
async function copySQL(turnId, index) {
  const sql = findTurn(turnId)?.data?.steps[index]?.sql;
  if (!sql) return;
  try { await navigator.clipboard.writeText(sql); toast("SQL 已复制"); } catch { toast("浏览器没有允许复制，请手动选中 SQL"); }
}

/* ---------- 布局开关 ---------- */
const narrow = () => matchMedia("(max-width: 760px)").matches;
function closeNav() { $("app").classList.remove("nav-open"); $("nav-scrim").hidden = true; }
function toggleSidebar(open) {
  if (narrow()) { $("app").classList.toggle("nav-open", open); $("nav-scrim").hidden = !open; }
  else $("app").classList.toggle("sidebar-collapsed", !open);
}
function effectiveTheme() {
  return document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}
function syncThemeIcon() { $("theme-toggle").innerHTML = icon(effectiveTheme() === "dark" ? "sun" : "moon"); }
function toggleTheme() {
  const next = effectiveTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("askdata-theme", next); } catch { /* 记不住也没关系 */ }
  syncThemeIcon();
}

/* ---------- 事件 ---------- */
document.addEventListener("click", event => {
  const el = event.target.closest("button");
  if (!el) return;
  if (el.dataset.session) selectSession(el.dataset.session);
  else if (el.dataset.sample !== undefined) setQuery(el.dataset.sample);
  else if (el.dataset.view) showView(el.dataset.turn, Number(el.dataset.step), el.dataset.view);
  else if (el.dataset.tab) { state.pane.tab = el.dataset.tab; renderPane(); }
  else if (el.dataset.action === "export") exportCSV(el.dataset.turn, Number(el.dataset.step));
  else if (el.dataset.action === "copy") copySQL(el.dataset.turn, Number(el.dataset.step));
  else if (el.dataset.action === "table") openSourceTable(el.dataset.table);
  else if (el.dataset.action === "details") { state.pane.turnId = el.dataset.turn; setPane(true, "overview"); }
  else if (el.dataset.action === "retry") {
    const turn = findTurn(el.dataset.turn);
    if (turn) { state.current.turns = state.current.turns.filter(t => t !== turn); save(); ask(turn.query); }
  }
});
document.addEventListener("change", event => {
  const el = event.target;
  if (el.dataset.metric === undefined) return;
  const step = findTurn(el.dataset.turn)?.data?.steps[Number(el.dataset.step)];
  if (!step) return;
  const key = `${el.dataset.turn}-${el.dataset.step}`;
  state.views[key] = {...state.views[key], metric: el.value};
  $(`chart-${el.dataset.turn}-${el.dataset.step}`).innerHTML = chartSVG(step, el.value, chartDimension(step, el.value));
});
document.addEventListener("input", event => {
  if (event.target.id !== "schema-search") return;
  const tables = matchTables(event.target.value);
  $("source-tables").innerHTML = tables.length ? schemaTables(tables, !!event.target.value) : '<p class="sessions-empty">没有匹配的表或字段。</p>';
});
$("composer").addEventListener("submit", event => { event.preventDefault(); ask(); });
$("q").addEventListener("input", autosize);
// Safari 里确认输入法候选词的那次回车 isComposing 已是 false，只能靠 keyCode 229 认出来
$("q").addEventListener("keydown", event => { if (event.key === "Enter" && !event.shiftKey && !event.isComposing && event.keyCode !== 229) { event.preventDefault(); ask(); } });
$("new-session").onclick = newSession;
$("nav-chat").onclick = () => showPage("chat");
$("nav-source").onclick = () => showPage("source");
$("dataset-chip").onclick = () => showPage("source");
$("sidebar-close").onclick = () => toggleSidebar(false);
$("sidebar-open").onclick = () => toggleSidebar(true);
$("nav-scrim").onclick = closeNav;
$("pane-toggle").onclick = () => setPane($("pane").hidden);
$("pane-close").onclick = () => setPane(false);
$("theme-toggle").onclick = toggleTheme;
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", syncThemeIcon);
matchMedia("(max-width: 760px)").addEventListener("change", closeNav);
document.addEventListener("keydown", event => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); newSession(); }
  if (event.key === "Escape") { closeNav(); if (state.pane.open) setPane(false); }
});

/* ---------- 启动 ---------- */
async function init() {
  syncThemeIcon();
  renderThread(); renderSidebar();
  try {
    const health = await api("/api/health");
    state.health = health; state.ready = true;
    load();
    $("status-dot").className = "dot ok";
    $("status-text").textContent = "服务已连接";
    $("status-sub").textContent = `${datasetName()} · ${health.provider === "mock" ? "Mock 演示模式" : health.model || health.provider}`;
    $("dataset-name").textContent = datasetName();
    $("composer-dataset").textContent = datasetName();
    $("model").textContent = health.provider === "mock" ? "Mock 演示" : health.model || health.provider;
    $("model").classList.toggle("mock", health.provider === "mock");
    if (health.provider === "mock") $("composer-note").textContent = "Mock 演示模式：只有内置示例能跑通，结果不代表真实模型能力。";
    renderSidebar(); renderThread(); scrollToBottom();
    try { state.schema = await api("/api/schema"); } catch { /* 数据源页读不到元数据也不影响提问 */ }
    if (state.page === "source") renderSource();
    renderPane();
  } catch (error) {
    $("status-dot").className = "dot err";
    $("status-text").textContent = "服务未连接";
    $("status-sub").textContent = "确认后台服务在运行后刷新页面";
    $("model").textContent = "未连接";
    toast(error.message);
  }
  autosize();
}
init();
