"use strict";
const NS = "http://www.w3.org/2000/svg";
const $ = id => document.getElementById(id);
const tip = $("tip");
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
let st = null, token = "", range = "today", formReady = false, appLimits = {}, ringBuilt = false, firstAppsOpen = true;

/* ---------- helpers ---------- */
function fmt(b) { b = +b || 0; return b >= 1e9 ? (b / 1e9).toFixed(2) + " GB" : b >= 1e6 ? (b / 1e6).toFixed(b >= 1e8 ? 0 : 1) + " MB" : (b / 1e3).toFixed(0) + " KB"; }
function rate(b) { b = +b || 0; return b >= 1e6 ? (b / 1e6).toFixed(1) + " MB/s" : (b / 1e3).toFixed(0) + " KB/s"; }
function el(tag, attrs, parent, text) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (text != null) e.textContent = text;
  if (parent) parent.appendChild(e);
  return e;
}
function h(tag, props, ...kids) {
  const e = document.createElement(tag);
  for (const k in (props || {})) { if (k === "class") e.className = props[k]; else e.setAttribute(k, props[k]); }
  kids.forEach(k => e.append(k));
  return e;
}
const HUES = [212, 262, 330, 24, 152, 190, 44, 290];
function appIcon(r, have) {
  const box = h("span", { class: "appicon" });
  const letter = () => { box.replaceChildren(); box.classList.add("letter"); box.dataset.h = String(HUES[(r.app.charCodeAt(0) + r.app.length) % HUES.length]); box.textContent = (r.app.replace(/[^a-z0-9]/gi, "")[0] || "?").toUpperCase(); };
  if (r.app.startsWith("(system")) { box.classList.add("sys"); box.append(icon("i-cog")); return box; }
  if (have.has(r.id)) {
    const img = h("img", { src: "/icon/" + r.id + ".png", alt: "", width: "24", height: "24", loading: "lazy" });
    img.addEventListener("error", letter); box.append(img);
  } else letter();
  return box;
}
function icon(id) { const s = el("svg", { class: "i" }); el("use", { href: "#" + id }, s); return s; }
function showTipAt(x, y, txt) { tip.textContent = txt; tip.style.opacity = 1; tip.style.left = Math.max(8, Math.min(x, innerWidth - tip.offsetWidth - 8)) + "px"; tip.style.top = y + "px"; }
function hideTip() { tip.style.opacity = 0; }
function hoverable(node, txt) {
  node.addEventListener("mousemove", e => showTipAt(e.clientX + 14, e.clientY + 14, txt));
  node.addEventListener("mouseleave", hideTip);
  node.addEventListener("focus", () => { const r = node.getBoundingClientRect(); showTipAt(r.left, r.top - 40, txt); });
  node.addEventListener("blur", hideTip);
}
let toastTimer = 0;
function toast(msg) { const t = $("toast"); t.textContent = msg; t.classList.add("on"); clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("on"), 2600); }
async function post(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-DW-Token": token }, body: JSON.stringify(body || {}) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || "request failed");
  return j;
}

/* ---------- theme ---------- */
const THEMES = [["auto", "i-auto", "Automatic"], ["light", "i-sun", "Light"], ["dark", "i-moon", "Dark"]];
function applyTheme(mode) {
  const root = document.documentElement;
  if (mode === "auto") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", mode);
  const t = THEMES.find(x => x[0] === mode) || THEMES[0];
  $("themeuse").setAttribute("href", "#" + t[1]); $("theme").setAttribute("aria-label", "Theme: " + t[2]); $("theme").title = "Theme: " + t[2];
  render();
}
function currentTheme() { try { return localStorage.getItem("dw-theme") || "auto"; } catch (e) { return "auto"; } }
$("theme").addEventListener("click", () => {
  const next = THEMES[(THEMES.findIndex(x => x[0] === currentTheme()) + 1) % 3][0];
  try { localStorage.setItem("dw-theme", next); } catch (e) { /* private mode */ }
  applyTheme(next);
});

/* ---------- Overview ---------- */
const R = 96, C = 2 * Math.PI * R, CX = 120, CY = 120;
let arc, ticks;
function levelOf(pct, w) { return pct >= 100 ? 3 : pct >= (w[w.length - 1] || 80) ? 2 : pct >= (w[0] || 50) ? 1 : 0; }
const LEVEL = [["good", "Within limit", "i-check", "--ring-good"], ["warn", "Over half used", "i-alert", "--ring-warn"], ["serious", "Close to the limit", "i-alert", "--ring-serious"], ["crit", "Limit reached", "i-stop", "--ring-crit"]];
function buildRing() {
  const s = $("ring");
  el("circle", { cx: CX, cy: CY, r: R, fill: "none", stroke: "var(--track)", "stroke-width": 20 }, s);
  arc = el("circle", { class: "arc", cx: CX, cy: CY, r: R, fill: "none", "stroke-width": 20, "stroke-linecap": "round", "stroke-dasharray": `0 ${C}`, transform: `rotate(-90 ${CX} ${CY})`, tabindex: 0 }, s);
  ticks = el("g", {}, s); ringBuilt = true;
  arc.addEventListener("mousemove", e => showTipAt(e.clientX + 14, e.clientY + 14, arc.dataset.tip || ""));
  arc.addEventListener("mouseleave", hideTip);
  arc.addEventListener("focus", () => { const r = arc.getBoundingClientRect(); showTipAt(r.left + r.width / 2, r.top, arc.dataset.tip || ""); });
  arc.addEventListener("blur", hideTip);
}
function drawRing(d, tot, cap, lvl) {
  if (!ringBuilt) buildRing();
  const f = cap > 0 ? Math.min(tot / cap, 1) : 0;
  arc.setAttribute("stroke", css(LEVEL[lvl][3]));
  arc.setAttribute("stroke-dasharray", `${Math.max(C * f, f > 0 ? 0.01 : 0)} ${C}`);
  arc.dataset.tip = cap > 0 ? fmt(tot) + " of " + fmt(cap) : fmt(tot);
  ticks.replaceChildren();
  if (cap <= 0) return;
  for (const p of d.settings.warn_percents) {
    const a = p / 100 * 2 * Math.PI - Math.PI / 2, c = Math.cos(a), s = Math.sin(a);
    el("line", { x1: CX + (R - 16) * c, y1: CY + (R - 16) * s, x2: CX + (R + 15) * c, y2: CY + (R + 15) * s, stroke: css("--ink2"), "stroke-width": 2, "stroke-linecap": "round" }, ticks);
    el("text", { x: CX + (R + 27) * c, y: CY + (R + 27) * s + 4, "text-anchor": "middle" }, ticks, p + "%");
  }
}

function spark(hist) {
  const s = $("spark"); s.replaceChildren(); if (hist.length < 2) return;
  const W = 600, H = 64, mx = Math.max(1e5, ...hist.map(p => Math.max(p[0], p[1])));
  [[0, "--down"], [1, "--up"]].forEach(([i, c]) => el("polyline", { points: hist.map((p, k) => `${k / (hist.length - 1) * W},${H - 3 - p[i] / mx * (H - 8)}`).join(" "), fill: "none", stroke: css(c), "stroke-width": 2, "stroke-linejoin": "round", "vector-effect": "non-scaling-stroke" }, s));
}
function bars(svg, items, o) {
  svg.replaceChildren();
  const W = 960, Hh = o.h, L = 52, B = 24, T = 10, iw = W - L - 8, n = items.length, bw = iw / n;
  const mx = Math.max(o.min, ...items.map(i => i.down + i.up)) * 1.08;
  for (let g = 0; g <= 4; g++) {
    const y = T + (Hh - T - B) * (1 - g / 4);
    el("line", { x1: L, x2: W - 8, y1: y, y2: y, stroke: css("--grid") }, svg);
    el("text", { x: L - 8, y: y + 4, "text-anchor": "end" }, svg, o.ylab(mx * g / 4));
  }
  items.forEach((it, i) => {
    const x = L + i * bw + bw * .16, w = bw * .68, hd = it.down / mx * (Hh - T - B), hu = it.up / mx * (Hh - T - B), y0 = Hh - B;
    if (hd > 0) el("rect", { x, y: y0 - hd, width: w, height: hd, rx: 3, fill: css("--down") }, svg);
    if (hu > 0) el("rect", { x, y: y0 - hd - hu - (hd > 0 ? 2 : 0), width: w, height: hu, rx: 3, fill: css("--up") }, svg);
    const hit = el("rect", { class: "hit", x: L + i * bw, y: T, width: bw, height: Hh - T - B, tabindex: 0, rx: 4, role: "img", "aria-label": it.label + ": " + fmt(it.down + it.up) }, svg);
    hoverable(hit, it.label + ": " + fmt(it.down + it.up) + " (down " + fmt(it.down) + ", up " + fmt(it.up) + ")");
    if (o.every(i)) el("text", { x: x + w / 2, y: Hh - 6, "text-anchor": "middle", class: it.now ? "strong" : "" }, svg, it.tick);
  });
  for (const [v, dash] of (o.lines || [])) {
    const y = T + (Hh - T - B) * (1 - v / mx);
    if (v > 0 && y > T) el("line", { x1: L, x2: W - 8, y1: y, y2: y, stroke: css("--crit"), "stroke-width": 1.5, "stroke-dasharray": dash }, svg);
  }
}
function meter(prefix, used, cap) {
  const box = $("prog-" + prefix), on = cap > 0;
  box.hidden = !on; if (!on) return;
  const pct = used / cap * 100, f = $(prefix === "daily" ? "pd-fill" : "pm-fill");
  f.className = ["", "w1", "w2", "w3"][levelOf(pct, st.settings.warn_percents)];
  f.style.width = Math.min(pct, 100) + "%";
  $(prefix === "daily" ? "pd-txt" : "pm-txt").textContent = fmt(used) + " of " + fmt(cap) + " · " + Math.round(pct) + "%";
  $(prefix === "daily" ? "pd-bar" : "pm-bar").setAttribute("aria-valuenow", String(Math.round(Math.min(pct, 100))));
}
function renderOverview(d) {
  const tot = d.today.down + d.today.up, cap = d.limits.daily, pct = cap > 0 ? tot / cap * 100 : 0, lvl = cap > 0 ? levelOf(pct, d.settings.warn_percents) : 0;
  $("used").textContent = fmt(tot);
  $("of").textContent = cap > 0 ? "of " + fmt(cap) + " · " + Math.round(pct) + "%" : "today";
  $("left").textContent = cap > 0 ? (pct >= 100 ? "Daily limit reached" : fmt(cap - tot) + " left today") : "No daily limit set";
  drawRing(d, tot, cap, lvl);
  const L = cap > 0 ? LEVEL[lvl] : ["good", "No limit set", "i-check"];
  $("pill").className = "pill " + L[0]; $("pilltxt").textContent = L[1]; $("pilluse").setAttribute("href", "#" + L[2]);
  const b = $("banner"); b.classList.toggle("on", cap > 0 && pct >= 100);
  if (pct >= 100) b.textContent = "Daily limit reached: " + fmt(tot) + " used of " + fmt(cap) + ".";
  $("headline").textContent = cap <= 0 ? "No daily limit set" : pct >= 100 ? "You are over your daily limit" : lvl >= 1 ? "Watch your usage today" : "You're on track today";
  const now = new Date(), secs = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds();
  $("pace").textContent = cap > 0 && secs > 7200 && pct < 100 ? "At this pace you will use about " + fmt(tot / secs * 86400) + " by midnight." : cap > 0 ? "" : "Set one in the Limits tab.";
  meter("daily", tot, cap); meter("monthly", d.month, d.limits.monthly);
  $("sdown").textContent = rate(d.rate.down); $("sup").textContent = rate(d.rate.up);
  $("adapter").textContent = d.rate.adapter ? "· " + d.rate.adapter : ""; spark(d.rate.history);
  $("tdown").textContent = fmt(d.today.down); $("tup").textContent = fmt(d.today.up); $("tmonth").textContent = fmt(d.month);
  const used14 = d.days.filter(x => x.down + x.up > 0); $("tavg").textContent = used14.length ? fmt(used14.reduce((a, x) => a + x.down + x.up, 0) / used14.length) : "0 KB";
  const hr = now.getHours();
  bars($("hours"), d.hours.map((v, i) => ({ down: v[0], up: v[1], label: String(i).padStart(2, "0") + ":00", tick: String(i).padStart(2, "0"), now: i === hr })), { h: 190, min: 5e7, ylab: fmt, every: i => i % 3 === 0 || i === hr });
  const days = d.days.map((x, i) => ({ down: x.down, up: x.up, label: x.day, tick: x.day.slice(5), now: i === d.days.length - 1 }));
  bars($("days"), days, { h: 230, min: Math.max(cap * 1.08, 5e8), ylab: v => (v / 1e9).toFixed(1) + " GB", every: () => true, lines: [[cap, "6 4"]] });
  $("limitkey").textContent = cap > 0 ? "— — daily limit " + fmt(cap) : "";
  const t = $("tbl"); t.replaceChildren();
  const th = h("thead"), tr = h("tr"); ["Day", "Down", "Up", "Total"].forEach(c => tr.append(h("th", {}, c))); th.append(tr); t.append(th);
  const tb = h("tbody"); days.slice().reverse().forEach(x => { const r = h("tr"); [x.label, fmt(x.down), fmt(x.up), fmt(x.down + x.up)].forEach(v => r.append(h("td", {}, v))); tb.append(r); }); t.append(tb);
}

/* ---------- Apps ---------- */
function renderApps(d) {
  const a = d.apps, t = $("apptbl"); t.replaceChildren();
  $("refresh").disabled = a.busy;
  $("refreshtxt").textContent = a.busy ? "Reading Windows history…" : a.available ? "Refresh" : "Load per-app data";
  $("appsnote").textContent = a.available ? "Windows history · loaded " + new Date(a.made * 1000).toLocaleString() : "";
  const msg = $("appsmsg"); msg.replaceChildren();
  if (a.busy) msg.append(h("span", { class: "spin", "aria-hidden": "true" }), " Waiting for Windows (about 30 seconds)…");
  else if (a.error) msg.textContent = a.error;
  const q = $("appsearch").value.trim().toLowerCase();
  const rows = (a[range] || []).filter(r => !q || r.app.includes(q));
  const empty = $("appsempty");
  if (!rows.length) {
    empty.hidden = false;
    $("emptytitle").textContent = !a.available ? "No per-app data yet" : q ? "No app matches that filter" : "Nothing recorded for this range";
    $("emptytext").replaceChildren(...(!a.available ? ["Windows keeps per-app history in a protected file. Press ", h("b", {}, "Load per-app data"), " once to read it. Windows may ask for administrator permission."] : [q ? "Try a different name." : "Try a longer range."]));
    return;
  }
  empty.hidden = true;
  const haveIcons = new Set(a.icons || []);
  const total = rows.reduce((s, r) => s + r.down + r.up, 0) || 1, mx = Math.max(...rows.map(r => r.down + r.up)) || 1;
  const th = h("thead"), tr = h("tr"); ["App", "", "Share", "Down", "Total", ""].forEach(c => tr.append(h("th", {}, c))); th.append(tr); t.append(th);
  const tb = h("tbody");
  rows.forEach(r => {
    const row = h("tr"), bar = h("div", { class: "usebar" }); bar.style.width = Math.max((r.down + r.up) / mx * 100, 1) + "%";
    const lim = h("button", { type: "button", class: "btn sm", "aria-label": "Set a daily limit for " + r.app }, "Set limit");
    lim.addEventListener("click", () => { selectTab("limits"); $("n-app").value = r.app; $("n-mb").focus(); });
    row.append(h("td", {}, h("div", { class: "appname" }, appIcon(r, haveIcons), h("span", {}, r.app))), h("td", { class: "barcell" }, bar), h("td", {}, Math.round((r.down + r.up) / total * 100) + "%"),
      h("td", {}, fmt(r.down)), h("td", { class: "num" }, fmt(r.down + r.up)), h("td", {}, lim));
    tb.append(row);
  });
  t.append(tb);
}

/* ---------- Limits ---------- */
function drawAppLimits() {
  const box = $("applimits"); box.replaceChildren();
  const entries = Object.entries(appLimits);
  if (!entries.length) box.append(h("div", { class: "muted" }, "No per-app limits yet."));
  entries.forEach(([app, mb]) => {
    const b = h("button", { type: "button", class: "btn sm", "aria-label": "Remove limit for " + app }, "Remove");
    b.addEventListener("click", () => { delete appLimits[app]; drawAppLimits(); });
    box.append(h("div", { class: "applimit" }, h("span", {}, h("b", {}, app), " — " + mb + " MB per day"), b));
  });
}
function fillForm(d) {
  $("f-daily").value = d.settings.daily_limit_gb; $("f-monthly").value = d.settings.monthly_limit_gb;
  $("f-warn").value = d.settings.warn_percents.join(", "); appLimits = Object.assign({}, d.settings.app_limits_mb); drawAppLimits();
  $("f-auto").checked = d.autostart; markPreset();
}
function markPreset() { const v = parseFloat($("f-daily").value); document.querySelectorAll("#presets .chip").forEach(c => c.setAttribute("aria-pressed", String(parseFloat(c.dataset.gb) === v))); }
function fieldErr(id, msg) { $("e-" + id).textContent = msg || ""; const i = $({ daily: "f-daily", monthly: "f-monthly", warn: "f-warn" }[id]); if (i) i.setAttribute("aria-invalid", String(!!msg)); }

/* ---------- wiring ---------- */
function render() { if (!st) return; renderOverview(st); renderApps(st); if (!formReady) { fillForm(st); formReady = true; } }
async function tick() {
  try { const r = await fetch("/api/state", { cache: "no-store" }); st = await r.json(); token = st.token; render(); }
  catch (e) { $("pill").className = "pill crit"; $("pilltxt").textContent = "datawatch is not running"; $("pilluse").setAttribute("href", "#i-stop"); }
}
function selectTab(n) {
  ["overview", "apps", "limits"].forEach(m => { $("tab-" + m).setAttribute("aria-selected", String(m === n)); $("view-" + m).hidden = m !== n; });
  hideTip(); if (n === "overview") render();
}
const tabs = ["overview", "apps", "limits"];
tabs.forEach((n, i) => {
  $("tab-" + n).addEventListener("click", () => selectTab(n));
  $("tab-" + n).addEventListener("keydown", e => {
    const j = e.key === "ArrowRight" ? (i + 1) % 3 : e.key === "ArrowLeft" ? (i + 2) % 3 : -1;
    if (j >= 0) { e.preventDefault(); selectTab(tabs[j]); $("tab-" + tabs[j]).focus(); }
  });
});
["today", "week", "month", "all"].forEach(k => $("r-" + k).addEventListener("click", () => {
  range = k; ["today", "week", "month", "all"].forEach(m => $("r-" + m).setAttribute("aria-pressed", String(m === k))); render();
}));
$("appsearch").addEventListener("input", render);
$("refresh").addEventListener("click", async () => { try { await post("/api/apps/refresh"); tick(); } catch (e) { toast(e.message); } });
document.querySelectorAll("#presets .chip").forEach(c => c.addEventListener("click", () => { $("f-daily").value = c.dataset.gb; markPreset(); }));
$("f-daily").addEventListener("input", markPreset);
$("addapp").addEventListener("click", () => {
  const n = $("n-app").value.trim().toLowerCase(), mb = parseFloat($("n-mb").value);
  if (!n || !(mb >= 1)) { $("e-app").textContent = "Enter an app name and a number of MB (1 or more)."; return; }
  $("e-app").textContent = ""; appLimits[n] = mb; $("n-app").value = ""; $("n-mb").value = ""; drawAppLimits();
});
$("limitform").addEventListener("submit", async ev => {
  ev.preventDefault();
  ["daily", "monthly", "warn"].forEach(k => fieldErr(k, ""));
  const daily = parseFloat($("f-daily").value || "0"), monthly = parseFloat($("f-monthly").value || "0");
  const warn = $("f-warn").value.split(",").map(s => s.trim()).filter(Boolean).map(Number);
  let bad = false;
  if (!(daily >= 0 && daily <= 100000)) { fieldErr("daily", "Enter a number from 0 to 100000."); bad = true; }
  if (!(monthly >= 0 && monthly <= 1000000)) { fieldErr("monthly", "Enter a number from 0 to 1000000."); bad = true; }
  if (warn.some(x => !Number.isInteger(x) || x < 1 || x > 99) || warn.length > 5) { fieldErr("warn", "Use up to 5 whole numbers from 1 to 99, like 50, 80."); bad = true; }
  if (bad) return;
  try {
    const j = await post("/api/settings", { daily_limit_gb: daily, monthly_limit_gb: monthly, warn_percents: warn, app_limits_mb: appLimits });
    st.settings = j.settings; formReady = false; toast("Limits saved"); tick();
  } catch (e) { toast(e.message); }
});
$("f-auto").addEventListener("change", async () => { try { await post("/api/autostart", { enabled: $("f-auto").checked }); toast($("f-auto").checked ? "Will start with Windows" : "Won't start with Windows"); } catch (e) { toast(e.message); } });
$("quit").addEventListener("click", async () => { try { await post("/api/quit"); } catch (e) { /* server closed */ } $("pilltxt").textContent = "datawatch stopped"; });
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", render);
applyTheme(currentTheme());
tick(); setInterval(tick, 2000);
