const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const state = { file: null, job: null, settings: null, poll: null };

function go(step) {
  if (step === "home") loadLibrary();
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
  if (!r.ok) throw Object.assign(new Error(data.detail || `Error ${r.status}`), { status: r.status });
  return data;
}
const postJSON = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

// ---------- opciones ----------
async function loadOptions() {
  const o = await api("/api/options");
  $("#rhythms").innerHTML = o.rhythms.map((r, i) => `
    <label class="choice"><input type="radio" name="rhythm" value="${r.key}" ${i === 0 ? "checked" : ""}>
    <span>${esc(r.label)}${i === 0 ? '<b class="tag">recomendado</b>' : ""}<small>${esc(r.description)}</small></span></label>`).join("");
  $("#styles").innerHTML = o.styles.map((s, i) => `
    <label class="choice"><input type="radio" name="style" value="${s.key}" ${i === 0 ? "checked" : ""}><span>${esc(s.label)}</span></label>`).join("");
  state.options = o;
  $("#packs").innerHTML = o.packs.map(p => `
    <label class="choice"><input type="radio" name="pack" value="${p.key}" ${p.key === "general" ? "checked" : ""}>
    <span>${esc(p.label)}<small>${esc(p.description)}</small></span></label>`).join("");
  $("#brand-sector").innerHTML = o.packs.map(p => `<option value="${p.key}">${esc(p.label)}</option>`).join("");
  $("#packs").onchange = () => applyPack(false);
  renderHooks(o.hook_templates);
}
function renderHooks(list) {
  $("#hook-template").innerHTML = `<option value="">Plantilla de gancho (opcional)</option>` + list.map(t => `<option>${esc(t)}</option>`).join("");
}
// Cada sector trae su estilo recomendado y sus ganchos.
function applyPack(fromBrand) {
  const o = state.options;
  if (!o) return;
  if (fromBrand && state.brand?.sector) {
    const r = $(`input[name=pack][value="${state.brand.sector}"]`);
    if (r) r.checked = true;
  }
  const p = o.packs.find(x => x.key === $("input[name=pack]:checked")?.value);
  if (!p) return;
  renderHooks([...p.hooks, ...o.hook_templates]);
  const st = p.style && $(`input[name=style][value="${p.style}"]`);
  if (st) st.checked = true;
}

const NAMES = { iman: "la IA de Imán", claude: "tu Claude", openai: "tu ChatGPT" };

async function loadSettings() {
  state.settings = await api("/api/settings");
  const s = state.settings;
  const f = $("#settings-form");
  f.provider.value = s.provider; f.transcriber.value = s.transcriber; f.language.value = s.language;
  f.anthropic_key.placeholder = s.has_anthropic_key ? "Guardada ✓ (escribe para cambiarla)" : "sk-ant-…";
  f.openai_key.placeholder = s.has_openai_key ? "Guardada ✓ (escribe para cambiarla)" : "sk-…";
  $("#own-keys").open = s.provider === "claude" || s.provider === "openai";
  const ok = s.provider === "iman" || (s.provider === "claude" && s.has_anthropic_key) || (s.provider === "openai" && s.has_openai_key);
  $("#ai-hint").innerHTML = ok
    ? `Edita con ${NAMES[s.provider]}.`
    : `Sin IA: cortaré silencios y repeticiones igualmente. <a href="#" id="hint-settings">Activa la IA</a> para el gancho, los efectos y las instrucciones.`;
  renderLicense(s.license);
}

function renderLicense(l) {
  const pill = $("#trial-pill");
  $("#license-error").hidden = true;
  $("#license-active").hidden = !l.licensed;
  $("#license-activate").hidden = $("#license-buy").hidden = l.licensed;
  if (l.licensed) {
    const until = l.expires ? ` hasta el ${new Date(l.expires).toLocaleDateString("es-ES")}` : "";
    $("#license-status").textContent = `Licencia activa${until}. Gracias por confiar en Imán.`;
    pill.hidden = true;
  } else {
    const left = l.free_left;
    $("#license-status").textContent = left
      ? `Estás probando Imán: te quedan ${left} ${left === 1 ? "reel" : "reels"} gratis (con marca de agua).`
      : "Has usado tus reels de prueba. Activa tu licencia para seguir editando sin marca de agua.";
    pill.hidden = l.dev;
    pill.textContent = left ? `Prueba · ${left} gratis` : "Activa tu licencia";
    pill.classList.toggle("warn", !left);
  }
}
$("#trial-pill").onclick = e => { e.preventDefault(); $("#settings").showModal(); };
$("#license-btn").onclick = async () => {
  const key = $("#license-input").value.trim();
  if (!key) return $("#license-input").focus();
  $("#license-btn").disabled = true; $("#license-btn").textContent = "Activando…";
  try {
    const s = await api("/api/license", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key }) });
    $("#license-input").value = "";
    state.settings = s; renderLicense(s.license);
  } catch (err) {
    $("#license-error").textContent = err.message; $("#license-error").hidden = false;
  } finally { $("#license-btn").disabled = false; $("#license-btn").textContent = "Activar"; }
};
$("#license-off").onclick = async () => {
  if (!confirm("¿Desactivar la licencia en este ordenador? Podrás activarla en otro.")) return;
  const s = await api("/api/license", { method: "DELETE" });
  state.settings = s; renderLicense(s.license);
};
$("#open-settings").onclick = () => $("#settings").showModal();
document.addEventListener("click", e => { if (e.target.id === "hint-settings") { e.preventDefault(); $("#settings").showModal(); } });
$("#save-settings").onclick = async e => {
  e.preventDefault();
  const f = $("#settings-form");
  const body = Object.fromEntries(new FormData(f));
  delete body.license_input;
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
  fd.append("pack", $("input[name=pack]:checked")?.value === "general" ? "" : $("input[name=pack]:checked")?.value || "");
  fd.append("use_brand", $("#use-brand").checked && !$("#use-brand-row").hidden);
  fd.append("hook_title", $("#hook-title").value);
  fd.append("hook_template", $("#hook-template").value);
  fd.append("instructions", $("#instructions").value);
  showWorking("Subiendo tu vídeo", 0.01);
  go("result");
  try {
    state.job = await api("/api/jobs", { method: "POST", body: fd });
    poll();
  } catch (err) {
    if (err.status === 402) { showError(err.message, true); $("#settings").showModal(); }
    else showError(err.message);
  }
};

// ---------- 3. resultado ----------
function showWorking(step, pct) {
  $("#working").hidden = false; $("#out").hidden = true;
  $("#working").innerHTML = `<div class="spinner"></div><strong>${esc(step)}</strong><div class="bar"><i style="width:${Math.round(pct * 100)}%"></i></div><span class="hint">Puedes hacer otra cosa mientras tanto.</span>`;
}
function showError(msg, needsLicense = false) {
  $("#working").hidden = false; $("#out").hidden = true;
  $("#working").innerHTML = needsLicense
    ? `<strong>Tu prueba gratis ha terminado</strong><span class="hint">${esc(msg)}</span><button class="primary" id="hint-settings">Activar licencia</button>`
    : `<strong class="error">No he podido editarlo</strong><span class="hint">${esc(msg)}</span>`;
}
function poll() {
  clearTimeout(state.poll);
  state.poll = setTimeout(async () => {
    const j = await api(`/api/jobs/${state.job.id}`);
    state.job = j;
    if (j.status === "working") { showWorking(j.step, j.progress); return poll(); }
    if (j.status === "error") return showError(j.error);
    showResult(j); if (j.options?.watermark) loadSettings();
  }, 900);
}
function fmt(s) { return `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`; }
function renderChat(j) {
  $("#chat").innerHTML = (j.chat || []).map(m => `<div class="msg ${m.role === "user" ? "user" : "iman"}">${esc(m.text)}</div>`).join("");
  $("#chat").scrollTop = 1e6;
}
$("#chat-form").onsubmit = async e => {
  e.preventDefault();
  const input = $("#chat-input"), msg = input.value.trim();
  if (!msg || !state.job || state.job.status === "working") return;
  input.value = "";
  renderChat({ chat: [...(state.job.chat || []), { role: "user", text: msg }] });
  showWorking("Pensando el cambio", 0.02);
  try {
    state.job = await api(`/api/jobs/${state.job.id}/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: msg }) });
    renderChat(state.job);
    poll();
  } catch (err) {
    renderChat({ chat: [...(state.job.chat || []), { role: "user", text: msg }, { role: "iman", text: err.message }] });
    if (state.job.result) showResult(state.job); else showError(err.message);
  }
};
const FX_NAMES = { lista: "Lista", palabra: "Palabra gigante", titular: "Titular", cifra: "Cifra", frase: "Frase", tecleo: "Texto que se escribe",
  color: "Golpe de color", comentario: "Comentario", contador: "Contador", portada: "Portada de revista", cta: "Llamada a la acción",
  dato: "Dato", bruto: "Toma en bruto", fantasma: "Eco", pagina: "Página de revista", detras: "Texto detrás de ti",
  fondo: "Fondo de color", desenfoque: "Fondo desenfocado", ubicacion: "Ubicación", oferta: "Oferta", ruta: "Ruta",
  testimonio: "Testimonio", plazas: "Plazas", precio: "Precio" };
function renderEffects(j) {
  const list = j.result.plan.effects || [];
  $("#fx-box").hidden = !list.length;
  $("#fx-apply").hidden = true;
  $("#fx-list").innerHTML = list.map((fx, i) => {
    const name = fx.type === "lista" && fx.look === "itinerario" ? "Itinerario" : FX_NAMES[fx.type] || fx.type;
    const detail = fx.type === "lista" ? fx.items.map(it => it.text).join(" · ") : [fx.text, fx.subtitle].filter(x => x && x !== "-").join(" · ");
    return `<label class="fx ${fx.off ? "off" : ""}"><input type="checkbox" class="switch" data-i="${i}" ${fx.off ? "" : "checked"}>
      <span class="grow">${esc(name)}<small>${esc(detail)}</small></span></label>`;
  }).join("");
}
$("#fx-list").onchange = e => {
  e.target.closest(".fx").classList.toggle("off", !e.target.checked);
  $("#fx-apply").hidden = false;
};
$("#fx-apply").onclick = async () => {
  const off = $$("#fx-list .switch").filter(s => !s.checked).map(s => +s.dataset.i);
  showWorking("Aplicando cambios", 0.02);
  try { state.job = await postJSON(`/api/jobs/${state.job.id}/plan`, { effects_off: off }); poll(); }
  catch (err) { showError(err.message); }
};
$("#safe-toggle").onchange = e => $("#phone").classList.toggle("show-safe", e.target.checked);
$("#post-btn").onclick = async () => {
  const btn = $("#post-btn");
  btn.disabled = true; btn.textContent = "Escribiendo…";
  try {
    const p = await api(`/api/jobs/${state.job.id}/post`, { method: "POST" });
    $("#post-text").value = `${p.caption}\n\n${p.hashtags.map(h => "#" + h).join(" ")}`;
    $("#post-box").hidden = false;
  } catch (err) { $("#post-text").value = err.message; $("#post-box").hidden = false; }
  finally { btn.disabled = false; btn.textContent = "✦ Escríbeme el texto y los hashtags"; }
};
$("#post-copy").onclick = async () => {
  await navigator.clipboard.writeText($("#post-text").value).catch(() => $("#post-text").select());
  $("#post-copy").textContent = "Copiado ✓";
  setTimeout(() => $("#post-copy").textContent = "Copiar texto", 1500);
};
function setCover(t) {
  const url = `/api/jobs/${state.job.id}/cover.jpg?t=${(+t).toFixed(1)}`;
  $("#cover-img").src = url; $("#cover-dl").href = url;
}
let coverTimer;
$("#cover-t").oninput = e => { clearTimeout(coverTimer); coverTimer = setTimeout(() => setCover(e.target.value), 150); };

async function loadLibrary() {
  const { reels } = await api("/api/reels");
  $("#library").innerHTML = reels.map(r => `
    <div class="reel-card" data-open="${r.id}" role="button" tabindex="0">
      <img src="/api/jobs/${r.id}/reel.jpg" alt="" loading="lazy">
      <button class="del" data-del="${r.id}" title="Borrar">✕</button>
      <div><strong>${esc(r.title || "Sin título")}</strong><span>${fmt(r.duration)} · ${new Date(r.created * 1000).toLocaleDateString("es-ES")}</span></div>
    </div>`).join("");
}
$("#library").onclick = async e => {
  const del = e.target.closest("[data-del]");
  if (del) {
    e.stopPropagation();
    if (!confirm("¿Borrar este reel? No se puede deshacer.")) return;
    await api(`/api/jobs/${del.dataset.del}`, { method: "DELETE" });
    return loadLibrary();
  }
  const card = e.target.closest("[data-open]");
  if (!card) return;
  state.job = await api(`/api/jobs/${card.dataset.open}`);
  go("result");
  showResult(state.job);
};

function showResult(j) {
  renderChat(j);
  renderEffects(j);
  $("#post-box").hidden = true;
  $("#cover-t").max = j.result.duration_out.toFixed(1);
  $("#cover-t").value = Math.min(0.5, j.result.duration_out / 2);
  setCover($("#cover-t").value);
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

// ---------- mi marca ----------
const brandForm = $("#brand-form");
function ink(hex) {
  const n = parseInt((hex || "#141518").slice(1), 16), r = (n >> 16) / 255, g = (n >> 8 & 255) / 255, b = (n & 255) / 255;
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.6 ? "#141518" : "#FFFFFF";
}
const FONT_CSS = Object.fromEntries(["Moderna", "Impacto", "Condensada", "Elegante", "Manuscrita"].map(n => [n, `"Iman ${n}"`]));
function renderBrand(b) {
  state.brand = b;
  const f = brandForm;
  for (const k of ["name", "cta", "contact", "handle"]) f[k].value = b[k] || "";
  f.primary.value = b.primary || "#FF5547"; f.secondary.value = b.secondary || "#141518";
  f.logo_corner.checked = b.logo_corner; f.end_card.checked = b.end_card;
  f.sector.value = b.sector || "general";
  $("#brand-fonts").innerHTML = ["", ...b.fonts].map(n => `
    <label class="choice"><input type="radio" name="font" value="${n}" ${n === (b.font || "") ? "checked" : ""}>
    <span style="font-family:${FONT_CSS[n] || "inherit"}">${n || "La del estilo"}</span></label>`).join("");
  const logo = b.has_logo ? `/api/brand/logo.png?t=${Date.now()}` : "";
  $("#logo-img").src = logo; $("#logo-img").hidden = !logo; $("#logo-empty").hidden = !!logo; $("#logo-remove").hidden = !logo;
  $("#swatches").innerHTML = (b.palette || []).map(c => `<button type="button" style="background:${c}" data-color="${c}" title="Usar ${c}"></button>`).join("");
  const active = b.has_logo || !!b.primary;
  $("#brand-dot").style.background = b.primary || (active ? "var(--accent)" : "var(--line)");
  $("#use-brand-row").hidden = !active;
  applyPack(true);
  previewBrand();
}
function previewBrand() {
  const f = brandForm, p = f.primary.value, font = FONT_CSS[f.querySelector("input[name=font]:checked")?.value] || "Iman Impacto";
  const logo = state.brand?.has_logo ? $("#logo-img").src : "";
  $("#mock-corner").src = f.logo_corner.checked ? logo : "";
  Object.assign($("#mock-hook").style, { background: p, color: ink(p), fontFamily: font });
  $("#mock-accent").style.color = p;
  $("#mock-end").style.display = f.end_card.checked ? "" : "none";
  Object.assign($("#mock-end").style, { background: p, color: ink(p) });
  $("#mock-logo").src = logo; $("#mock-name").textContent = logo ? "" : f.name.value;
  $("#mock-cta").textContent = f.cta.value || "Tu llamada a la acción";
  $("#mock-contact").textContent = f.contact.value; $("#mock-handle").textContent = f.handle.value;
}
brandForm.addEventListener("input", previewBrand);
$("#swatches").onclick = e => {
  const c = e.target.dataset.color;
  if (!c) return;
  // Clic: principal. Mayúsculas + clic: secundario.
  brandForm[e.shiftKey ? "secondary" : "primary"].value = c;
  previewBrand();
};
function brandError(msg) { $("#brand-error").textContent = msg || ""; $("#brand-error").hidden = !msg; }
async function uploadLogo(file) {
  if (!file) return;
  brandError("");
  const fd = new FormData(); fd.append("logo", file);
  try {
    // Guardamos antes lo escrito para que el logo no pise los colores elegidos a mano.
    renderBrand(await api("/api/brand/logo", { method: "POST", body: fd }));
  } catch (err) { brandError(err.message); }
}
$("#logo-file").onchange = e => uploadLogo(e.target.files[0]);
const logoDrop = $("#logo-drop");
logoDrop.ondragover = e => { e.preventDefault(); logoDrop.classList.add("over"); };
logoDrop.ondragleave = () => logoDrop.classList.remove("over");
logoDrop.ondrop = e => { e.preventDefault(); logoDrop.classList.remove("over"); uploadLogo(e.dataTransfer.files[0]); };
$("#logo-remove").onclick = async () => renderBrand(await api("/api/brand/logo", { method: "DELETE" }));
function brandBody() {
  const f = brandForm;
  return { name: f.name.value, cta: f.cta.value, contact: f.contact.value, handle: f.handle.value,
    primary: f.primary.value.toUpperCase(), secondary: f.secondary.value.toUpperCase(),
    font: f.querySelector("input[name=font]:checked")?.value || "", sector: f.sector.value === "general" ? "" : f.sector.value,
    logo_corner: f.logo_corner.checked, end_card: f.end_card.checked };
}
$("#brand-auto").onclick = async () => {
  const d = brandForm.description.value.trim();
  if (!d) return brandForm.description.focus();
  const btn = $("#brand-auto");
  btn.disabled = true; btn.textContent = "Pensando…"; brandError("");
  try {
    await postJSON("/api/brand", brandBody());
    renderBrand(await postJSON("/api/brand/auto", { description: d }));
  } catch (err) { brandError(err.message); }
  finally { btn.disabled = false; btn.textContent = "✦ Rellénalo tú"; }
};
$("#brand-save").onclick = async e => {
  e.preventDefault();
  try { renderBrand(await postJSON("/api/brand", brandBody())); $("#brand").close(); }
  catch (err) { brandError(err.message); }
};
$("#open-brand").onclick = () => { brandError(""); $("#brand").showModal(); };
$("#brand-edit-link").onclick = e => { e.preventDefault(); $("#brand").showModal(); };
// Versión nueva: aviso arriba y actualización con un clic.
async function checkUpdate() {
  let u;
  try { u = await api("/api/update"); } catch { return; }
  const box = $("#update");
  if (!u.available || localStorage.getItem("iman-update-later") === u.latest) return;
  $("#update-title").textContent = `Hay una versión nueva de Imán (${u.latest})`;
  $("#update-text").textContent = u.covered ? "Tardas un minuto y no pierdes nada de lo que tienes."
    : "Salió después de que caducara tu licencia. Renueva para tenerla.";
  $("#update-notes").textContent = u.notes || "";
  $("#update-notes-wrap").hidden = !u.notes;
  $("#update-btn").hidden = !u.covered;
  $("#update-later").onclick = () => { try { localStorage.setItem("iman-update-later", u.latest); } catch {} box.hidden = true; };
  box.hidden = false;
}
$("#update-btn").onclick = async () => {
  const btn = $("#update-btn");
  btn.disabled = true;
  try { await postJSON("/api/update/install", {}); }
  catch (err) { $("#update-text").textContent = err.message; btn.disabled = false; return; }
  const tick = async () => {
    const s = (await api("/api/update").catch(() => null))?.install;
    if (!s) { $("#update-text").textContent = "Instalando… Imán se volverá a abrir solo."; return; }
    if (s.state === "downloading") {
      btn.textContent = `Descargando… ${Math.round(s.progress * 100)}%`;
      return setTimeout(tick, 800);
    }
    btn.hidden = s.state !== "error"; btn.disabled = false; btn.textContent = "Reintentar";
    $("#update-text").textContent = s.message;
  };
  tick();
};
checkUpdate(); setInterval(checkUpdate, 6 * 3600 * 1000);

loadOptions().then(() => api("/api/brand").then(renderBrand)); loadSettings();
api("/api/reels").then(r => go(r.reels.length ? "home" : "upload"));
