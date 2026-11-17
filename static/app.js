// Placement Copilot – frontend (vanilla JS, no build step)
const ICON = { resume: "📄", jobs: "🔎", gap: "🧩", roadmap: "🗺️", interview: "🎤", progress: "📈", orchestrator: "⬡" };
const ROLES = ["Software Engineer", "Full Stack Developer", "Frontend Developer", "Backend Developer", "Data Analyst",
  "Machine Learning Engineer", "DevOps Engineer", "Android Developer", "Data Scientist", "Cloud Engineer"];

let cfg = null;
let sid = localStorage.getItem("pc_sid");
let st = null;
let stJson = "";
let view = "dashboard";
let lastEventId = 0;
let nodeState = {};
let pending = false; // an action was just submitted; keep polling until it settles
const drafts = {};

const $ = (s, el = document) => el.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const labelOf = (name) => (cfg?.agents.find((a) => a.name === name) || {}).label || (name === "orchestrator" ? "Orchestrator" : name);

async function api(method, path, body, form = false) {
  const opts = { method, headers: {} };
  if (body && form) opts.body = body;
  else if (body) { opts.body = JSON.stringify(body); opts.headers["Content-Type"] = "application/json"; }
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `Request failed (${r.status})`);
  return data;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove("show"), 3200);
}

// ---------------------------------------------------------------- boot
async function boot() {
  cfg = await api("GET", "/api/config");
  const pill = $("#llmPill");
  pill.textContent = cfg.llm_enabled ? `LLM · ${cfg.model}` : "Offline mode (no LLM key)";
  pill.className = "pill " + (cfg.llm_enabled ? "on" : "off");
  $("#nav").addEventListener("click", (e) => { const a = e.target.closest("a[data-view]"); if (a) go(a.dataset.view); });
  $("#newStudentBtn").onclick = () => { sid = null; localStorage.removeItem("pc_sid"); st = null; resetFeed(); go("dashboard"); refreshStudents(); };
  $("#studentSelect").onchange = (e) => selectStudent(e.target.value);
  renderPipeline();
  await refreshStudents();
  if (sid) await selectStudent(sid); else render();
  setInterval(tick, 1000);
}

async function refreshStudents() {
  const list = await api("GET", "/api/students");
  const sel = $("#studentSelect");
  sel.innerHTML = `<option value="">${list.length ? "Select student…" : "No students yet"}</option>` +
    list.map((s) => `<option value="${s.id}" ${s.id === sid ? "selected" : ""}>${esc(s.name)} · ${esc(s.target_role || "")}${s.readiness != null ? ` · ${s.readiness}%` : ""}</option>`).join("");
  if (sid && !list.some((s) => s.id === sid)) { sid = null; localStorage.removeItem("pc_sid"); }
}

async function selectStudent(id) {
  if (!id) return;
  sid = id;
  localStorage.setItem("pc_sid", id);
  resetFeed();
  await loadState(true);
  await pollEvents();
}

function resetFeed() { lastEventId = 0; nodeState = {}; $("#feed").innerHTML = ""; renderPipeline(); }

async function loadState(force = false) {
  if (!sid) return;
  try { st = await api("GET", `/api/students/${sid}`); } catch { sid = null; st = null; localStorage.removeItem("pc_sid"); render(); return; }
  const j = JSON.stringify(st);
  if (force || j !== stJson) { stJson = j; render(); }
  $("#busyDot").classList.toggle("busy", st.status === "running");
}

async function tick() {
  if (!sid || document.hidden) return;
  const n = await pollEvents();
  if (n || pending || st?.status === "running") {
    await loadState();
    if (st && st.status !== "running" && pending) { pending = false; refreshStudents(); }
  }
}

async function submit(path, body, form = false) {
  try {
    await api("POST", path, body, form);
    pending = true;
    if (st) { st.status = "running"; $("#busyDot").classList.add("busy"); }
    render();
  } catch (e) { toast(e.message); }
}

function go(v) {
  view = v;
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === v));
  render();
}

// ---------------------------------------------------------------- activity feed
async function pollEvents() {
  if (!sid) return 0;
  const evs = await api("GET", `/api/students/${sid}/events?after=${lastEventId}`).catch(() => []);
  if (!evs.length) return 0;
  const feed = $("#feed");
  const atBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 60;
  for (const e of evs) {
    lastEventId = e.id;
    trackNode(e);
    const t = new Date(e.ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const div = document.createElement("div");
    div.className = `ev ${e.kind}`;
    div.innerHTML = `<div class="bar"></div><div><div class="who">${ICON[e.agent] || "•"} ${esc(labelOf(e.agent))}<span class="time">${t}</span></div>${esc(e.message)}</div>`;
    feed.appendChild(div);
  }
  while (feed.children.length > 250) feed.removeChild(feed.firstChild);
  if (atBottom || evs.length > 20) feed.scrollTop = feed.scrollHeight;
  renderPipeline();
  return evs.length;
}

function trackNode(e) {
  if (e.agent === "orchestrator" && e.kind === "event") nodeState = {};
  if (e.kind === "route") {
    const label = e.message.split("→ ")[1];
    const a = cfg.agents.find((x) => x.label === label);
    if (a) nodeState[a.name] = "active";
  }
  if (e.kind === "done" && e.agent !== "orchestrator") nodeState[e.agent] = "done";
}

function renderPipeline() {
  if (!cfg) return;
  $("#pipeline").innerHTML = cfg.agents.map((a) =>
    `<div class="node ${nodeState[a.name] || ""}" title="${esc(a.description)}"><b>${ICON[a.name]}</b>${esc(a.label)}</div>`).join("");
}

// ---------------------------------------------------------------- render
function render() {
  const main = $("#main");
  if (!sid || !st) { main.innerHTML = onboardingView(); bindUploader(); return; }
  if (!st.profile && view !== "agents") {
    main.innerHTML = st.status === "running" ? workingView("Agents are analysing your resume…") : onboardingView(true);
    bindUploader();
    return;
  }
  const views = { dashboard: dashboardView, resume: resumeView, jobs: jobsView, gaps: gapsView, roadmap: roadmapView, interview: interviewView, agents: agentsView };
  main.innerHTML = (views[view] || dashboardView)();
  bindView();
}

function workingView(msg) {
  return `<div class="card empty"><div class="h2"><span class="loader"></span>${esc(msg)}</div>
    <p class="muted">Watch the agents hand work to each other in the activity panel →</p></div>`;
}

function onboardingView(existing = false) {
  return `
  <div class="page-head"><div><div class="h1">Start your placement prep</div>
  <div class="muted">Upload a resume. Six agents will analyse it, find matching jobs, find your skill gaps, plan your learning and track readiness.</div></div></div>
  <div class="grid g2">
    <div class="card">
      ${existing ? `<div class="muted small" style="margin-bottom:12px">Workspace: <b>${esc(st.name)}</b></div>` : `
      <div class="field"><label>Your name</label><input id="obName" placeholder="e.g. Riya Verma" /></div>`}
      <div class="field"><label>Target role</label>
        <input id="obRole" list="roles" value="${esc(st?.target_role || "Full Stack Developer")}" />
        <datalist id="roles">${ROLES.map((r) => `<option>${r}</option>`).join("")}</datalist></div>
      ${uploaderHtml()}
    </div>
    <div class="card">
      <div class="h2" style="margin-bottom:10px">What happens next</div>
      <ol class="clean muted" style="padding-left:18px">
        <li><b>${ICON.resume} Resume Analyst</b> builds a structured profile and scores your resume for ATS.</li>
        <li><b>${ICON.jobs} Job Scout</b> ranks openings against your skills.</li>
        <li><b>${ICON.gap} Skill Gap Analyzer</b> compares you with the best-fit job description.</li>
        <li><b>${ICON.roadmap} Roadmap Planner</b> writes a week-by-week plan.</li>
        <li><b>${ICON.progress} Progress Tracker</b> scores your placement readiness.</li>
        <li><b>${ICON.interview} Mock Interviewer</b> runs a mock interview when you start one. Weak answers send new topics back to the roadmap.</li>
      </ol>
      <p class="muted small">An event-driven orchestrator coordinates all six agents, and every step appears in the activity panel.</p>
    </div>
  </div>`;
}

function uploaderHtml() {
  return `
    <div class="field"><label>Resume (PDF, DOCX or TXT)</label>
      <div class="drop" id="drop"><input type="file" id="file" accept=".pdf,.docx,.txt" hidden />
        <div id="dropText">Drop a file here or <a>browse</a></div></div></div>
    <div class="field"><label>…or paste resume text</label><textarea id="resumeText" placeholder="Paste your resume here"></textarea></div>
    <div class="row between"><button class="btn ghost sm" id="sampleBtn">Use sample resume</button>
      <button class="btn" id="runBtn">Run copilot →</button></div>`;
}

function bindUploader() {
  const drop = $("#drop");
  if (!drop) return;
  const file = $("#file");
  drop.onclick = () => file.click();
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); file.files = e.dataTransfer.files; showFile(); };
  file.onchange = showFile;
  function showFile() { if (file.files[0]) $("#dropText").textContent = `📎 ${file.files[0].name}`; }
  $("#sampleBtn").onclick = async (e) => { e.preventDefault(); $("#resumeText").value = (await api("GET", "/api/sample-resume")).text; };
  $("#runBtn").onclick = runCopilot;
}

async function runCopilot() {
  const file = $("#file").files[0];
  const text = $("#resumeText").value.trim();
  const role = ($("#obRole")?.value || "").trim() || "Software Engineer";
  if (!file && text.split(/\s+/).length < 30) return toast("Upload a resume file or paste at least a few lines");
  $("#runBtn").disabled = true;
  try {
    if (!sid || !st) {
      const name = ($("#obName")?.value || "").trim() || "Student";
      sid = (await api("POST", "/api/students", { name, target_role: role })).id;
      localStorage.setItem("pc_sid", sid);
      resetFeed();
    }
    const fd = new FormData();
    if (file) fd.append("file", file); else fd.append("text", text);
    fd.append("target_role", role);
    await api("POST", `/api/students/${sid}/resume`, fd, true);
    pending = true;
    view = "dashboard";
    go("dashboard");
    await loadState(true);
    await refreshStudents();
  } catch (e) { toast(e.message); $("#runBtn").disabled = false; }
}

// ---------------------------------------------------------------- dashboard
function ring(value) {
  const r = 64, c = 2 * Math.PI * r, off = c * (1 - value / 100);
  return `<div class="ring"><svg width="150" height="150"><circle cx="75" cy="75" r="${r}" stroke="#243049" stroke-width="12" fill="none"/>
    <circle cx="75" cy="75" r="${r}" stroke="url(#gr)" stroke-width="12" fill="none" stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${off}" style="transition:stroke-dashoffset .8s"/>
    <defs><linearGradient id="gr"><stop offset="0" stop-color="#6d8cff"/><stop offset="1" stop-color="#39d0b4"/></linearGradient></defs></svg>
    <div class="val"><div><b>${value}%</b><span class="muted small">ready</span></div></div></div>`;
}

function sparkline(hist) {
  if (!hist || hist.length < 2) return `<div class="muted small">Readiness history appears here as you make progress.</div>`;
  const w = 520, h = 90, pts = hist.map((p, i) => [(i / (hist.length - 1)) * w, h - (p.readiness / 100) * (h - 10) - 5]);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="none">
    <path d="${d} L${w},${h} L0,${h} Z" fill="rgba(109,140,255,.12)"/><path d="${d}" fill="none" stroke="#6d8cff" stroke-width="2.5"/>
    ${pts.map((p) => `<circle cx="${p[0]}" cy="${p[1]}" r="3" fill="#39d0b4"/>`).join("")}</svg>`;
}

function meterRow(label, v) {
  return `<div style="margin-bottom:12px"><div class="row between small"><span>${esc(label)}</span><b>${v}%</b></div><div class="meter"><div style="width:${v}%"></div></div></div>`;
}

function dashboardView() {
  const p = st.progress || { readiness: 0, components: {}, next_actions: [], level: "Getting started" };
  const c = p.components || {};
  const target = st.jobs.find((j) => j.id === st.target_job_id);
  const running = st.status === "running" ? `<span class="tag"><span class="loader"></span>agents working</span>` : "";
  return `
  <div class="page-head"><div><div class="h1">Hi ${esc(st.name.split(" ")[0])} 👋</div>
    <div class="muted">Target role: ${esc(st.target_role)}${target ? ` · Best-fit opening: <b>${esc(target.title)}</b> at ${esc(target.company)}` : ""}</div></div>${running}</div>
  <div class="grid" style="grid-template-columns: 1.1fr 1fr; margin-bottom:16px">
    <div class="card row" style="gap:28px">
      ${ring(p.readiness)}
      <div style="flex:1">
        <div class="h2">${esc(p.level)}</div>
        <div class="muted small" style="margin-bottom:14px">Weighted: resume 20% · skills 30% · roadmap 25% · interviews 25%</div>
        ${meterRow("Resume (ATS)", c.resume || 0)}${meterRow("Skill match", c.skills || 0)}
        ${meterRow("Roadmap done", c.roadmap || 0)}${meterRow("Interview avg", c.interview || 0)}
      </div>
    </div>
    <div class="card">
      <div class="h2" style="margin-bottom:10px">Next best actions</div>
      ${p.next_actions?.length ? `<ul class="clean">${p.next_actions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>` : `<div class="muted">No actions yet.</div>`}
      ${p.coach_note ? `<div class="card" style="background:var(--panel-2);margin-top:12px;padding:12px"><div class="small muted">${ICON.progress} Coach note</div>${esc(p.coach_note)}</div>` : ""}
    </div>
  </div>
  <div class="grid g4" style="margin-bottom:16px">
    ${stat(st.ats?.score ?? "–", "ATS score", "resume")}
    ${stat((st.gaps?.match_pct ?? "–") + (st.gaps ? "%" : ""), "Core skills matched", "gaps")}
    ${stat(`${p.tasks_done || 0}/${p.tasks_total || 0}`, "Roadmap tasks done", "roadmap")}
    ${stat(p.interviews_taken || 0, "Mock interviews", "interview")}
  </div>
  <div class="card"><div class="row between" style="margin-bottom:8px"><div class="h2">Readiness over time</div><span class="muted small">${st.readiness_history.length} updates</span></div>
    ${sparkline(st.readiness_history)}</div>`;
}

function stat(num, lbl, v) {
  return `<div class="card stat" style="cursor:pointer" data-go="${v}"><div class="num">${esc(num)}</div><div class="lbl">${esc(lbl)} →</div></div>`;
}

// ---------------------------------------------------------------- resume
function resumeView() {
  const p = st.profile, a = st.ats;
  const cats = p.skill_categories || {};
  return `
  <div class="page-head"><div><div class="h1">${ICON.resume} Resume analysis</div><div class="muted">${esc(p.summary || "Structured profile extracted by the Resume Analyst")}</div></div></div>
  <div class="grid g2">
    <div class="card">
      <div class="row between"><div><div class="h2">${esc(p.name)}</div>
        <div class="muted small">${[p.email, p.phone].filter(Boolean).map(esc).join(" · ")}</div>
        <div class="small">${(p.links || []).map((l) => `<a href="${esc(l.startsWith("http") ? l : "https://" + l)}" target="_blank">${esc(l)}</a>`).join(" · ")}</div></div>
        ${p.cgpa ? `<span class="tag">CGPA ${esc(p.cgpa)}</span>` : ""}</div>
      <div style="margin-top:16px">${Object.entries(cats).map(([k, v]) => `<div class="small muted" style="margin:6px 0 4px">${esc(k)}</div>${v.map((s) => `<span class="chip">${esc(s)}</span>`).join("")}`).join("")}</div>
      ${p.projects?.length ? `<div class="h3" style="margin:16px 0 8px">Projects</div><ul class="clean">${p.projects.map((pr) => `<li><b>${esc(pr.name)}</b>${pr.tech?.length ? ` <span class="muted small">· ${esc(pr.tech.join(", "))}</span>` : ""}${pr.summary ? `<div class="muted small">${esc(pr.summary)}</div>` : ""}</li>`).join("")}</ul>` : ""}
      ${p.experience?.length ? `<div class="h3" style="margin:16px 0 8px">Experience</div><ul class="clean">${p.experience.map((x) => `<li><b>${esc(x.role)}</b> · ${esc(x.org)} <span class="muted small">${esc(x.duration || "")}</span></li>`).join("")}</ul>` : ""}
    </div>
    <div class="list">
      <div class="card"><div class="row between" style="margin-bottom:12px"><div class="h2">ATS score</div><div class="match">${a.score}<span class="muted small">/100</span></div></div>
        ${Object.entries(a.breakdown).map(([k, v]) => `<div class="row between small" style="padding:4px 0;border-bottom:1px solid var(--line)"><span>${esc(k)}</span><b>${v}</b></div>`).join("")}</div>
      <div class="card"><div class="h2" style="margin-bottom:10px">Improvements</div><ul class="clean">${a.suggestions.map((s) => `<li>${esc(s)}</li>`).join("")}</ul></div>
      ${p.strengths?.length ? `<div class="card"><div class="h2" style="margin-bottom:8px">Strengths</div>${p.strengths.map((s) => `<span class="chip good">${esc(s)}</span>`).join("")}</div>` : ""}
      <details class="card"><summary class="h3" style="cursor:pointer">Upload an updated resume</summary><div style="margin-top:12px">
        <div class="field"><label>Target role</label><input id="obRole" value="${esc(st.target_role)}" /></div>${uploaderHtml()}</div></details>
    </div>
  </div>`;
}

// ---------------------------------------------------------------- jobs
function jobsView() {
  return `
  <div class="page-head"><div><div class="h1">${ICON.jobs} Job matches</div>
    <div class="muted">Ranked by the Job Scout against your profile. ${cfg.live_jobs ? "Includes live Adzuna listings." : "Showing sample listings (add Adzuna keys for live jobs)."} Setting a job as your target re-runs gap analysis and your roadmap.</div></div></div>
  <div class="list">${st.jobs.map((j) => {
    const isT = j.id === st.target_job_id;
    return `<div class="card job ${isT ? "target" : ""}">
      <div>
        <div class="row" style="gap:8px"><div class="h2">${esc(j.title)}</div>${isT ? `<span class="tag" style="color:var(--accent)">🎯 Target</span>` : ""}<span class="tag">${esc(j.source || "Sample")}</span></div>
        <div class="muted small" style="margin-bottom:8px">${esc(j.company)} · ${esc(j.location)} · ${esc(j.type)}${j.experience ? " · " + esc(j.experience) : ""}</div>
        <div class="small" style="margin-bottom:8px">${esc(j.reason || "")}</div>
        <div>${j.matched.map((s) => `<span class="chip good">✓ ${esc(s)}</span>`).join("")}${j.missing.map((s) => `<span class="chip bad">✗ ${esc(s)}</span>`).join("")}</div>
      </div>
      <div style="text-align:right;min-width:130px"><div class="match">${j.match}%</div><div class="muted small" style="margin-bottom:10px">match</div>
        ${isT ? "" : `<button class="btn sm" data-target="${j.id}">Set as target</button>`}
        ${j.url ? `<div style="margin-top:8px"><a href="${esc(j.url)}" target="_blank" class="small">Apply ↗</a></div>` : ""}</div>
    </div>`;
  }).join("")}</div>`;
}

// ---------------------------------------------------------------- gaps
function gapsView() {
  const g = st.gaps;
  if (!g) return workingView("Waiting for skill-gap analysis…");
  const maxM = Math.max(1, ...g.market_gaps.map((m) => m.count));
  return `
  <div class="page-head"><div><div class="h1">${ICON.gap} Skill gap analysis</div><div class="muted">${esc(g.job_title)} at ${esc(g.company)}</div></div>
    <button class="btn ghost" data-go="jobs">Change target job</button></div>
  <div class="grid" style="grid-template-columns: 2fr 1fr; margin-bottom:16px">
    <div class="card"><div class="h2" style="margin-bottom:8px">Summary</div><p style="margin:0 0 14px">${esc(g.summary)}</p>
      ${meterRow("Core requirements met", g.match_pct)}
      <div class="small muted" style="margin:10px 0 6px">You already have</div>${g.matched.map((s) => `<span class="chip good">${esc(s)}</span>`).join("") || `<span class="muted small">—</span>`}
      ${g.transferable?.length ? `<div class="small muted" style="margin:10px 0 6px">Transferable strengths</div>${g.transferable.map((s) => `<span class="chip">${esc(s)}</span>`).join("")}` : ""}
    </div>
    <div class="card"><div class="h2" style="margin-bottom:4px">Market demand</div><div class="muted small" style="margin-bottom:12px">Missing skills that appear most often across your top matches</div>
      ${g.market_gaps.map((m) => `<div style="margin-bottom:8px"><div class="row between small"><span>${esc(m.skill)}</span><span class="muted">${m.count} jobs</span></div><div class="meter"><div style="width:${(100 * m.count) / maxM}%"></div></div></div>`).join("") || `<div class="muted small">No recurring gaps 🎉</div>`}
    </div>
  </div>
  <div class="card"><div class="row between" style="margin-bottom:10px"><div class="h2">Gaps to close</div><button class="btn sm" data-go="roadmap">View roadmap →</button></div>
    ${g.items.length ? `<table><tr><th>Skill</th><th>Priority</th><th>Why it matters</th><th>Est. time</th></tr>
      ${g.items.map((i) => `<tr><td><b>${esc(i.skill)}</b><div class="muted small">${i.kind === "required" ? "Required" : "Nice to have"}</div></td><td class="prio-${esc(i.priority)}"><b>${esc(i.priority)}</b></td><td>${esc(i.why)}</td><td>${i.est_weeks} wk</td></tr>`).join("")}</table>`
      : `<div class="muted">You meet every listed requirement for this job. Pick a more ambitious target, or focus on interviews.</div>`}
  </div>`;
}

// ---------------------------------------------------------------- roadmap
function roadmapView() {
  const rm = st.roadmap;
  if (!rm) return workingView("Waiting for the Roadmap Planner…");
  const all = rm.plan.flatMap((w) => w.tasks), done = all.filter((t) => t.done).length;
  const pct = all.length ? Math.round((100 * done) / all.length) : 0;
  return `
  <div class="page-head"><div><div class="h1">${ICON.roadmap} Learning roadmap</div><div class="muted">${rm.weeks} weeks to become interview-ready for ${esc(rm.job_title)}</div></div>
    <div class="row"><select id="weeksSel">${[2, 4, 6, 8, 12].map((w) => `<option value="${w}" ${w === rm.weeks ? "selected" : ""}>${w} weeks</option>`).join("")}</select>
    <button class="btn ghost" id="regenBtn">Regenerate</button></div></div>
  <div class="card" style="margin-bottom:16px">${meterRow(`Progress · ${done}/${all.length} tasks`, pct)}
    ${rm.revisions?.length ? `<div class="small" style="color:var(--warn)">⚡ Adapted ${rm.revisions.length}× from interview feedback (latest: ${esc(rm.revisions[rm.revisions.length - 1].topics.join(", "))})</div>` : ""}</div>
  ${rm.plan.map((w) => {
    const wd = w.tasks.filter((t) => t.done).length;
    return `<div class="card week"><div class="row between"><div><div class="muted small">WEEK ${w.week}</div><div class="h2">${esc(w.theme)}</div>
      ${w.goal ? `<div class="muted small">${esc(w.goal)}</div>` : ""}</div><span class="tag">${wd}/${w.tasks.length}</span></div>
      <div style="margin-top:10px">${w.tasks.map((t) => `<div class="task ${t.done ? "done" : ""}">
        <input type="checkbox" data-task="${t.id}" ${t.done ? "checked" : ""}/>
        <div><div class="ttl">${esc(t.title)}</div>
          ${t.added_by ? `<div class="added">+ added by ${esc(t.added_by)}</div>` : ""}
          ${t.resources?.length ? `<div class="res">${t.resources.map((r) => `<a href="${esc(r.url)}" target="_blank">${esc(r.title)} ↗</a>`).join("")}</div>` : ""}</div>
        <div class="row" style="gap:6px"><span class="tag">${esc(t.type)}</span><span class="muted small">${t.hours}h</span></div></div>`).join("")}</div></div>`;
  }).join("")}`;
}

// ---------------------------------------------------------------- interview
function interviewView() {
  const iv = st.active_interview;
  const running = st.status === "running";
  if (!iv) {
    const past = st.interviews.slice().reverse();
    return `
    <div class="page-head"><div><div class="h1">${ICON.interview} Mock interview</div><div class="muted">Questions are tailored to your target job, your projects and your skill gaps. Weak answers update your roadmap automatically.</div></div></div>
    <div class="card" style="margin-bottom:16px"><div class="row" style="flex-wrap:wrap">
      <div><label>Round</label><select id="ivMode"><option value="technical">Technical</option><option value="hr">HR / Behavioural</option></select></div>
      <div><label>Questions</label><select id="ivCount">${[3, 4, 5, 6].map((n) => `<option ${n === 5 ? "selected" : ""}>${n}</option>`).join("")}</select></div>
      <div style="align-self:flex-end"><button class="btn" id="ivStart" ${running ? "disabled" : ""}>${running ? `<span class="loader"></span>Preparing…` : "Start interview"}</button></div>
    </div></div>
    ${past.length ? `<div class="h2" style="margin-bottom:10px">Past interviews</div><div class="list">${past.map((iv, i) => pastInterview(iv, i === 0)).join("")}</div>` : ""}`;
  }
  const answered = iv.questions.filter((q) => q.evaluation);
  const current = iv.questions.find((q) => !q.evaluation);
  const waiting = current && current.answer != null && running;
  return `
  <div class="page-head"><div><div class="h1">${ICON.interview} ${iv.mode === "hr" ? "HR" : "Technical"} interview</div><div class="muted">${esc(iv.job_title)} · Question ${Math.min(answered.length + 1, iv.questions.length)} of ${iv.questions.length}</div></div></div>
  <div class="card" style="margin-bottom:16px"><div class="meter"><div style="width:${(100 * answered.length) / iv.questions.length}%"></div></div></div>
  ${answered.map(qaBlock).join("")}
  ${current ? `<div class="card"><div class="muted small">Q${current.index + 1} · ${esc(current.topic)}</div><div class="h2" style="margin:6px 0 12px">${esc(current.question)}</div>
    <textarea id="ivAnswer" data-idx="${current.index}" placeholder="Type your answer the way you'd say it in the interview…" ${waiting ? "disabled" : ""}>${esc(drafts[iv.id + current.index] || current.answer || "")}</textarea>
    <div class="row between" style="margin-top:10px"><span class="muted small">Tip: structure it as definition → example → trade-offs.</span>
    <button class="btn" id="ivSubmit" ${waiting ? "disabled" : ""}>${waiting ? `<span class="loader"></span>Evaluating…` : "Submit answer"}</button></div></div>`
    : `<div class="card">${running ? `<span class="loader"></span>Wrapping up…` : ""}</div>`}`;
}

function qaBlock(q) {
  const e = q.evaluation;
  const color = e.score >= 8 ? "var(--good)" : e.score >= 6 ? "var(--warn)" : "var(--bad)";
  return `<div class="card qa scored" style="margin-bottom:12px"><div class="row between"><div class="muted small">Q${q.index + 1} · ${esc(q.topic)}</div><div class="score" style="color:${color}">${e.score}/10</div></div>
    <div class="h3" style="margin:4px 0 8px">${esc(q.question)}</div>
    <div class="small muted" style="margin-bottom:8px">Your answer: ${esc(q.answer || "(blank)")}</div>
    <div class="small">${esc(e.feedback)}</div>
    ${e.improvements?.length ? `<div style="margin-top:6px">${e.improvements.map((s) => `<span class="chip warn">${esc(s)}</span>`).join("")}</div>` : ""}
    ${e.ideal_answer ? `<details style="margin-top:6px"><summary class="small" style="cursor:pointer;color:var(--accent)">Model answer</summary><div class="small" style="margin-top:6px">${esc(e.ideal_answer)}</div></details>` : ""}</div>`;
}

function pastInterview(iv, open = false) {
  const d = new Date(iv.finished_at * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  return `<details class="card" ${open ? "open" : ""}><summary style="cursor:pointer;list-style:none"><div class="row between"><div><div class="h3">${iv.mode === "hr" ? "HR" : "Technical"} · ${esc(iv.job_title)}</div><div class="muted small">${d}</div></div>
    <div class="row">${iv.weak_topics.map((t) => `<span class="chip bad">${esc(t)}</span>`).join("")}<div class="match">${iv.score}%</div></div></div></summary>
    <div style="margin-top:14px">${iv.questions.map(qaBlock).join("")}</div></details>`;
}

// ---------------------------------------------------------------- agents / architecture
function agentsView() {
  const flows = [
    ["resume.uploaded", "resume", "profile.ready", "jobs", "jobs.ranked", "gap", "gaps.identified", "roadmap", "roadmap.ready", "progress"],
    ["target.selected", "jobs", "target.changed", "gap", "gaps.identified", "roadmap", "roadmap.ready", "progress"],
    ["interview.answered", "interview", "interview.evaluated", "progress", "weak_topics.detected", "roadmap", "roadmap.revised", "progress"],
    ["task.toggled", "roadmap", "task.updated", "progress"],
  ];
  const flowHtml = (f) => `<div class="flow">${f.map((x, i) => (i % 2 === 0 ? `<span class="evt">${esc(x)}</span>` : `<span class="chip">${ICON[x]} ${esc(labelOf(x))}</span>`)).join(`<span class="arrow">→</span>`)}</div>`;
  return `
  <div class="page-head"><div><div class="h1">⬡ How the agents collaborate</div>
    <div class="muted">Agents never call each other directly. Each one handles an event, updates the shared student state and emits new events. The orchestrator routes every event to the agents subscribed to it, saves state after each step and logs every step.</div></div></div>
  <div class="card" style="margin-bottom:16px"><div class="h2" style="margin-bottom:12px">Workflows</div>
    <div class="list">
      <div><div class="small muted">1 · New resume (fully automatic)</div>${flowHtml(flows[0])}</div>
      <div><div class="small muted">2 · Student changes target job</div>${flowHtml(flows[1])}</div>
      <div><div class="small muted">3 · Feedback loop: weak interview answers re-plan the roadmap</div>${flowHtml(flows[2])}</div>
      <div><div class="small muted">4 · Progress updates</div>${flowHtml(flows[3])}</div>
    </div></div>
  <div class="grid g3" style="margin-bottom:16px">${cfg.agents.map((a) => `<div class="card"><div class="h2">${ICON[a.name]} ${esc(a.label)}</div>
    <p class="muted small" style="margin:6px 0 10px">${esc(a.description)}</p><div class="small muted">Subscribes to</div>
    ${a.subscribes.map((s) => `<span class="chip mono" style="font-size:11px">${esc(s)}</span>`).join("")}</div>`).join("")}</div>
  <div class="card"><div class="h2" style="margin-bottom:8px">Reasoning engine</div>
    <p class="muted small" style="margin:0">${cfg.llm_enabled ? `Agents reason with <b>${esc(cfg.model)}</b> through an OpenAI-compatible API.` : "No LLM key is configured, so the agents are running on their built-in logic."}
    Every agent has deterministic fallback logic (skill taxonomy, rule-based scoring, curated question bank), so the system degrades gracefully when the LLM is down or rate-limited.</p></div>`;
}

// ---------------------------------------------------------------- bindings
function bindView() {
  document.querySelectorAll("[data-go]").forEach((el) => (el.onclick = () => go(el.dataset.go)));
  document.querySelectorAll("[data-target]").forEach((b) => (b.onclick = () => { submit(`/api/students/${sid}/target`, { job_id: b.dataset.target }); toast("Target updated: gap analysis and roadmap are re-running"); }));
  document.querySelectorAll("[data-task]").forEach((cb) => (cb.onchange = () => {
    cb.closest(".task").classList.toggle("done", cb.checked);
    submit(`/api/students/${sid}/tasks/${cb.dataset.task}`, { done: cb.checked });
  }));
  const regen = $("#regenBtn");
  if (regen) regen.onclick = () => submit(`/api/students/${sid}/roadmap`, { weeks: +$("#weeksSel").value });
  const ivStart = $("#ivStart");
  if (ivStart) ivStart.onclick = () => submit(`/api/students/${sid}/interview/start`, { mode: $("#ivMode").value, count: +$("#ivCount").value });
  const ans = $("#ivAnswer");
  if (ans) {
    const key = st.active_interview.id + ans.dataset.idx;
    ans.oninput = () => (drafts[key] = ans.value);
    if (!ans.disabled) ans.focus();
    $("#ivSubmit").onclick = () => {
      if (ans.value.trim().split(/\s+/).length < 3 && !confirm("Submit a very short answer?")) return;
      st.active_interview.questions[+ans.dataset.idx].answer = ans.value;
      submit(`/api/students/${sid}/interview/answer`, { index: +ans.dataset.idx, answer: ans.value });
    };
  }
  bindUploader();
}

boot();
