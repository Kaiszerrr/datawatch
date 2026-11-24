"use strict";
const NS = "http://www.w3.org/2000/svg";
const $ = id => document.getElementById(id);
const tip = $("tip");
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
let st = null, token = "", range = "today", formReady = false, appLimits = {};

function fmt(b) { b = +b || 0; return b >= 1e9 ? (b / 1e9).toFixed(2) + " GB" : b >= 1e6 ? (b / 1e6).toFixed(b >= 1e8 ? 0 : 1) + " MB" : (b / 1e3).toFixed(0) + " KB"; }
function rate(b) { b = +b || 0; return b >= 1e6 ? (b / 1e6).toFixed(1) + " MB/s" : (b / 1e3).toFixed(0) + " KB/s"; }
function el(tag, attrs, parent, text) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (text != null) e.textContent = text;
  if (parent) parent.appendChild(e);
  return e;
}
function showTip(ev, txt) { tip.textContent = txt; tip.style.opacity = 1; tip.style.left = Math.min(ev.clientX + 14, innerWidth - tip.offsetWidth - 8) + "px"; tip.style.top = (ev.clientY + 14) + "px"; }
function hoverable(node, txt) { node.addEventListener("mousemove", e => showTip(e, txt)); node.addEventListener("mouseleave", () => { tip.style.opacity = 0; }); }

async function post(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-DW-Token": token }, body: JSON.stringify(body || {}) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || "request failed");
  return j;
}

/* ---------- Overview ---------- */
function ring(d) {
  const s = $("ring"); s.replaceChildren();
  const R = 90, C = 2 * Math.PI * R, cx = 110, cy = 110, tot = d.today.down + d.today.up, cap = d.limits.daily;
  el("circle", { cx, cy, r: R, fill: "none", stroke: css("--track"), "stroke-width": 18 }, s);
  if (cap <= 0) return;
  const f = Math.min(tot / cap, 1), pct = tot / cap * 100, w = d.settings.warn_percents;
  const col = pct >= 100 ? css("--crit") : pct >= (w[w.length - 1] || 80) ? css("--serious") : pct >= (w[0] || 50) ? css("--warn") : css("--good");
  const a = el("circle", { cx, cy, r: R, fill: "none", stroke: col, "stroke-width": 18, "stroke-linecap": "round", "stroke-dasharray": `${C * f} ${C}`, transform: `rotate(-90 ${cx} ${cy})` }, s);
  for (const p of w) {
    const ang = p / 100 * 2 * Math.PI - Math.PI / 2;
    el("line", { x1: cx + (R - 14) * Math.cos(ang), y1: cy + (R - 14) * Math.sin(ang), x2: cx + (R + 14) * Math.cos(ang), y2: cy + (R + 14) * Math.sin(ang), stroke: css("--ink2"), "stroke-width": 2 }, s);
    el("text", { x: cx + (R + 25) * Math.cos(ang), y: cy + (R + 25) * Math.sin(ang) + 4, "text-anchor": "middle" }, s, p + "%");
  }
  hoverable(a, fmt(tot) + " of " + fmt(cap));
}
function spark(h) {
  const s = $("spark"); s.replaceChildren(); if (h.length < 2) return;
  const W = 600, H = 70, mx = Math.max(1e5, ...h.map(p => Math.max(p[0], p[1])));
  [[0, "--down"], [1, "--up"]].forEach(([i, c]) => el("polyline", { points: h.map((p, k) => `${k / (h.length - 1) * W},${H - 3 - p[i] / mx * (H - 8)}`).join(" "), fill: "none", stroke: css(c), "stroke-width": 2, "stroke-linejoin": "round", "vector-effect": "non-scaling-stroke" }, s));
}
function bars(svg, items, o) {
  svg.replaceChildren();
  const W = 960, H = o.h, L = 48, B = 24, T = 8, iw = W - L - 8, n = items.length, bw = iw / n;
  const mx = Math.max(o.min, ...items.map(i => i.down + i.up)) * 1.08;
  for (let g = 0; g <= 4; g++) {
    const y = T + (H - T - B) * (1 - g / 4);
    el("line", { x1: L, x2: W - 8, y1: y, y2: y, stroke: css("--grid") }, svg);
    el("text", { x: L - 6, y: y + 4, "text-anchor": "end" }, svg, o.ylab(mx * g / 4));
  }
  items.forEach((it, i) => {
    const x = L + i * bw + bw * .14, w = bw * .72, hd = it.down / mx * (H - T - B), hu = it.up / mx * (H - T - B), y0 = H - B;
    if (hd > 0) el("rect", { x, y: y0 - hd, width: w, height: hd, rx: 3, fill: css("--down") }, svg);
    if (hu > 0) el("rect", { x, y: y0 - hd - hu - (hd > 0 ? 2 : 0), width: w, height: hu, rx: 3, fill: css("--up") }, svg);
    const hit = el("rect", { x: L + i * bw, y: T, width: bw, height: H - T - B, fill: "transparent" }, svg);
    hoverable(hit, it.label + ": " + fmt(it.down + it.up) + " (down " + fmt(it.down) + ", up " + fmt(it.up) + ")");
    if (o.every(i)) el("text", { x: x + w / 2, y: H - 6, "text-anchor": "middle" }, svg, it.tick);
  });
  for (const [v, dash] of (o.lines || [])) {
    const y = T + (H - T - B) * (1 - v / mx);
    if (v > 0 && y > T) el("line", { x1: L, x2: W - 8, y1: y, y2: y, stroke: css("--crit"), "stroke-width": 1.5, "stroke-dasharray": dash }, svg);
  }
}
function renderOverview(d) {
  const tot = d.today.down + d.today.up, cap = d.limits.daily, pct = cap > 0 ? tot / cap * 100 : 0, w = d.settings.warn_percents;
  $("used").textContent = fmt(tot);
  $("of").textContent = cap > 0 ? "of " + fmt(cap) + " today · " + Math.round(pct) + "%" : "today · no daily limit set";
  $("left").textContent = cap > 0 ? (pct >= 100 ? "Daily limit reached" : fmt(cap - tot) + " left today") : "Set a limit in the Limits tab";
  ring(d);
  const lvl = cap <= 0 ? ["good", "No limit set", "●"] : pct >= 100 ? ["crit", "Limit reached", "■"] : pct >= (w[w.length - 1] || 80) ? ["serious", "Close to the limit", "▲"] : pct >= (w[0] || 50) ? ["warn", "Over half used", "▲"] : ["good", "Within limit", "●"];
  $("pilltxt").textContent = lvl[1]; $("pillicon").textContent = lvl[2]; $("pillicon").style.color = css("--" + lvl[0]);
  const b = $("banner"); b.classList.toggle("on", cap > 0 && pct >= 100);
  if (pct >= 100) b.textContent = "Daily limit reached: " + fmt(tot) + " used of " + fmt(cap) + ".";
  $("sdown").textContent = rate(d.rate.down); $("sup").textContent = rate(d.rate.up);
  $("adapter").textContent = d.rate.adapter ? "· " + d.rate.adapter : ""; spark(d.rate.history);
  $("tdown").textContent = fmt(d.today.down); $("tup").textContent = fmt(d.today.up); $("tmonth").textContent = fmt(d.month);
  bars($("hours"), d.hours.map((v, h) => ({ down: v[0], up: v[1], label: String(h).padStart(2, "0") + ":00", tick: String(h).padStart(2, "0") })), { h: 190, min: 5e7, ylab: fmt, every: i => i % 3 === 0 });
  const days = d.days.map(x => ({ down: x.down, up: x.up, label: x.day, tick: x.day.slice(5) }));
  bars($("days"), days, { h: 230, min: Math.max(cap * 1.08, 5e8), ylab: v => (v / 1e9).toFixed(1) + " GB", every: () => true, lines: [[cap, "6 4"]] });
  $("limitkey").textContent = cap > 0 ? "— — daily limit " + fmt(cap) : "";
  const t = $("tbl"); t.replaceChildren();
  const hr = t.insertRow(); ["Day", "Down", "Up", "Total"].forEach(c => { const th = document.createElement("th"); th.textContent = c; hr.appendChild(th); });
  days.slice().reverse().forEach(x => { const r = t.insertRow(); [x.label, fmt(x.down), fmt(x.up), fmt(x.down + x.up)].forEach(v => { r.insertCell().textContent = v; }); });
}

/* ---------- Apps ---------- */
function renderApps(d) {
  const a = d.apps, t = $("apptbl"); t.replaceChildren();
  $("refresh").disabled = a.busy;
  $("appsnote").textContent = a.available
    ? "From Windows' own usage history (about the last 30–60 days). Last loaded " + new Date(a.made * 1000).toLocaleString() + "."
    : "Per-app numbers come from Windows' own usage history. Press the button once: Windows will ask for administrator permission, because that history is protected.";
  $("appsmsg").textContent = a.busy ? "Waiting for the Windows permission prompt…" : a.error || "";
  const rows = a[range] || [];
  if (!rows.length) { const r = t.insertRow(); const c = r.insertCell(); c.colSpan = 4; c.textContent = a.available ? "No data for this range." : ""; return; }
  const hr = t.insertRow(); ["App", "", "Down", "Total"].forEach(c => { const th = document.createElement("th"); th.textContent = c; hr.appendChild(th); });
  const mx = Math.max(...rows.map(r => r.down + r.up)) || 1;
  rows.forEach(r => {
    const tr = t.insertRow(); tr.insertCell().textContent = r.app;
    const bc = tr.insertCell(), bar = document.createElement("div"); bar.className = "bar"; bar.style.width = Math.max((r.down + r.up) / mx * 100, 1) + "%"; bc.appendChild(bar);
    tr.insertCell().textContent = fmt(r.down); tr.insertCell().textContent = fmt(r.down + r.up);
  });
}

/* ---------- Limits ---------- */
function drawAppLimits() {
  const box = $("applimits"); box.replaceChildren();
  Object.entries(appLimits).forEach(([app, mb]) => {
    const row = document.createElement("div"); row.className = "applimit";
    const s = document.createElement("span"); s.textContent = app + " — " + mb + " MB per day";
    const b = document.createElement("button"); b.type = "button"; b.className = "btn"; b.textContent = "Remove";
    b.addEventListener("click", () => { delete appLimits[app]; drawAppLimits(); });
    row.append(s, b); box.appendChild(row);
  });
}
function fillForm(d) {
  $("f-daily").value = d.settings.daily_limit_gb; $("f-monthly").value = d.settings.monthly_limit_gb;
  $("f-warn").value = d.settings.warn_percents.join(", "); appLimits = Object.assign({}, d.settings.app_limits_mb); drawAppLimits();
  $("f-auto").checked = d.autostart;
}

/* ---------- wiring ---------- */
function render() { if (!st) return; renderOverview(st); renderApps(st); if (!formReady) { fillForm(st); formReady = true; } }
async function tick() {
  try { const r = await fetch("/api/state", { cache: "no-store" }); st = await r.json(); token = st.token; render(); }
  catch (e) { $("pilltxt").textContent = "datawatch is not running"; $("pillicon").textContent = "■"; }
}
["overview", "apps", "limits"].forEach(n => $("tab-" + n).addEventListener("click", () => {
  ["overview", "apps", "limits"].forEach(m => { $("tab-" + m).setAttribute("aria-selected", String(m === n)); $("view-" + m).hidden = m !== n; });
}));
["today", "week", "month", "all"].forEach(k => $("r-" + k).addEventListener("click", () => {
  range = k; ["today", "week", "month", "all"].forEach(m => $("r-" + m).setAttribute("aria-pressed", String(m === k))); render();
}));
$("refresh").addEventListener("click", async () => { try { await post("/api/apps/refresh"); $("appsmsg").textContent = "Waiting for the Windows permission prompt…"; } catch (e) { $("appsmsg").textContent = e.message; } });
$("addapp").addEventListener("click", () => {
  const n = $("n-app").value.trim().toLowerCase(), mb = parseFloat($("n-mb").value);
  if (!n || !(mb >= 1)) { $("savemsg").textContent = "Enter an app name and a number of MB."; return; }
  appLimits[n] = mb; $("n-app").value = ""; $("n-mb").value = ""; drawAppLimits();
});
$("limitform").addEventListener("submit", async ev => {
  ev.preventDefault();
  const warn = $("f-warn").value.split(",").map(s => s.trim()).filter(Boolean).map(Number);
  try {
    const j = await post("/api/settings", { daily_limit_gb: parseFloat($("f-daily").value || "0"), monthly_limit_gb: parseFloat($("f-monthly").value || "0"), warn_percents: warn, app_limits_mb: appLimits });
    st.settings = j.settings; $("savemsg").textContent = "Saved."; formReady = false; tick();
  } catch (e) { $("savemsg").textContent = e.message; }
});
$("f-auto").addEventListener("change", async () => { try { await post("/api/autostart", { enabled: $("f-auto").checked }); } catch (e) { $("savemsg").textContent = e.message; } });
$("quit").addEventListener("click", async () => { try { await post("/api/quit"); } catch (e) { /* server closed */ } $("pilltxt").textContent = "datawatch stopped"; });
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", render);
tick(); setInterval(tick, 2000);
