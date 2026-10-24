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
  renderStyles(o.styles);
  state.options = o;
  $("#packs").innerHTML = o.packs.map(p => `
    <label class="choice"><input type="radio" name="pack" value="${p.key}" ${p.key === "general" ? "checked" : ""}>
    <span>${esc(p.label)}<small>${esc(p.description)}</small></span></label>`).join("");
  $("#brand-sector").innerHTML = o.packs.map(p => `<option value="${p.key}">${esc(p.label)}</option>`).join("");
  $("#packs").onchange = () => applyPack(false);
  renderHooks(o.hook_templates);
}
// Galería de estilos: cada tarjeta enseña el texto moviéndose como saldrá en el reel.
const CSS_FONT = { "Montserrat Black": "Iman Impacto", "Anton": "Iman Condensada", "Playfair Display ExtraBold": "Iman Elegante",
  "Caveat": "Iman Manuscrita", "Figtree ExtraBold": "Iman Moderna", "Figtree SemiBold": "Iman Ligera" };
function stylePreview(s) {
  const L = s.look;
  if (!L) return "";
  const words = L.words <= 1 ? ["CAMBIA"] : L.words === 2 ? ["esto", "cambia"] : ["esto", "lo", "cambia", "todo"].slice(0, Math.min(4, L.words));
  const px = Math.round(Math.min(L.words <= 1 ? 30 : 22, L.size * 0.2));
  const stroke = L.outline_w ? `-webkit-text-stroke:${Math.min(3, L.outline_w / 3)}px ${L.outline};paint-order:stroke fill;` : "";
  const shadow = L.shadow ? `text-shadow:0 ${L.shadow}px ${L.shadow * 2}px rgba(0,0,0,.6);` : "";
  const box = L.box ? `background:${L.box};padding:2px 8px;border-radius:4px;` : "";
  const txt = w => esc(L.upper ? w.toUpperCase() : w);
  const html = words.map(w => w === "cambia" || w === "CAMBIA"
    ? `<b style="color:${L.accent}${L.alt_font ? `;font-family:'Iman Elegante';font-size:1.5em` : ""}">${txt(w)}</b>` : txt(w)).join(" ");
  return `<span class="sp"><i class="sp-face"></i><em class="sp-text e-${L.entry}" style="font-family:'${CSS_FONT[L.font] || "Iman Moderna"}';font-size:${px}px;color:${L.text};${stroke}${shadow}${box}">${html}</em></span>`;
}
function renderStyles(list, select) {
  const cur = select || $("input[name=style]:checked")?.value;
  $("#styles").innerHTML = list.map((s, i) => `
    <label class="choice style-card ${s.mine ? "mine" : ""}" ${s.notes ? `title="${esc(s.notes)}"` : ""}>
      <input type="radio" name="style" value="${s.key}" data-rhythm="${s.rhythm || ""}" ${(cur ? s.key === cur : i === 0) ? "checked" : ""}>
      <span>${stylePreview(s)}${esc(s.label)}${s.mine ? `<small>Copiado de un reel</small><button type="button" class="link forget" data-style-del="${s.key}" title="Borrar">✕</button>` : ""}</span></label>`).join("");
}
$("#styles").onclick = async e => {
  const del = e.target.closest("[data-style-del]");
  if (!del) return;
  e.preventDefault();
  if (!confirm("¿Borrar este estilo?")) return;
  renderStyles((await api(`/api/styles/${del.dataset.styleDel}`, { method: "DELETE" })).styles);
};
$("#styles").onchange = e => {
  const r = e.target.dataset.rhythm && $(`input[name=rhythm][value="${e.target.dataset.rhythm}"]`);
  if (r) r.checked = true;  // el estilo copiado trae su ritmo
};
$("#copy-style-btn").onclick = () => { $("#copy-style-box").hidden = !$("#copy-style-box").hidden; };
$("#copy-style-go").onclick = async () => {
  const f = $("#copy-style-file").files[0];
  if (!f) return $("#copy-style-file").click();
  const btn = $("#copy-style-go"), msg = $("#copy-style-msg");
  btn.disabled = true; btn.textContent = "Mirando el reel…"; msg.textContent = "";
  const fd = new FormData();
  fd.append("file", f); fd.append("name", $("#copy-style-name").value);
  try {
    const r = await api("/api/styles/copy", { method: "POST", body: fd });
    renderStyles(r.styles, r.key);
    const rh = $(`input[name=rhythm][value="${r.rhythm}"]`); if (rh) rh.checked = true;
    msg.textContent = `Listo: «${r.label}». ${r.notes}`;
    $("#copy-style-file").value = ""; $("#copy-style-name").value = "";
  } catch (err) { msg.textContent = err.message; }
  finally { btn.disabled = false; btn.textContent = "Sacar el estilo"; }
};
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

$("#export-secrets").onchange = e => {
  $("#export-warn").hidden = !e.target.checked;
  $("#export-settings").href = "/api/settings/export" + (e.target.checked ? "?claves=1" : "");
};
$("#import-settings").onchange = async e => {
  const f = e.target.files[0];
  if (!f) return;
  const out = $("#import-result");
  out.hidden = false; out.classList.remove("error"); out.textContent = "Importando…";
  try {
    const fd = new FormData(); fd.append("file", f);
    const { got } = await api("/api/settings/import", { method: "POST", body: fd });
    const parts = ["tus ajustes y lo que Imán recuerda de ti"];
    if (got.marca) parts.push(got.logo ? "Mi marca con el logo" : "Mi marca");
    if (got.claves) parts.push("tus claves de IA");
    if (got.licencia) parts.push("tu licencia");
    out.textContent = "✓ Listo: he traído " + parts.join(", ") + ".";
    await loadSettings();
    api("/api/brand").then(renderBrand);
  } catch (err) {
    out.classList.add("error"); out.textContent = err.message;
  } finally { e.target.value = ""; }
};
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
document.querySelectorAll("[data-test-key]").forEach(btn => btn.onclick = async () => {
  const provider = btn.dataset.testKey, f = $("#settings-form");
  const out = $("#test-" + provider);
  btn.disabled = true; btn.textContent = "Probando…";
  try {
    const r = await api("/api/settings/test-key", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, key: f[provider === "claude" ? "anthropic_key" : "openai_key"].value.trim() }) });
    out.textContent = r.message; out.classList.toggle("error", !r.ok); out.classList.toggle("ok", r.ok);
    if (r.ok) f.provider.value = provider;  // si funciona, la dejamos elegida
  } catch (err) {
    out.textContent = err.message; out.classList.add("error");
  } finally { out.hidden = false; btn.disabled = false; btn.textContent = "Probar mi clave"; }
});
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
// Ideas listas para grabar, según el sector de «Mi marca». No usan la IA: salen siempre.
const TODAY = {
  viajes: [
    ["Cuenta atrás: quedan X días para el viaje", "el grupo que viaja con nosotros", "Crea ganas y recuerda lo que falta"],
    ["Qué meter en la maleta para este destino", "viajeros que salen en unas semanas", "Lista práctica que todos guardan"],
    ["3 errores que comete todo el mundo en este destino", "gente que va por primera vez", "Gancho de error: funciona siempre"],
    ["Lo que nadie te cuenta antes de ir", "viajeros curiosos", "Secretos y consejos de experto"],
    ["Un día del itinerario, hora a hora", "quien duda si apuntarse", "Enseña el viaje por dentro"],
    ["Cuánto cuesta de verdad este viaje", "gente que compara precios", "Transparencia: genera confianza"],
    ["Por qué viajar en grupo con nosotros", "quien viaja solo o en pareja", "Tu diferencia frente a ir por libre"],
    ["Presento al guía o al equipo", "futuros viajeros", "Caras conocidas = más reservas"],
  ],
  cursos: [
    ["El error nº 1 de quien empieza en esto", "principiantes", "Gancho de error"],
    ["Lo que haría si empezara hoy desde cero", "quien quiere empezar", "Consejo de experto"],
    ["Un mito de mi sector que hay que desmontar", "mi audiencia", "Genera debate"],
    ["Antes y después de un alumno", "quien duda si apuntarse", "Prueba social"],
    ["3 pasos para conseguir el primer resultado", "principiantes", "Contenido que se guarda"],
    ["Respondo la pregunta que más me hacen", "mis seguidores", "Fácil de grabar"],
  ],
  productos: [
    ["Cómo se hace nuestro producto por dentro", "clientes curiosos", "Detrás de las cámaras"],
    ["3 formas de usarlo que no conocías", "clientes actuales", "Útil y se comparte"],
    ["Respondo la duda que más nos llega", "quien está a punto de comprar", "Quita objeciones"],
    ["Por qué cuesta lo que cuesta", "gente que compara", "Transparencia"],
    ["Lo nuevo que acaba de llegar", "seguidores", "Novedad con urgencia real"],
    ["Un cliente cuenta su experiencia", "indecisos", "Prueba social"],
  ],
  empresas: [
    ["El problema que resolvemos en 30 segundos", "clientes potenciales", "Claro y directo"],
    ["Un caso real de un cliente", "empresas parecidas", "Prueba social"],
    ["3 señales de que necesitas este servicio", "quien aún no lo sabe", "Gancho de diagnóstico"],
    ["Presento al equipo", "clientes y candidatos", "Confianza"],
    ["Lo que nadie te cuenta de mi sector", "clientes potenciales", "Autoridad"],
    ["Cómo trabajamos, paso a paso", "quien está comparando", "Quita miedos"],
  ],
  general: [
    ["Lo que he aprendido esta semana", "mis seguidores", "Fácil y cercano"],
    ["3 consejos que me hubiera gustado saber antes", "quien empieza", "Se guarda y se comparte"],
    ["Un error que cometí y cómo lo arreglé", "mi audiencia", "Historia personal"],
    ["Respondo la pregunta que más me hacen", "mis seguidores", "Fácil de grabar"],
    ["Mi opinión sincera sobre un tema de moda", "mi audiencia", "Genera comentarios"],
    ["Un día conmigo en 60 segundos", "seguidores nuevos", "Te conocen mejor"],
  ],
};
let todayAt = 0;
function renderToday() {
  const list = TODAY[state.brand?.sector] || TODAY.general;
  const pick = Array.from({ length: Math.min(3, list.length) }, (_, k) => list[(todayAt + k) % list.length]);
  $("#today").innerHTML = pick.map(([t, a, why]) =>
    `<button type="button" data-topic="${esc(t)}" data-audience="${esc(a)}">${esc(t)}<small>${esc(why)}</small></button>`).join("");
}
$("#today-more").onclick = () => { todayAt += 3; renderToday(); };
$("#today").onclick = e => {
  const b = e.target.closest("button[data-topic]");
  if (!b) return;
  const f = $("#idea-form");
  f.topic.value = b.dataset.topic;
  if (!f.audience.value.trim()) f.audience.value = b.dataset.audience;
  f.topic.focus(); f.topic.select();
  f.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
};
renderToday();
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
state.broll = [];
const MODES = {
  camara: { title: "Arrastra tu vídeo aquí", hint: "o pulsa para elegirlo · MP4, MOV", accept: "video/*",
    broll: "＋ Vídeos o fotos de apoyo", brollHint: "Opcional. Imán los pone a pantalla completa en el momento justo, con tu cara en un círculo." },
  voz: { title: "Arrastra tu audio aquí", hint: "una nota de voz o un vídeo del que solo quieres la voz · M4A, MP3, WAV, MP4", accept: "audio/*,video/*",
    broll: "＋ Fotos o vídeos para acompañar (opcional)", brollHint: "Sin ellos, tu voz va sobre un fondo con tus colores y subtítulos grandes." },
  vozclips: { title: "Arrastra tu voz aquí", hint: "una nota de voz o un vídeo del que solo quieres la voz", accept: "audio/*,video/*",
    broll: "＋ Tus vídeos y fotos", brollHint: "Imán va cambiando de plano al ritmo de lo que dices." },
  largo: { title: "Arrastra tu vídeo largo aquí", hint: "un directo, una clase o un podcast · Imán saca los mejores momentos", accept: "video/*" },
};
const mode = () => $("input[name=mode]:checked").value;
function canGo() {
  $("#to-edit").disabled = !state.file || (mode() === "vozclips" && !state.broll.length);
}
function setMode() {
  const m = MODES[mode()];
  $("#drop-title").textContent = m.title; $("#drop-hint").textContent = m.hint;
  $("#file").accept = m.accept;
  $("#broll-box").hidden = !m.broll;
  $("#bg-box").hidden = mode() !== "camara";
  if (m.broll) { $("#broll-title").textContent = m.broll; $("#broll-hint").textContent = m.brollHint; }
  canGo();
}
$("#modes").onchange = setMode;
function pick(file) {
  if (!file || !(file.type.startsWith("video") || (mode().startsWith("voz") && file.type.startsWith("audio")))) return;
  state.file = file;
  const v = $("#preview");
  $(".drop-inner").hidden = true;
  if (file.type.startsWith("audio")) {
    v.hidden = true;
    $("#audio-picked").hidden = false; $("#audio-picked").textContent = `🎙 ${file.name}`;
  } else {
    $("#audio-picked").hidden = true;
    v.src = URL.createObjectURL(file); v.hidden = false; v.play();
  }
  $("#picked-name").textContent = file.name; $("#picked-row").hidden = false;
  canGo();
}
function renderBroll() {
  $("#broll-list").innerHTML = state.broll.map((f, i) => `
    <figure>${f.type.startsWith("image") ? `<img src="${URL.createObjectURL(f)}" alt="">` : `<video src="${URL.createObjectURL(f)}#t=0.5" muted></video>`}
      <figcaption>${i + 1}</figcaption><button type="button" data-unbroll="${i}" title="Quitar">✕</button></figure>`).join("");
  canGo();
}
$("#broll").onchange = e => {
  state.broll = [...state.broll, ...[...e.target.files].filter(f => /^(video|image)\//.test(f.type))].slice(0, 12);
  e.target.value = ""; renderBroll();
};
$("#broll-list").onclick = e => {
  const b = e.target.closest("[data-unbroll]");
  if (b) { state.broll.splice(+b.dataset.unbroll, 1); renderBroll(); }
};
setMode();
$("#file").onchange = e => pick(e.target.files[0]);
drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = e => { e.preventDefault(); drop.classList.remove("over"); pick(e.dataTransfer.files[0]); };
$("#to-edit").onclick = () => go("edit");
// Empezar de cero: olvida el vídeo elegido y el reel abierto (el anterior sigue en «Mis reels»).
function clearUpload() {
  state.file = null; state.broll = []; renderBroll();
  const v = $("#preview"); v.pause(); v.removeAttribute("src"); v.hidden = true;
  $("#audio-picked").hidden = true; $(".drop-inner").hidden = false; $("#picked-row").hidden = true;
  $("#file").value = ""; $("#music-file").value = "";
  canGo();
}
function newReel() {
  clearTimeout(state.poll);
  clearUpload();
  state.job = null;
  for (const id of ["#hook-title", "#hook-template", "#instructions", "#chat-input"]) if ($(id)) $(id).value = "";
  $("#out").pause?.(); $("#out").removeAttribute("src");
  renderInstrIdeas();
  go("upload");
}
$("#new-reel").onclick = newReel;
$("#change-file").onclick = e => { e.preventDefault(); clearUpload(); $("#file").click(); };

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
  fd.append("remember", $("#remember").checked);
  fd.append("mode", mode() === "vozclips" ? "voz" : mode());
  const bg = mode() === "camara" ? $("input[name=background]:checked").value : "";
  fd.append("background", bg === "foto" && !$("#bg-photo").files[0] ? "" : bg);
  if (bg === "foto" && $("#bg-photo").files[0]) fd.append("background_photo", $("#bg-photo").files[0]);
  fd.append("sfx", $("#sfx").checked);
  fd.append("punch", $("#punch").checked);
  const ms = $("#music-style").value;
  if (ms === "mia" && $("#music-file").files[0]) fd.append("music_file", $("#music-file").files[0]);
  else fd.append("music_style", ms === "mia" ? "" : ms);  // «Mi música» sin canción elegida: sin música
  if (mode() !== "largo") state.broll.forEach(f => fd.append("broll", f));
  showWorking(mode() === "largo" ? "Subiendo tu vídeo largo" : "Subiendo tu vídeo", 0.01);
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
    if (j.result?.clips) return showClips(j);
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
    state.job = await api(`/api/jobs/${state.job.id}/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: msg, remember: $("#chat-remember").checked }) });
    if ($("#chat-remember").checked) { $("#chat-remember").checked = false; loadMemory(); }
    renderChat(state.job);
    poll();
  } catch (err) {
    renderChat({ chat: [...(state.job.chat || []), { role: "user", text: msg }, { role: "iman", text: err.message }] });
    if (state.job.result) showResult(state.job); else showError(err.message);
  }
};
// Ideas para «Dímelo como a tu editor», según lo que ya lleva el reel y el sector de «Mi marca».
// Sin IA: salen al momento y nadie se queda en blanco.
const CHAT_IDEAS = {
  sin_titular: "Pon un titular grande al principio que enganche",
  sin_lista: "Cuando enumero cosas, ponlas en una lista que vaya apareciendo",
  sin_palabra: "Pon en grande la palabra más importante de cada frase",
  sin_cta: "Termina con una llamada a la acción: escríbeme por privado",
  sin_cifra: "Cuando diga un número o un precio, que salga en grande",
  sin_comentario: "Abre con un comentario de un seguidor preguntando esto",
  arranque: "Empieza directamente en la frase más potente, sin saludar",
  zoom: "Haz zoom en los momentos importantes para que tenga más ritmo",
  emojis: "Añade algún emoji en los subtítulos donde encaje",
  corto: "Déjalo en menos de 30 segundos con lo mejor",
};
const SECTOR_IDEAS = {
  viajes: ["Pon el itinerario del viaje con la ruta de ciudad en ciudad y las fechas", "Pon una cuenta atrás con los días que quedan para el viaje", "Al final, pon «Plazas limitadas» y que nos escriban por privado"],
  cursos: ["Al final, invita a apuntarse al curso con un enlace en la bio", "Pon en pantalla los 3 pasos que explico"],
  productos: ["Que salga el precio en grande cuando lo diga", "Termina con «pídelo por privado»"],
  empresas: ["Pon un dato o cifra de clientes en grande", "Termina con «pide tu presupuesto sin compromiso»"],
};
function renderChatIdeas(j) {
  const kinds = new Set((j.result?.plan?.effects || []).filter(fx => !fx.off).map(fx => fx.type));
  const out = [];
  if (!kinds.has("titular") && !j.result?.plan?.hook_title) out.push(CHAT_IDEAS.sin_titular);
  for (const k of ["lista", "palabra", "cta", "cifra", "comentario"]) if (!kinds.has(k)) out.push(CHAT_IDEAS["sin_" + k]);
  out.push(...(SECTOR_IDEAS[state.brand?.sector] || []));
  out.push(CHAT_IDEAS.arranque, CHAT_IDEAS.zoom);
  if ((j.result?.duration_out || 0) > 40) out.push(CHAT_IDEAS.corto);
  // Primero las del sector y lo que falta, sin pasarse: 6 como mucho.
  const sector = SECTOR_IDEAS[state.brand?.sector] || [];
  const picked = [...sector.slice(0, 2), ...out.filter(t => !sector.includes(t))].slice(0, 6);
  $("#chat-ideas").innerHTML = picked.map(t => `<button type="button" data-idea="${esc(t)}">${esc(t)}</button>`).join("");
}
// Las mismas ideas en el paso 2, antes de editar: aquí se suman en varias líneas.
const FIRST_IDEAS = [
  "Que tenga mucho movimiento: efectos variados, zooms y textos grandes",
  "Cuando enumere cosas, ponlas en una lista que se vaya marcando",
  "Pon en grande las palabras y cifras importantes",
  "Empieza directamente en la frase más potente, sin saludar",
  "Quita todas las muletillas y las veces que me equivoco",
  "Termina con una llamada a la acción: que me escriban por privado",
];
function renderInstrIdeas() {
  const list = [...(SECTOR_IDEAS[state.brand?.sector] || []).slice(0, 2), ...FIRST_IDEAS].slice(0, 7);
  $("#instr-ideas").innerHTML = list.map(t => `<button type="button" data-idea="${esc(t)}">${esc(t)}</button>`).join("");
}
$("#instr-ideas").onclick = e => {
  const b = e.target.closest("[data-idea]");
  if (!b) return;
  const t = $("#instructions"), line = b.dataset.idea;
  if (!t.value.includes(line)) t.value = (t.value.trim() ? t.value.trim() + "\n" : "") + line;
  b.classList.add("on");
};
renderInstrIdeas();
$("#chat-ideas").onclick = e => {
  const b = e.target.closest("[data-idea]");
  if (!b) return;
  const input = $("#chat-input");
  input.value = b.dataset.idea; input.focus(); input.setSelectionRange(input.value.length, input.value.length);
};
const FX_NAMES = { lista: "Lista", palabra: "Palabra gigante", titular: "Titular", cifra: "Cifra", frase: "Frase", tecleo: "Texto que se escribe",
  color: "Golpe de color", comentario: "Comentario", contador: "Contador", portada: "Portada de revista", cta: "Llamada a la acción",
  dato: "Dato", bruto: "Toma en bruto", fantasma: "Eco", pagina: "Página de revista", detras: "Texto detrás de ti",
  fondo: "Fondo de color", desenfoque: "Fondo desenfocado", ubicacion: "Ubicación", objeto: "Objeto", viaje: "Itinerario del viaje", oferta: "Oferta", ruta: "Ruta",
  testimonio: "Testimonio", plazas: "Plazas", precio: "Precio", apoyo: "Vídeo de apoyo",
  notificaciones: "Notificaciones", foco: "Foco", anillo: "Anillo de texto",
  sube: "Sube con tu dedo", choque: "El choque", aparece: "Aparece donde señalas" };
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

// ---------- carrusel e historias ----------
function renderKit(k) {
  const url = n => `/api/jobs/${state.job.id}/kit/${n}?v=${k.version}`;
  $("#kit-carousel").innerHTML = k.carousel.map(n => `<a href="${url(n)}" target="_blank"><img src="${url(n)}" alt="" loading="lazy"></a>`).join("");
  $("#kit-stories").innerHTML = k.stories.map(n => `<a href="${url(n)}" target="_blank"><img src="${url(n)}" alt="" loading="lazy"></a>`).join("");
  $("#kit-dl").href = url("kit.zip");
  $("#kit-reply").textContent = k.reply || "";
  $("#kit-box").hidden = false;
}
async function makeKit(message = "") {
  const btn = $("#kit-btn");
  btn.disabled = true; btn.textContent = message ? "Cambiándolo…" : "Preparándolo…";
  try { renderKit(await postJSON(`/api/jobs/${state.job.id}/kit`, { message })); }
  catch (err) { $("#kit-reply").textContent = err.message; $("#kit-box").hidden = false; }
  finally { btn.disabled = false; btn.textContent = "✦ Rehazlo"; }
}
$("#kit-btn").onclick = () => makeKit();
$("#kit-form").onsubmit = e => {
  e.preventDefault();
  const m = $("#kit-input").value.trim();
  if (m) { $("#kit-input").value = ""; makeKit(m); }
};

// ---------- revisa lo que dices ----------
async function loadPhrases(j) {
  $("#phrases-apply").hidden = true;
  let list = [];
  try { list = (await api(`/api/jobs/${j.id}/review`)).phrases; } catch { /* reels antiguos sin plan */ }
  $("#review-box").hidden = !list.length;
  const out = list.filter(p => p.state !== "dentro").length;
  $("#review-box summary").textContent = `Revisa lo que dices · ${list.length} frases${out ? `, ${out} con cortes` : ""}`;
  $("#phrases").innerHTML = list.map(p => `
    <div class="phrase ${p.state}" data-from="${p.from}" data-to="${p.to}" data-keep="${p.state !== "fuera"}">
      <span class="t">${fmt(p.start)}</span>
      <span class="grow"><span class="txt">${esc(p.text)}</span>${p.reason ? `<small>${esc(p.reason)}${p.state === "parte" ? " · una parte" : ""}</small>` : ""}</span>
      <button type="button" class="link">${p.state === "fuera" ? "Recuperar" : "Quitar"}</button>
    </div>`).join("");
}
$("#phrases").onclick = e => {
  const b = e.target.closest("button");
  if (!b) return;
  const row = b.closest(".phrase"), keep = row.dataset.keep !== "true";
  row.dataset.keep = keep; row.dataset.changed = "1";
  row.classList.toggle("fuera", !keep); row.classList.toggle("dentro", keep); row.classList.remove("parte");
  b.textContent = keep ? "Quitar" : "Recuperar";
  $("#phrases-apply").hidden = false;
};
$("#phrases-apply").onclick = async () => {
  const phrases = $$("#phrases .phrase[data-changed]").map(r => ({ from: +r.dataset.from, to: +r.dataset.to, keep: r.dataset.keep === "true" }));
  showWorking("Aplicando cambios", 0.02);
  try { state.job = await postJSON(`/api/jobs/${state.job.id}/plan`, { phrases }); poll(); }
  catch (err) { showError(err.message); }
};

// ---------- lo que Imán recuerda ----------
async function loadMemory() {
  const { memory } = await api("/api/memory");
  $("#memory-empty").hidden = memory.length > 0;
  $("#memory-list").innerHTML = memory.map((m, i) => `<li><span>${esc(m)}</span><button type="button" class="link" data-forget="${i}" title="Olvidar">✕</button></li>`).join("");
  $("#memory-hint").hidden = !memory.length;
  $("#memory-hint").textContent = memory.length ? `Ya recuerdo ${memory.length} ${memory.length === 1 ? "preferencia tuya" : "preferencias tuyas"}: las aplico solas.` : "";
}
$("#memory-list").onclick = async e => {
  const b = e.target.closest("[data-forget]");
  if (b) { await api(`/api/memory/${b.dataset.forget}`, { method: "DELETE" }); loadMemory(); }
};
loadMemory();

function showClips(j) {
  // Vídeo largo → varios reels: los enseñamos todos y cada uno se abre como un reel normal.
  $("#working").hidden = true; $("#download").hidden = true;
  $("#clips").hidden = false; $("#result-tools").hidden = true;
  const first = j.result.clips[0];
  if (first) { $("#out").src = `/api/jobs/${first.id}/reel.mp4`; $("#out").hidden = false; }
  $("#clips").innerHTML = `<h3>He sacado ${j.result.clips.length} reels de tu vídeo</h3><div class="library">` + j.result.clips.map(c => `
    <div class="reel-card" data-open-clip="${c.id}" role="button" tabindex="0">
      <img src="/api/jobs/${c.id}/reel.jpg" alt="" loading="lazy">
      <div><strong>${esc(c.title || "Sin título")}</strong><span>${fmt(c.duration)}${c.why ? " · " + esc(c.why) : ""}</span></div>
    </div>`).join("") + `</div><p class="hint">Están también en tu biblioteca. Abre uno para cambiarlo, hacer su carrusel o descargarlo.</p>`;
  loadLibrary();
}
$("#clips").onclick = async e => {
  const card = e.target.closest("[data-open-clip]");
  if (!card) return;
  state.job = await api(`/api/jobs/${card.dataset.openClip}`);
  showResult(state.job);
};
function showResult(j) {
  const om = j.options && j.options.music;
  const used = om === "auto" ? (j.result.plan.music || "") : om === true ? "mia" : (om || "");
  if (used === "mia" && !$("#re-music option[value=mia]")) $("#re-music").insertAdjacentHTML("beforeend", `<option value="mia">Mi música</option>`);
  $("#re-music").value = used;
  $("#clips").hidden = true; $("#result-tools").hidden = false; $("#download").hidden = false;
  renderChat(j);
  renderChatIdeas(j);
  $("#kit-box").hidden = true; $("#kit-btn").textContent = "✦ Hazme el carrusel y las historias";
  loadPhrases(j);
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
  $("#hook-box").innerHTML = (r.ai_warning ? `<div class="card warn"><p>${esc(r.ai_warning)}</p><p class="hint">El reel está cortado y con subtítulos, pero sin los efectos de la IA.</p></div>` : "")
    + (p.hook_title ? `<div class="card"><h4>${esc(p.hook_title)}</h4><p class="hint">Gancho en pantalla</p></div>` : "")
    + (p.hook_line ? `<div class="card"><p>«${esc(p.hook_line)}»</p><p class="hint">Si quieres regrabar el arranque, prueba con esta frase.</p></div>` : "");
}
async function reedit(changes) {
  if (!state.job || state.job.status === "working") return;
  showWorking("Aplicando cambios", 0.02);
  try {
    state.job = await api(`/api/jobs/${state.job.id}/reedit`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(changes) });
    poll();
  } catch (err) { showError(err.message); }
}
$$(".quick:not(.ideas) button").forEach(b => b.onclick = () => reedit(
  b.dataset.rhythm ? { rhythm: b.dataset.rhythm } : b.dataset.background !== undefined ? { background: b.dataset.background } : { style: b.dataset.style }));
// Fondo: «Mi foto» pide elegir la imagen; solo tiene sentido cuando hablas a cámara.
$("#bg-choices").onchange = () => {
  const foto = $("input[name=background]:checked").value === "foto";
  $("#bg-photo-pick").hidden = !foto;
  if (foto && !$("#bg-photo").files[0]) $("#bg-photo").click();
};
api("/api/music").then(list => {
  const opts = list.map(m => `<option value="${m.key}">${esc(m.label)}</option>`).join("");
  $("#music-style").insertAdjacentHTML("beforeend", opts);
  $("#re-music").insertAdjacentHTML("beforeend", opts);
}).catch(() => {});
$("#re-music").onchange = e => reedit({ music: e.target.value });
$("#music-style").onchange = () => {
  const v = $("#music-style").value;
  $("#music-pick").hidden = v !== "mia";
  $("#music-play").hidden = !v || v === "mia" || v === "auto";
  const a = $("#music-audio"); a.pause(); $("#music-play").textContent = "▶ Escuchar";
  if (v === "mia" && !$("#music-file").files[0]) $("#music-file").click();
};
$("#music-play").onclick = () => {
  const a = $("#music-audio"), v = $("#music-style").value;
  if (!a.paused) { a.pause(); $("#music-play").textContent = "▶ Escuchar"; return; }
  a.src = `/api/music/${v}.wav`; a.play();
  $("#music-play").textContent = "■ Parar";
  a.onended = () => $("#music-play").textContent = "▶ Escuchar";
};
$("#music-file").onchange = e => {
  const f = e.target.files[0];
  $("#music-name").textContent = f ? `✓ ${f.name} · baja sola cuando hablas` : "Elige tu canción.";
};
$("#bg-photo").onchange = e => {
  const f = e.target.files[0];
  $("#bg-photo-name").hidden = !f; $("#bg-photo-name").textContent = f ? `✓ ${f.name}` : "";
};
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
  renderToday();
  renderInstrIdeas();
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
