const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const state = { file: null, job: null, settings: null, poll: null };

function go(step) {
  $$(".panel").forEach(p => p.classList.toggle("show", p.dataset.panel === step));
  $$("#steps button").forEach(b => b.classList.toggle("active", b.dataset.step === step));
  window.scrollTo({ top: 0 });
}
document.addEventListener("click", e => {
  const t = e.target.closest("[data-goto],[data-step]");
  if (!t) return;
  e.preventDefault();
  go(t.dataset.goto || t.dataset.step);
});

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `Error ${r.status}`);
  return data;
}
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ---------- opciones ----------
async function loadOptions() {
  const o = await api("/api/options");
  $("#rhythms").innerHTML = o.rhythms.map((r, i) => `
    <label class="choice"><input type="radio" name="rhythm" value="${r.key}" ${i === 0 ? "checked" : ""}>
    <span>${esc(r.label)}${i === 0 ? '<b class="tag">recomendado</b>' : ""}<small>${esc(r.description)}</small></span></label>`).join("");
  $("#styles").innerHTML = o.styles.map((s, i) => `
    <label class="choice"><input type="radio" name="style" value="${s.key}" ${i === 0 ? "checked" : ""}><span>${esc(s.label)}</span></label>`).join("");
  $("#hook-template").innerHTML += o.hook_templates.map(t => `<option>${esc(t)}</option>`).join("");
}

async function loadSettings() {
  state.settings = await api("/api/settings");
  const s = state.settings;
  const f = $("#settings-form");
  f.provider.value = s.provider; f.transcriber.value = s.transcriber; f.language.value = s.language;
  f.anthropic_key.placeholder = s.has_anthropic_key ? "Guardada ✓ (escribe para cambiarla)" : "sk-ant-…";
  f.openai_key.placeholder = s.has_openai_key ? "Guardada ✓ (escribe para cambiarla)" : "sk-…";
  const ok = (s.provider === "claude" && s.has_anthropic_key) || (s.provider === "openai" && s.has_openai_key);
  $("#ai-hint").innerHTML = ok
    ? `Edita con ${s.provider === "claude" ? "Claude" : "ChatGPT"}.`
    : `Sin IA conectada: cortaré silencios y repeticiones igualmente. <a href="#" id="hint-settings">Conectar Claude o ChatGPT</a> para el gancho y las instrucciones.`;
}
$("#open-settings").onclick = () => $("#settings").showModal();
document.addEventListener("click", e => { if (e.target.id === "hint-settings") { e.preventDefault(); $("#settings").showModal(); } });
$("#save-settings").onclick = async e => {
  e.preventDefault();
  const f = $("#settings-form");
  const body = Object.fromEntries(new FormData(f));
  await api("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  f.anthropic_key.value = ""; f.openai_key.value = "";
  await loadSettings();
  $("#settings").close();
};

// ---------- 0. idea ----------
$("#idea-form").onsubmit = async e => {
  e.preventDefault();
  const btn = e.target.querySelector("button");
  btn.disabled = true; btn.textContent = "Pensando…";
  try {
    const body = Object.fromEntries(new FormData(e.target));
    const { ideas } = await api("/api/ideas", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    $("#ideas").innerHTML = ideas.map(i => `
      <div class="card"><h4>${esc(i.hook)}</h4><p>${esc(i.script)}</p><p class="hint">${esc(i.why)}</p>
      <button class="ghost use-idea" data-hook="${esc(i.hook)}">Grabar esta →</button></div>`).join("");
  } catch (err) {
    $("#ideas").innerHTML = `<p class="error">${esc(err.message)}</p>`;
  } finally { btn.disabled = false; btn.textContent = "Dame 3 ideas"; }
};
document.addEventListener("click", e => {
  const b = e.target.closest(".use-idea");
  if (!b) return;
  $("#hook-title").value = b.dataset.hook;
  go("upload");
});

// ---------- 1. subir ----------
const drop = $("#drop");
function pick(file) {
  if (!file || !file.type.startsWith("video")) return;
  state.file = file;
  const v = $("#preview");
  v.src = URL.createObjectURL(file); v.hidden = false; v.play();
  $(".drop-inner").hidden = true;
  $("#to-edit").disabled = false;
}
$("#file").onchange = e => pick(e.target.files[0]);
drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = e => { e.preventDefault(); drop.classList.remove("over"); pick(e.dataTransfer.files[0]); };
$("#to-edit").onclick = () => go("edit");

// ---------- 2. editar ----------
$("#go").onclick = async () => {
  if (!state.file) return go("upload");
  const fd = new FormData();
  fd.append("video", state.file);
  fd.append("rhythm", $("input[name=rhythm]:checked").value);
  fd.append("style", $("input[name=style]:checked").value);
  fd.append("fit", $("input[name=fit]:checked").value);
  fd.append("size", $("input[name=size]:checked").value);
  fd.append("hook", $("#hook").checked);
  fd.append("voice", $("#voice").checked);
  fd.append("hook_title", $("#hook-title").value);
  fd.append("hook_template", $("#hook-template").value);
  fd.append("instructions", $("#instructions").value);
  showWorking("Subiendo tu vídeo", 0.01);
  go("result");
  try {
    state.job = await api("/api/jobs", { method: "POST", body: fd });
    poll();
  } catch (err) { showError(err.message); }
};

// ---------- 3. resultado ----------
function showWorking(step, pct) {
  $("#working").hidden = false; $("#out").hidden = true;
  $("#working").innerHTML = `<div class="spinner"></div><strong>${esc(step)}</strong><div class="bar"><i style="width:${Math.round(pct * 100)}%"></i></div><span class="hint">Puedes hacer otra cosa mientras tanto.</span>`;
}
function showError(msg) {
  $("#working").hidden = false; $("#out").hidden = true;
  $("#working").innerHTML = `<strong class="error">No he podido editarlo</strong><span class="hint">${esc(msg)}</span>`;
}
function poll() {
  clearTimeout(state.poll);
  state.poll = setTimeout(async () => {
    const j = await api(`/api/jobs/${state.job.id}`);
    state.job = j;
    if (j.status === "working") { showWorking(j.step, j.progress); return poll(); }
    if (j.status === "error") return showError(j.error);
    showResult(j);
  }, 900);
}
function fmt(s) { return `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`; }
function showResult(j) {
  const r = j.result, bust = `?t=${Date.now()}`;
  const v = $("#out");
  v.src = `/api/jobs/${j.id}/reel.mp4${bust}`; v.hidden = false; $("#working").hidden = true;
  $("#download").href = `/api/jobs/${j.id}/reel.mp4`;
  $("#stats").innerHTML = `
    <div><b>${fmt(r.duration_in)} → ${fmt(r.duration_out)}</b><span>duración</span></div>
    <div><b>${r.cuts}</b><span>cortes</span></div>
    <div><b>${r.removed_words.length}</b><span>palabras quitadas</span></div>`;
  const p = r.plan;
  $("#hook-box").innerHTML = (p.hook_title ? `<div class="card"><h4>${esc(p.hook_title)}</h4><p class="hint">Gancho en pantalla</p></div>` : "")
    + (p.hook_line ? `<div class="card"><p>«${esc(p.hook_line)}»</p><p class="hint">Si quieres regrabar el arranque, prueba con esta frase.</p></div>` : "");
  $("#cuts").innerHTML = (p.drop_reasons.length ? `<p>${p.drop_reasons.map(esc).join("<br>")}</p>` : "")
    + `<p>${r.removed_words.map(esc).join(" · ") || "Nada"}</p>`;
}
async function reedit(changes) {
  if (!state.job || state.job.status === "working") return;
  showWorking("Aplicando cambios", 0.02);
  try {
    state.job = await api(`/api/jobs/${state.job.id}/reedit`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(changes) });
    poll();
  } catch (err) { showError(err.message); }
}
$$(".quick button").forEach(b => b.onclick = () => reedit(b.dataset.rhythm ? { rhythm: b.dataset.rhythm } : { style: b.dataset.style }));
$("#reedit-form").onsubmit = e => {
  e.preventDefault();
  const h = $("#new-hook").value.trim();
  if (h) reedit({ hook_title: h, hook: true });
};

loadOptions(); loadSettings(); go("upload");
