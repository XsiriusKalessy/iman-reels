const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const state = { file: null, takes: [], job: null, settings: null, poll: null };

function go(step) {
  if (step === "home") loadLibrary();
  const swap = () => {
    $$(".panel").forEach(p => p.classList.toggle("show", p.dataset.panel === step));
    $$("#steps button").forEach(b => b.classList.toggle("active", b.dataset.step === step));
    movePill();
    window.scrollTo({ top: 0 });
  };
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (document.startViewTransition && !calm) document.startViewTransition(swap); else swap();
}
// La píldora del paso activo se desliza de un paso a otro.
function movePill() {
  const nav = document.getElementById("steps");
  if (!nav) return;
  let pill = nav.querySelector(".pill-bg");
  if (!pill) { pill = document.createElement("span"); pill.className = "pill-bg"; nav.prepend(pill); }
  const b = nav.querySelector("button.active");
  if (!b) { pill.style.opacity = 0; return; }
  pill.style.opacity = 1;
  pill.style.width = `${b.offsetWidth}px`;
  pill.style.transform = `translateX(${b.offsetLeft}px)`;
}
addEventListener("resize", () => movePill());
// Las listas entran escalonadas: cada hijo sabe su número.
new MutationObserver(muts => {
  for (const m of muts) [...m.target.children].forEach((c, i) => c.style.setProperty("--i", Math.min(i, 12)));
}).observe(document.body, { childList: true, subtree: true });
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

// Copiar al portapapeles también fuera de https (p. ej. abriendo Imán desde otro aparato de casa).
async function copyText(text, el) {
  try { if (navigator.clipboard?.writeText) { await navigator.clipboard.writeText(text); return true; } } catch {}
  try {
    const ta = el && el.tagName === "TEXTAREA" ? el : Object.assign(document.body.appendChild(document.createElement("textarea")), { value: text });
    ta.select(); const ok = document.execCommand("copy"); if (ta !== el) ta.remove(); return ok;
  } catch { return false; }
}
// ---------- opciones ----------
async function loadOptions() {
  const o = await api("/api/options");
  $("#rhythms").innerHTML = o.rhythms.map((r, i) => `
    <label class="choice"><input type="radio" name="rhythm" value="${r.key}" ${i === 0 ? "checked" : ""}>
    <span>${esc(r.label)}${i === 0 ? '<b class="tag">recomendado</b>' : ""}<small>${esc(r.description)}</small></span></label>`).join("");
  state.options = o;
  renderStyles(o.styles);
  $("#packs").innerHTML = o.packs.map(p => `
    <label class="choice"><input type="radio" name="pack" value="${p.key}" ${p.key === "general" ? "checked" : ""}>
    <span>${esc(p.label)}<small>${esc(p.description)}</small></span></label>`).join("");
  $("#redes").innerHTML = (o.redes || []).map((r, i) => `
    <label class="choice"><input type="radio" name="red" value="${r.key}" ${i === 0 ? "checked" : ""}>
    <span>${esc(r.label)}<small>${esc(r.description)}</small></span></label>`).join("");
  $("#brand-sector").innerHTML = o.packs.map(p => `<option value="${p.key}">${esc(p.label)}</option>`).join("");
  $("#packs").onchange = () => applyPack(false);
  renderHooks(o.hook_templates);
  renderGanchos(o.ganchos || []);
}
// Ganchos visuales: el desplegable del ajuste fino y la biblioteca con lo que conviene grabar al principio.
function ganchoOf(key) { return (state.options?.ganchos || []).find(g => g.key === key); }
function renderGanchos(list) {
  $("#gancho").innerHTML = `<option value="auto">Que lo elija Imán</option>` + list.map(g => `<option value="${g.key}">${esc(g.label)}</option>`).join("");
  $("#gancho-cards").innerHTML = list.map(g => `<div class="card gancho-card" data-gancho-pick="${g.key}"><h4>${esc(g.label)}</h4><p>${esc(g.description)}</p>${g.record ? `<p class="hint">🎥 ${esc(g.record)}</p>` : ""}</div>`).join("");
  ganchoTip();
}
function ganchoTip() {
  const g = ganchoOf($("#gancho").value);
  $("#gancho-tip").textContent = g ? `${g.description}${g.record ? " 🎥 " + g.record : ""}` : "Imán mira lo que dices y cómo está grabado y elige el gancho; luego puedes probar otros con un clic.";
}
$("#gancho").onchange = ganchoTip;
$("#gancho-cards").onclick = e => {
  const c = e.target.closest("[data-gancho-pick]");
  if (!c) return;
  $("#gancho").value = c.dataset.ganchoPick;
  ganchoTip();
  $("#gancho-lib").open = false;
};
// Galería de estilos: cada tarjeta enseña el texto moviéndose como saldrá en el reel.
const CSS_FONT = { "Montserrat Black": "Iman Impacto", "Anton": "Iman Condensada", "Playfair Display ExtraBold": "Iman Elegante",
  "Caveat": "Iman Manuscrita", "Figtree ExtraBold": "Iman Moderna", "Figtree SemiBold": "Iman Ligera",
  "Bebas Neue": "Iman Bebas", "Archivo Black": "Iman Bloque", "Bangers": "Iman Comic", "Poppins ExtraBold": "Iman Hormozi" };
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
  // Con tu vídeo elegido, la tarjeta enseña un fotograma tuyo (cada estilo uno distinto) y su paleta.
  const n = state.styleList ? state.styleList.indexOf(s) + 1 : 0;
  const frame = state.frames?.length ? state.frames[n % state.frames.length] : "";
  const bg = frame ? ` style="background-image:url(${frame})"` : "";
  const dots = [L.text, L.accent, L.outline_w ? L.outline : "", L.box || ""].filter(Boolean)
    .map(c => `<i style="background:${c}"></i>`).join("");
  return `<span class="sp${frame ? " has-frame" : ""}"${bg}>${frame ? "" : '<i class="sp-face"></i>'}<span class="sp-dots">${dots}</span><em class="sp-text e-${L.entry}" style="font-family:'${CSS_FONT[L.font] || "Iman Moderna"}';font-size:${px}px;color:${L.text};${stroke}${shadow}${box}">${html}</em></span>`;
}
// Primera tarjeta: «Recomendado», marcado de serie. La IA elige el estilo para cada vídeo;
// la vista previa enseña el del sector mientras tanto.
function autoStyleCard(list, cur) {
  const p = state.options?.packs.find(x => x.key === $("input[name=pack]:checked")?.value);
  const s = list.find(x => x.key === (p?.style || "hormozi")) || list[0];
  return `<label class="choice style-card recommended" title="Imán elige el estilo que mejor vende tu vídeo">
      <input type="radio" name="style" value="auto" ${!cur || cur === "auto" ? "checked" : ""}>
      <span>${s ? stylePreview(s) : ""}Automático<b class="tag">recomendado</b><small>Imán lo elige según tu vídeo</small></span></label>`;
}
function renderStyles(list, select) {
  state.styleList = list;
  const cur = select || $("input[name=style]:checked")?.value;
  $("#styles").innerHTML = autoStyleCard(list, cur) + list.map(s => `
    <label class="choice style-card ${s.mine ? "mine" : ""}" ${s.notes ? `title="${esc(s.notes)}"` : ""}>
      <input type="radio" name="style" value="${s.key}" data-rhythm="${s.rhythm || ""}" ${cur && s.key === cur ? "checked" : ""}>
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
  // El sector no pisa la elección: solo cambia la vista previa de «Recomendado».
  if (state.styleList) renderStyles(state.styleList);
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
  f.pexels_key.placeholder = s.has_pexels_key ? "Guardada ✓ (escribe para cambiarla)" : "Tu clave de Pexels";
  $("#own-keys").open = s.provider === "claude" || s.provider === "openai";
  const ok = s.provider === "iman" || (s.provider === "claude" && s.has_anthropic_key) || (s.provider === "openai" && s.has_openai_key);
  $("#ai-hint").innerHTML = ok
    ? `Edita con ${NAMES[s.provider]}.`
    : `Sin IA: cortaré silencios y repeticiones igualmente. <a href="#" id="hint-settings">Activa la IA</a> para el gancho, los efectos y las instrucciones.`;
  renderLicense(s.license);
  f.ligero.value = s.ligero || "auto";
  const eq = s.equipo;
  if (eq) $("#equipo-hint").textContent = `Tu ordenador: ${eq.cores} núcleos, ${eq.ram_gb} GB de memoria${eq.gpu ? " y tarjeta gráfica" : ""}. ` +
    (eq.weak ? "Es sencillo, así que en automático Imán se salta lo más pesado (texto detrás de ti, anillo, lluvia, 3D y 4K) para que vaya rápido."
             : "Tiene potencia de sobra: en automático usa todos los efectos.");
}

function renderLicense(l) {
  const pill = $("#trial-pill");
  $("#license-error").hidden = true;
  $("#license-active").hidden = !l.licensed;
  $("#license-activate").hidden = $("#license-buy").hidden = l.licensed;
  if (l.licensed) {
    const until = l.expires ? ` hasta el ${new Date(l.expires).toLocaleDateString("es-ES")}` : "";
    $("#license-status").textContent = l.plan === "dueno"
      ? "Licencia de dueño: todas las opciones, también las Pro, sin límites de IA y para siempre."
      : `${l.plan_label || "Licencia"} activa${until}. Gracias por confiar en Imán.`;
    pill.hidden = true;
  } else {
    const left = l.free_left;
    $("#license-status").textContent = l.expired
      ? "Tu licencia de prueba ha terminado. Gracias por probar Imán. Si te ha servido, la licencia de fundador cuesta 79 € al año y ese precio se te queda mientras renueves. Tus reels y tu marca siguen aquí."
      : left
      ? `Estás probando Imán: te quedan ${left} ${left === 1 ? "reel" : "reels"} gratis (con marca de agua).`
      : "Has usado tus reels de prueba. Activa tu licencia para seguir editando sin marca de agua.";
    pill.hidden = l.dev;
    pill.textContent = l.expired ? "Licencia caducada" : left ? `Prueba · ${left} gratis` : "Activa tu licencia";
    pill.classList.toggle("warn", !left);
  }
}
$("#trial-pill").onclick = e => { e.preventDefault(); $("#settings").showModal(); };
$("#feedback-btn").onclick = async () => {
  const msg = $("#feedback-msg");
  try {
    const i = await api("/api/soporte");
    const text = `Imán ${i.version} · ${i.system} · ${i.plan} · ${i.reels} reels hechos` +
      (i.last_error ? `\nÚltimo error: ${i.last_error}` : "") + "\n\nQué ha pasado o qué mejorarías:\n";
    let copied = true;
    copied = await copyText(text);
    if (i.feedback_url) window.open(i.feedback_url, "_blank", "noopener");
    msg.textContent = (copied ? "Datos copiados. Pégalos en el mensaje" : "Copia estos datos en el mensaje:\n" + text) +
      (i.feedback_url ? " del formulario que se ha abierto." : " y mándalos por WhatsApp o correo a quien te dio Imán.");
  } catch (err) { msg.textContent = err.message; }
  msg.hidden = false;
};
$("#logs-btn").onclick = async () => {
  try { await api("/api/soporte/registros", { method: "POST" }); }
  catch (err) { $("#feedback-msg").textContent = err.message; $("#feedback-msg").hidden = false; }
};
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
  try {
    await api("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    f.anthropic_key.value = ""; f.openai_key.value = ""; f.pexels_key.value = "";
    await loadSettings();
    $("#settings").close();
  } catch (err) { $("#license-error").textContent = err.message; $("#license-error").hidden = false; }
};
// Enter en un campo guarda, no cierra sin guardar.
$("#settings-form").addEventListener("submit", e => { if (!e.submitter || e.submitter.value !== "cancel") { e.preventDefault(); $("#save-settings").click(); } });
$("#brand-form").addEventListener("submit", e => { if (!e.submitter || e.submitter.value !== "cancel") { e.preventDefault(); $("#brand-save").click(); } });

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
      <div class="card"><h4>${esc(i.hook)}</h4><p>${esc(i.script)}</p>${i.loop && i.loop.mystery ? `
      <div class="open-loop"><b>Bucle abierto</b><span>🔒 Abres: ${esc(i.loop.mystery)}</span>${(i.loop.clues || []).map(c => `<span>👀 Pista: ${esc(c)}</span>`).join("")}<span>🔓 Lo resuelves: ${esc(i.loop.payoff)}</span></div>` : ""}
      <p class="hint">${esc(i.why)}</p>
      <button class="ghost use-idea" data-hook="${esc(i.hook)}">Grabar esta →</button></div>`).join("");
  } catch (err) {
    $("#ideas").innerHTML = `<p class="error">${esc(err.message)}</p>`;
  } finally { btn.disabled = false; btn.textContent = "Dame 3 ideas"; }
};
document.addEventListener("click", e => {
  const b = e.target.closest(".use-idea");
  if (!b) return;
  showHook(b.dataset.hook);
  go("upload");
});

// Nota de viralidad: lo que retiene, medido sobre este reel, y los tres cambios que más suman.
function renderViral(v) {
  const box = $("#viral-box");
  if (!v || typeof v.score !== "number") { box.hidden = true; return; }
  box.hidden = false;
  const cls = v.score >= 70 ? "good" : v.score >= 50 ? "mid" : "low";
  box.innerHTML = `<div class="viral-head"><div class="viral-score ${cls}"><b>${v.score}</b><span>/100</span></div>
    <div><h4>Nota de viralidad: ${esc(v.label)}</h4><p class="hint">No adivina las visitas: mide lo que retiene (gancho, arranque, duración, ritmo, cambios en pantalla, subtítulos, música, cierre).</p></div></div>
    ${(v.tips || []).length ? `<p class="hint">Lo que más sumaría:</p><ul class="checks">${v.tips.map(t => `<li class="warn">↑ ${esc(t)}</li>`).join("")}</ul>` : `<p class="hint">Está redondo. A publicar.</p>`}
    <div class="viral-bars">${(v.items || []).map(i => `<div title="${esc(i.text)}"><span style="width:${Math.round(100 * i.points / i.max)}%"></span></div>`).join("")}</div>`;
}

// Modo agencia de viajes: destino y fechas → reel listo para grabar.
$("#agency-form").onsubmit = async e => {
  e.preventDefault();
  const btn = e.target.querySelector("button[type=submit]");
  btn.disabled = true; btn.textContent = "Preparando…";
  const out = $("#agency-out");
  try {
    const body = Object.fromEntries(new FormData(e.target));
    const r = await api("/api/agencia", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    state.agency = r;
    out.innerHTML = `
      <div class="cards">
        <div class="card"><h4>Ganchos</h4>${(r.hooks || []).map(h => `<p class="hook-line">«${esc(h)}»</p>`).join("")}<p class="hint">${esc(r.why || "")}</p></div>
        <div class="card"><h4>Guion (una toma)</h4><p class="script">${esc(r.script || "").replace(/\n/g, "<br>")}</p>
          <button class="primary" type="button" id="agency-use">Grabar este →</button></div>
        <div class="card"><h4>Qué grabar o pedir a los viajeros</h4><ul class="checks">${(r.shots || []).map(x => `<li class="ok">🎥 ${esc(x)}</li>`).join("")}</ul>
          ${r.route_text ? `<p class="hint">Mapa 3D: ${esc((r.route || []).map(x => x.name).join(" › "))}. Imán lo dibuja solo cuando cuentes el recorrido.</p>` : ""}</div>
        <div class="card"><h4>Instagram</h4><p class="script">${esc(r.post || "").replace(/\n/g, "<br>")}</p><button class="ghost small" type="button" data-copy="post">Copiar</button></div>
        <div class="card"><h4>WhatsApp</h4><p class="script">${esc(r.whatsapp || "").replace(/\n/g, "<br>")}</p><button class="ghost small" type="button" data-copy="whatsapp">Copiar</button></div>
      </div>`;
    out.querySelectorAll("[data-copy]").forEach(b => b.onclick = () => { navigator.clipboard.writeText(r[b.dataset.copy] || ""); b.textContent = "Copiado"; });
    $("#agency-use").onclick = () => {
      showHook((r.hooks || [])[0] || "");
      const inst = $("#instructions");
      const route = r.route_text ? `Si cuento el recorrido, usa el efecto "viaje" con estas paradas: ${r.route_text}${body.dates ? ` (subtitle: ${body.dates})` : ""}.` : "";
      if (inst && route) inst.value = (inst.value ? inst.value + "\n" : "") + route;
      go("upload");
    };
  } catch (err) {
    out.innerHTML = `<p class="error">${esc(err.message)}</p>`;
  } finally { btn.disabled = false; btn.textContent = "Prepárame el reel"; }
};

// Calendario de contenido: qué grabar cada día, y descarga para el calendario del móvil.
const KIND_NAMES = { venta: "Vende", valor: "Da valor", detras: "Cómo trabajas", testimonio: "Testimonio", tendencia: "Tendencia", fecha: "Fecha clave" };
$("#calendar-form").onsubmit = async e => {
  e.preventDefault();
  const btn = e.target.querySelector("button[type=submit]");
  btn.disabled = true; btn.textContent = "Pensando…";
  const out = $("#calendar-out");
  try {
    const body = Object.fromEntries(new FormData(e.target));
    body.pack = $("input[name=pack]:checked")?.value || state.brand?.sector || "general";
    body.weeks = +body.weeks; body.per_week = +body.per_week;
    const { items } = await api("/api/calendario", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    state.calendar = items;
    const fmt = d => { const [y, m, dd] = d.split("-"); return `${dd}/${m}`; };
    out.innerHTML = `<table class="calendar"><thead><tr><th>Día</th><th>Reel</th><th>Tipo</th><th></th></tr></thead><tbody>
      ${items.map((it, i) => `<tr><td><b>${fmt(it.date)}</b></td><td><b>${esc(it.hook)}</b><br><small>${esc(it.why)}</small><br><small>🎥 ${esc(it.record)}</small></td><td><span class="kind kind-${esc(it.kind)}">${esc(KIND_NAMES[it.kind] || it.kind)}</span></td><td><button class="ghost small use-idea" data-hook="${esc(it.hook)}">Grabar →</button></td></tr>`).join("")}
      </tbody></table>
      <button class="ghost" type="button" id="calendar-ics">Descargar para el calendario (.ics)</button>`;
    $("#calendar-ics").onclick = () => {
      const esc2 = t => String(t || "").replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/,/g, "\\,").replace(/;/g, "\\;");
      const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Iman//Calendario de contenido//ES"];
      items.forEach((it, i) => {
        const d = it.date.replace(/-/g, "");
        lines.push("BEGIN:VEVENT", `UID:iman-${d}-${i}@imanreels`, `DTSTART;VALUE=DATE:${d}`, `SUMMARY:${esc2("Reel: " + it.hook)}`,
          `DESCRIPTION:${esc2((KIND_NAMES[it.kind] || it.kind) + ". " + it.why + " Grabar: " + it.record)}`, "END:VEVENT");
      });
      lines.push("END:VCALENDAR");
      const blob = new Blob([lines.join("\r\n")], { type: "text/calendar" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob); a.download = "calendario-iman.ics"; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    };
  } catch (err) {
    out.innerHTML = `<p class="error">${esc(err.message)}</p>`;
  } finally { btn.disabled = false; btn.textContent = "Hazme el calendario"; }
};

// ---------- 1. subir ----------
const drop = $("#drop");
state.broll = [];
const MODES = {
  camara: { title: "Arrastra tu vídeo aquí", hint: "o pulsa para elegirlo · MP4, MOV · puedes elegir varias tomas y Imán las une con el mismo color", accept: "video/*",
    broll: "＋ Vídeos o fotos de apoyo", brollHint: "Opcional. Imán los pone a pantalla completa en el momento justo, con tu cara en un círculo." },
  voz: { title: "Arrastra tu audio aquí", hint: "una nota de voz o un vídeo del que solo quieres la voz · M4A, MP3, WAV, MP4", accept: "audio/*,video/*",
    broll: "＋ Fotos o vídeos para acompañar (opcional)", brollHint: "Sin ellos, tu voz va sobre un fondo con tus colores y subtítulos grandes." },
  vozclips: { title: "Arrastra tu voz aquí", hint: "una nota de voz o un vídeo del que solo quieres la voz", accept: "audio/*,video/*",
    broll: "＋ Tus vídeos y fotos", brollHint: "Imán va cambiando de plano al ritmo de lo que dices." },
  largo: { title: "Arrastra tu vídeo largo aquí", hint: "un directo, una clase o un podcast · Imán saca los mejores momentos", accept: "video/*" },
};
const mode = () => $("input[name=mode]:checked").value;
function canGo() {
  $("#to-edit").disabled = $("#go-quick").disabled = !state.file || (mode() === "vozclips" && !state.broll.length);
}
function setMode() {
  const m = MODES[mode()];
  $("#drop-title").textContent = m.title; $("#drop-hint").textContent = m.hint;
  $("#file").accept = m.accept;
  $("#file").multiple = mode() === "camara";
  $("#broll-box").hidden = !m.broll;
  $("#bg-box").hidden = mode() !== "camara";
  if (m.broll) { $("#broll-title").textContent = m.broll; $("#broll-hint").textContent = m.brollHint; }
  canGo();
}
$("#modes").onchange = setMode;
// Tres fotogramas de tu vídeo (al 20, 50 y 80 %) para enseñarte los estilos sobre ti, no sobre un dibujo.
async function grabFrames(file) {
  const v = document.createElement("video");
  v.muted = true; v.playsInline = true; v.preload = "auto";
  v.src = URL.createObjectURL(file);
  try {
    await new Promise((ok, ko) => { v.onloadeddata = ok; v.onerror = ko; setTimeout(ko, 8000); });
    const c = document.createElement("canvas");
    c.width = 180; c.height = 260;
    const g = c.getContext("2d");
    const out = [];
    for (const at of [0.2, 0.5, 0.8]) {
      await new Promise(ok => { v.onseeked = ok; v.currentTime = Math.max(0.1, v.duration * at); setTimeout(ok, 3000); });
      const k = Math.max(c.width / v.videoWidth, c.height / v.videoHeight);
      const w = v.videoWidth * k, h = v.videoHeight * k;
      g.drawImage(v, (c.width - w) / 2, (c.height - h) / 2 * 0.4, w, h);  // un poco hacia arriba: se ve la cara
      out.push(c.toDataURL("image/jpeg", 0.72));
    }
    return out;
  } catch { return []; }
  finally { URL.revokeObjectURL(v.src); }
}
// En «cámara» se pueden elegir varias tomas: Imán las une en orden e iguala el color a la primera.
function pick(files) {
  const ok = f => f && (f.type.startsWith("video") || (mode().startsWith("voz") && f.type.startsWith("audio")));
  const list = [...(files || [])].filter(ok);
  const file = list[0];
  if (!file) return;
  state.file = file;
  state.takes = mode() === "camara" ? list.slice(1, 10).filter(f => f.type.startsWith("video")) : [];
  state.frames = [];
  if (file.type.startsWith("video") && mode() === "camara") {
    grabFrames(file).then(fr => { if (state.file === file) { state.frames = fr; if (state.styleList) renderStyles(state.styleList); } });
  }
  const v = $("#preview");
  $(".drop-inner").hidden = true;
  if (file.type.startsWith("audio")) {
    v.hidden = true;
    $("#audio-picked").hidden = false; $("#audio-picked").textContent = `🎙 ${file.name}`;
  } else {
    $("#audio-picked").hidden = true;
    v.src = URL.createObjectURL(file); v.hidden = false; v.play();
  }
  $("#picked-name").textContent = state.takes.length
    ? `${file.name} + ${state.takes.length} toma${state.takes.length > 1 ? "s" : ""} más (se unen en orden con el mismo color)`
    : file.name;
  $("#picked-row").hidden = false;
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
$("#file").onchange = e => pick(e.target.files);
drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = e => { e.preventDefault(); drop.classList.remove("over"); pick(e.dataTransfer.files); };
$("#to-edit").onclick = () => go("edit");
$("#go-quick").onclick = () => $("#go").click();  // todo automático: con lo que Imán elige por defecto
// Empezar de cero: olvida el vídeo elegido y el reel abierto (el anterior sigue en «Mis reels»).
function clearUpload() {
  state.file = null; state.takes = []; state.frames = []; state.broll = []; renderBroll();
  const v = $("#preview"); v.pause(); v.removeAttribute("src"); v.hidden = true;
  $("#audio-picked").hidden = true; $(".drop-inner").hidden = false; $("#picked-row").hidden = true;
  $("#file").value = ""; $("#music-file").value = "";
  canGo();
}
function newReel() {
  clearTimeout(state.poll);
  clearUpload();
  state.job = null; state.comment = null; state.longId = null; state.post = null;
  $("#post-tabs").innerHTML = ""; $("#post-box").hidden = true;
  for (const id of ["#working", "#result-tools", "#early", "#clips", "#download", "#download-wa-mp4"]) if ($(id)) $(id).hidden = true;
  if ($("#comment-bubble")) $("#comment-bubble").checked = false;
  for (const id of ["#hook-title", "#hook-template", "#instructions", "#chat-input"]) if ($(id)) $(id).value = "";
  $("#gancho").value = "auto"; ganchoTip();
  $("#out").pause?.(); $("#out").removeAttribute("src");
  renderInstrIdeas();
  go("upload");
}
$("#new-reel").onclick = newReel;
$("#change-file").onclick = e => { e.preventDefault(); clearUpload(); $("#file").click(); };

// ---------- 2. editar ----------
$("#go").onclick = async () => {
  if (!state.file) return go("upload");
  if (state.uploading) return;  // un doble clic no debe crear dos reels
  state.uploading = true;
  $("#go").disabled = $("#go-quick").disabled = true;
  const fd = new FormData();
  fd.append("video", state.file);
  if (mode() === "camara") for (const t of state.takes || []) fd.append("video", t);
  fd.append("rhythm", $("input[name=rhythm]:checked")?.value ?? "rapido");
  fd.append("style", $("input[name=style]:checked")?.value ?? "auto");
  fd.append("fit", $("input[name=fit]:checked")?.value ?? "recortar");
  fd.append("size", $("input[name=size]:checked")?.value ?? "1080");
  fd.append("hook", $("#hook").checked);
  fd.append("voice", $("#voice").checked);
  fd.append("ruido", $("#ruido").checked);
  fd.append("pack", $("input[name=pack]:checked")?.value === "general" ? "" : $("input[name=pack]:checked")?.value || "");
  fd.append("use_brand", $("#use-brand").checked && !$("#use-brand-row").hidden);
  fd.append("hook_title", $("#hook-title").value);
  fd.append("hook_template", $("#hook-template").value);
  fd.append("gancho", $("#gancho").value || "auto");
  fd.append("instructions", $("#instructions").value);
  fd.append("remember", $("#remember").checked);
  fd.append("mode", mode() === "vozclips" ? "voz" : mode());
  const bg = mode() === "camara" ? $("input[name=background]:checked").value : "";
  fd.append("background", bg === "foto" && !$("#bg-photo").files[0] ? "" : bg);
  if (bg === "foto" && $("#bg-photo").files[0]) fd.append("background_photo", $("#bg-photo").files[0]);
  fd.append("sfx", $("#sfx").checked);
  fd.append("punch", $("#punch").checked);
  fd.append("barra", $("#barra").checked);
  fd.append("transiciones", $("#transiciones").checked);
  fd.append("look", $("#look").value);
  fd.append("letra", $("input[name=letra]:checked")?.value || "normal");
  fd.append("red", $("input[name=red]:checked")?.value || "instagram");
  if (state.comment?.text) { fd.append("comentario", state.comment.text); fd.append("comentario_de", state.comment.author || ""); }
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
  } finally { state.uploading = false; $("#go").disabled = false; canGo(); }
};

// ---------- 3. resultado ----------
function showWorking(step, pct) {
  $("#working").hidden = false; $("#out").hidden = true;
  const p = Math.max(0, Math.min(100, Math.round((pct || 0) * 100)));
  $("#working").innerHTML = `<div class="spinner"></div><strong>${esc(step)}</strong><div class="bar"><i style="width:${p}%"></i></div><span class="hint">${p} % · Puedes hacer otra cosa mientras tanto.</span>`;
}
function showError(msg, needsLicense = false) {
  $("#working").hidden = false; $("#out").hidden = true;
  $("#working").innerHTML = needsLicense
    ? `<strong>Tu prueba gratis ha terminado</strong><span class="hint">${esc(msg)}</span><button class="primary" id="hint-settings">Activar licencia</button>`
    : `<strong class="error">No he podido editarlo</strong><span class="hint">${esc(msg)}</span>`;
}
function poll(retries = 0) {
  clearTimeout(state.poll);
  const id = state.job?.id;
  if (!id) return;
  state.poll = setTimeout(async () => {
    let j;
    try { j = await api(`/api/jobs/${id}`); }
    catch (err) {
      if (state.job?.id !== id) return;
      if (retries < 8 && err.status !== 404) { showWorking("Esperando a Imán… (reconectando)", state.job.progress || 0); return poll(retries + 1); }
      return showError(err.status === 404 ? "Imán se ha reiniciado y este reel se ha perdido. Vuelve a subirlo." : "He perdido la conexión con Imán. Comprueba que sigue abierto y vuelve a intentarlo.");
    }
    if (state.job?.id !== id) return;  // ya has empezado otro reel: este sondeo sobra
    state.job = j;
    if (j.status === "working") { showWorking(j.step, j.progress); earlyReview(j); return poll(); }
    $("#early").hidden = true;
    if (j.status === "done" && await applyEarly(j)) return;
    if (j.status === "error") return showError(j.error);
    if (j.result?.clips) return showClips(j);
    showResult(j); if (j.options?.watermark) loadSettings();
  }, 900);
}
// Revisar las frases mientras el director trabaja: en cuanto Imán te ha escuchado salen tus frases;
// lo que quites o recuperes se guarda y se aplica solo al terminar la primera edición.
async function earlyReview(j) {
  if (j.result || j.mode !== "camara") return;
  const e = state.early;
  if (e && e.job === j.id && (e.list.length || e.busy)) return;
  if (!e || e.job !== j.id) state.early = { job: j.id, list: [], changes: {}, busy: false };
  state.early.busy = true;
  try {
    const r = await api(`/api/jobs/${j.id}/review`);
    if (state.early.job !== j.id || !r.phrases.length) return;
    state.early.list = r.phrases;
    $("#result-tools").hidden = true;
    $("#early").hidden = false;
    $("#early-audio").src = `/api/jobs/${j.id}/original`;
    renderEarly();
  } catch { /* aún no */ } finally { state.early.busy = false; }
}
function renderEarly() {
  const { list, changes } = state.early;
  const keep = p => (p.from + "-" + p.to) in changes ? changes[p.from + "-" + p.to] : p.state !== "fuera";
  const kept = list.filter(keep);
  const secs = kept.reduce((a, p) => a + (p.end - p.start), 0);
  const rhythm = $("input[name=rhythm]:checked")?.closest("label")?.querySelector("span")?.firstChild?.textContent?.trim() || "";
  $("#early-stats").innerHTML = `<b>${kept.length}</b> de ${list.length} frases · <b>${secs.toFixed(1).replace(".", ",")} s</b>${rhythm ? ` · ritmo ${esc(rhythm.toLowerCase())}` : ""}`;
  $("#early-phrases").innerHTML = list.map(p => {
    const k = keep(p);
    return `<div class="phrase ${k ? "dentro" : "fuera"}" data-key="${p.from}-${p.to}">
      <button type="button" class="play" data-play="${p.start}-${p.end}" title="Escuchar">▶</button>
      <span class="grow"><span class="txt">${esc(p.text)}</span><small>${(p.end - p.start).toFixed(1).replace(".", ",")} s${p.reason ? ` · ${esc(p.reason)}` : ""}</small></span>
      <button type="button" class="link" data-toggle="1">${k ? "Quitar" : "Recuperar"}</button></div>`;
  }).join("");
}
$("#early-phrases").onclick = e => {
  const play = e.target.closest("[data-play]"), tog = e.target.closest("[data-toggle]");
  if (play) {
    const [a, b] = play.dataset.play.split("-").map(Number), au = $("#early-audio");
    au.currentTime = a; au.play().catch(() => {});
    clearTimeout(state.earlyStop); state.earlyStop = setTimeout(() => au.pause(), (b - a) * 1000 + 150);
  } else if (tog) {
    const key = tog.closest(".phrase").dataset.key, p = state.early.list.find(x => `${x.from}-${x.to}` === key);
    const now = key in state.early.changes ? state.early.changes[key] : p.state !== "fuera";
    state.early.changes[key] = !now;
    renderEarly();
  }
};
async function applyEarly(j) {
  const e = state.early;
  if (!e || e.job !== j.id || e.applied) return false;
  const phrases = Object.entries(e.changes).map(([k, keep]) => { const [from, to] = k.split("-").map(Number); return { from, to, keep }; });
  e.applied = true;
  $("#early-audio").pause();
  if (!phrases.length) return false;
  showWorking("Aplicando lo que has revisado", 0.02);
  try { state.job = await postJSON(`/api/jobs/${j.id}/plan`, { phrases }); poll(); return true; }
  catch { return false; }
}
function fmt(s) { return `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`; }
function renderChat(j) {
  $("#chat").innerHTML = (j.chat || []).map(m => `<div class="msg ${m.role === "user" ? "user" : "iman"}">${esc(m.text)}</div>`).join("");
  $("#chat").scrollTop = 1e6;
}
function madeIn(j) {
  if (!j.finished || !j.created) return "";
  const secs = Math.max(1, Math.round(j.finished - j.created));
  const txt = secs >= 60 ? `${Math.floor(secs / 60)} min ${secs % 60} s` : `${secs} s`;
  return `<div><b>${txt}</b><span>montado en</span></div>`;
}

function renderFixes(fixes) {
  const box = $("#fixes-box");
  box.hidden = !fixes.length;
  box.innerHTML = fixes.length ? `<details class="card fixes"><summary>✓ Revisado y arreglado solo (${fixes.length})</summary><ul>${fixes.map(f => `<li>${esc(f)}</li>`).join("")}</ul></details>` : "";
}

// Dictar el cambio al chat: reconocimiento de voz del navegador (Chrome y Edge lo traen; si no, el botón no sale).
(() => {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition, mic = $("#chat-mic");
  if (!SR || !mic) return;
  mic.hidden = false;
  let rec = null;
  mic.onclick = () => {
    if (rec) { rec.stop(); return; }
    rec = new SR();
    rec.lang = "es-ES"; rec.interimResults = true; rec.continuous = false;
    const input = $("#chat-input"), before = input.value.trim();
    mic.classList.add("on"); mic.textContent = "⏹";
    rec.onresult = ev => {
      const said = Array.from(ev.results).map(r => r[0].transcript).join(" ").trim();
      input.value = (before ? before + " " : "") + said;
    };
    rec.onerror = () => { mic.title = "No he podido escucharte. Revisa el permiso del micrófono."; };
    rec.onend = () => { rec = null; mic.classList.remove("on"); mic.textContent = "🎙"; input.focus(); };
    try { rec.start(); } catch { rec = null; }
  };
})();

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
const FX_NAMES = { congelado: "Congelado de arranque", moviles: "Tus clips en móviles", mosaico: "Mosaico de reels detrás de ti", lista: "Lista", grafico: "Gráfico de barras", texto3d: "Texto 3D", etiqueta: "Etiqueta que te sigue", tarjetas: "Tarjetas con iconos", particulas: "Título con partículas", bloques: "Bloques que se resaltan", pexels: "Plano de Pexels", lluvia: "Lluvia de confeti o billetes", capitulo: "Pantalla de capítulo", palabra: "Palabra gigante", titular: "Titular", cifra: "Cifra", frase: "Frase", tecleo: "Texto que se escribe",
  color: "Golpe de color", comentario: "Comentario", contador: "Contador", portada: "Portada de revista", cta: "Llamada a la acción",
  dato: "Dato", bruto: "Toma en bruto", fantasma: "Eco", pagina: "Página de revista", detras: "Texto detrás de ti",
  fondo: "Fondo de color", desenfoque: "Fondo desenfocado", ubicacion: "Ubicación", objeto: "Objeto", viaje: "Itinerario del viaje", oferta: "Oferta", ruta: "Ruta",
  testimonio: "Testimonio", plazas: "Plazas", precio: "Precio", apoyo: "Vídeo de apoyo",
  notificaciones: "Notificaciones", buscador: "Buscador", chat: "Chat de mensajes", captura: "Captura", collage: "Collage", foco: "Foco", anillo: "Anillo de texto",
  sube: "Sube con tu dedo", choque: "El choque", aparece: "Aparece donde señalas",
  bocadillo: "Bocadillo con cifra", hueca: "Palabra hueca", marco: "Marco editorial", progreso: "Barra de progreso", paso: "Paso del tutorial" };
function renderEffects(j) {
  const list = (j.result.plan || {}).effects || [];
  $("#fx-box").hidden = !list.length;
  $("#fx-apply").hidden = true;
  $("#fx-list").innerHTML = list.map((fx, i) => {
    const name = fx.type === "lista" && fx.look === "itinerario" ? "Itinerario" : FX_NAMES[fx.type] || fx.type;
    const detail = fx.type === "lista" ? (fx.items || []).map(it => it.text).join(" · ") : [fx.text, fx.subtitle].filter(x => x && x !== "-").join(" · ");
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
const PLATFORM_NAMES = { instagram: "Instagram", tiktok: "TikTok", youtube: "YouTube", facebook: "Facebook", whatsapp: "WhatsApp",
  anuncio_meta: "Anuncio Meta", anuncio_tiktok: "Anuncio TikTok" };
const STAGES = { atraer: "atraer gente nueva", confiar: "que confíen en ti", vender: "vender" };
function postText(p) {
  const tags = (p.hashtags || []).map(h => "#" + h).join(" ");
  return [p.title, p.text, tags].filter(Boolean).join("\n\n");
}
function showPost(p, which) {
  const keys = Object.keys(p.platforms || {});
  if (!keys.length) { $("#post-tabs").innerHTML = ""; state.post = null; state.postWhich = "instagram"; setShare("instagram"); $("#post-text").value = postText({ text: p.caption, hashtags: p.hashtags }); return; }
  which = keys.includes(which) ? which : keys[0];
  state.post = p;
  $("#post-tabs").innerHTML = keys.map(k => `<button type="button" role="tab" aria-selected="${k === which}" data-post="${k}" class="${k === which ? "on" : ""}">${PLATFORM_NAMES[k] || k}</button>`).join("");
  $("#post-text").value = postText(p.platforms[which]);
  state.postWhich = which;
  setShare(which);
  $("#post-funnel").textContent = p.stage ? `Embudo: este reel sirve para ${STAGES[p.stage] || p.stage}. ${p.funnel || ""}` : "";
}
$("#guide-btn").onclick = async () => {
  const btn = $("#guide-btn"), msg = $("#guide-msg");
  btn.disabled = true; btn.textContent = "Preparando la guía…";
  try {
    const g = await api(`/api/jobs/${state.job.id}/guia`, { method: "POST" });
    msg.innerHTML = `«${esc(g.title)}» lista. <a href="${g.url}" download>Descargar la guía (PDF)</a>. ` +
      "Regálala a quien te escriba una palabra («GUÍA») por privado o por WhatsApp: así consigues su contacto y le das un motivo para pedirte la propuesta." +
      (g.ai ? "" : " Sin IA, la guía lleva tus frases del vídeo.");
    msg.hidden = false;
  } catch (err) { msg.textContent = err.message; msg.hidden = false; }
  finally { btn.disabled = false; btn.textContent = "📘 Guía PDF para captar contactos"; }
};
async function loadPost(again = false) {
  const btn = $("#post-btn");
  btn.disabled = true; btn.textContent = "Escribiendo…";
  try {
    showPost(await api(`/api/jobs/${state.job.id}/post${again ? "?nuevo=true" : ""}`, { method: "POST" }));
    $("#post-box").hidden = false;
  } catch (err) { $("#post-text").value = err.message; $("#post-box").hidden = false; }
  finally { btn.disabled = false; btn.textContent = "✦ Textos para cada red y anuncios"; }
}
$("#post-btn").onclick = () => loadPost();
$("#post-again").onclick = () => loadPost(true);
$("#post-tabs").onclick = e => { const b = e.target.closest("[data-post]"); if (b) showPost(state.post, b.dataset.post); };
$("#post-copy").onclick = async () => {
  await copyText($("#post-text").value, $("#post-text"));
  $("#post-copy").textContent = "Copiado ✓";
  setTimeout(() => $("#post-copy").textContent = "Copiar texto", 1500);
};
// Portadas tipo YouTube: 3 variantes, cada una en vertical y en horizontal.
$("#covers-btn").onclick = async () => {
  if (!state.job) return;
  const btn = $("#covers-btn");
  btn.disabled = true; btn.textContent = "Recortándote y pintando las portadas…";
  try {
    const r = await api(`/api/jobs/${state.job.id}/portadas`, { method: "POST" });
    const base = `/api/jobs/${state.job.id}/portadas`, v = `?v=${r.version}`;
    $("#covers").innerHTML = Object.entries(r.variants).map(([k, label]) => `
      <figure><img src="${base}/portada-${k}-vertical.jpg${v}" alt="${esc(label)}">
        <figcaption>${esc(label)}<span>
          <a href="${base}/portada-${k}-vertical.jpg" download="portada-${k}-vertical.jpg">Vertical</a> ·
          <a href="${base}/portada-${k}-horizontal.jpg" download="portada-${k}-youtube.jpg">YouTube</a></span></figcaption></figure>`).join("");
    $("#covers").hidden = false; $("#covers-hint").hidden = false;
    btn.textContent = "↻ Otras portadas";
  } catch (err) { btn.textContent = "✦ Hazme 3 portadas que se pinchen"; alert(err.message); }
  finally { btn.disabled = false; }
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
$("#library").onkeydown = e => { if ((e.key === "Enter" || e.key === " ") && e.target.closest(".reel-card")) { e.preventDefault(); e.target.closest(".reel-card").click(); } };
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
  $("#working").hidden = true; $("#download").hidden = true; $("#download-wa-mp4").hidden = true;
  $("#clips").hidden = false; $("#result-tools").hidden = true;
  const first = j.result.clips[0];
  if (first) { $("#out").src = `/api/jobs/${first.id}/reel.mp4`; $("#out").hidden = false; }
  $("#clips").innerHTML = `<h3>He sacado ${j.result.clips.length} reels de tu vídeo</h3><div class="library">` + j.result.clips.map(c => `
    <div class="reel-card" data-open-clip="${c.id}" role="button" tabindex="0">
      <img src="/api/jobs/${c.id}/reel.jpg" alt="" loading="lazy">
      <div><strong>${esc(c.title || "Sin título")}</strong><span>${fmt(c.duration)}${c.why ? " · " + esc(c.why) : ""}</span></div>
    </div>`).join("") + `</div><p class="hint">Están también en tu biblioteca. Abre uno para cambiarlo, hacer su carrusel o descargarlo.</p>
    <div class="cascade"><h3>Y todo lo demás, de la misma grabación</h3>
      <p class="hint">El vídeo largo sin silencios (para YouTube), el audio para tu podcast, un carrusel de citas con tu marca y la newsletter.</p>
      <button class="primary" id="cascade-btn" type="button">✦ Sácamelo todo</button>
      <p class="hint" id="cascade-status" role="status"></p><div id="cascade-out"></div></div>`;
  state.longId = j.id;
  pollCascade();
  loadLibrary();
}
$("#clips").onclick = async e => {
  const card = e.target.closest("[data-open-clip]");
  if (!card) return;
  state.job = await api(`/api/jobs/${card.dataset.openClip}`);
  showResult(state.job);
};
// Lo que la IA recomienda para este vídeo sale marcado con ✦ en los cambios rápidos.
function markRecommended(j) {
  const plan = j.result?.plan || {};
  const os = j.options?.style;
  const used = !os || os === "auto" ? plan.caption_style : os;
  $$(".quick [data-style]").forEach(b => {
    b.dataset.label = b.dataset.label || b.textContent;
    const rec = b.dataset.style === plan.caption_style;
    b.textContent = b.dataset.label + (rec ? " ✦" : "");
    b.title = rec ? "Recomendado para este vídeo" : "";
    b.classList.toggle("on", b.dataset.style === used);
  });
  for (const [sel, key] of [["#re-music", plan.music], ["#re-look", plan.color]]) {
    $$(`${sel} option`).forEach(o => {
      o.dataset.label = o.dataset.label || o.textContent;
      o.textContent = o.dataset.label + (key && o.value === key ? " ✦ recomendada" : "");
    });
  }
}
// Pestañas para comparar: tu vídeo solo con los cortes, el reel terminado y lo que subiste.
const VIEWS = {
  cut: ["sin-silencios.mp4", "Tu vídeo sin silencios ni frases quitadas, sin efectos: para revisar lo que se queda."],
  reel: ["reel.mp4", ""],
  orig: ["original", "Lo que subiste, tal cual."],
};
function setView(view) {
  if (!state.job) return;
  const [file, hint] = VIEWS[view];
  $$("#view-tabs button").forEach(b => b.classList.toggle("on", b.dataset.view === view));
  $("#view-hint").textContent = hint; $("#view-hint").hidden = !hint;
  const v = $("#out");
  const t = view === "reel" ? v.currentTime : 0;
  v.src = `/api/jobs/${state.job.id}/${file}${state.bust || ""}`;
  if (t) v.currentTime = t;
  $("#phone").classList.toggle("raw", view !== "reel");
}
$("#view-tabs").onclick = e => { const b = e.target.closest("[data-view]"); if (b) setView(b.dataset.view); };
function showResult(j) {
  const om = j.options && j.options.music;
  const used = om === "auto" ? ((j.result.plan || {}).music || "") : om === true ? "mia" : (om || "");
  if (used === "mia" && !$("#re-music option[value=mia]")) $("#re-music").insertAdjacentHTML("beforeend", `<option value="mia">Mi música</option>`);
  $("#re-music").value = used;
  $("#re-letra").value = (j.options && j.options.letra) || "normal";
  const ol = j.options && j.options.look;
  $("#re-look").value = (ol === "auto" || !ol ? (j.result.plan || {}).color : ol) || "natural";
  markRecommended(j);
  $("#clips").hidden = true; $("#result-tools").hidden = false; $("#download").hidden = false; $("#download-wa-mp4").hidden = false;
  if (state.postJob !== j.id) { state.post = null; $("#post-tabs").innerHTML = ""; $("#post-box").hidden = true; $("#guide-msg").hidden = true; }
  state.postJob = j.id;
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
  v.hidden = false; $("#working").hidden = true;
  state.bust = bust;
  $("#view-tabs").hidden = j.mode === "voz" || j.mode === "largo";
  setView("reel");
  $("#download").href = `/api/jobs/${j.id}/reel.mp4`;
  $("#download-wa").href = `/api/jobs/${j.id}/whatsapp.zip`;
  $("#download-wa").hidden = !(j.result && j.result.duration_out > 60);
  $("#download-wa-mp4").href = `/api/jobs/${j.id}/whatsapp.mp4`;
  $("#stats").innerHTML = `
    <div><b>${fmt(r.duration_in)} → ${fmt(r.duration_out)}</b><span>duración</span></div>
    <div><b>${r.cuts}</b><span>cortes</span></div>
    <div><b>${r.removed_words.length}</b><span>palabras quitadas</span></div>${madeIn(j)}`;
  const p = r.plan;
  renderFixes(r.fixes || []);
  $("#hook-box").innerHTML = (r.notices || []).map(n => `<div class="card warn"><p>${esc(n)}</p></div>`).join("")
    + (r.ai_warning ? `<div class="card warn"><p>${esc(r.ai_warning)}</p><p class="hint">El reel está cortado y con subtítulos, pero sin los efectos de la IA.</p></div>` : "")
    + (p.hook_title ? `<div class="card"><h4>${esc(p.hook_title)}</h4><p class="hint">Gancho en pantalla</p></div>` : "")
    + (p.gancho && ganchoOf(p.gancho) ? `<div class="card"><h4>Gancho visual: ${esc(ganchoOf(p.gancho).label)}</h4><p>${esc(p.gancho_why || ganchoOf(p.gancho).description)}</p>${(p.gancho_options || []).filter(ganchoOf).length ? `<p class="hint">Prueba otro arranque (se cambia en segundos):</p><div class="hook-try">${p.gancho_options.filter(ganchoOf).map(k => `<button type="button" class="ghost small" data-gancho-try="${k}" title="${esc(ganchoOf(k).description)}">${esc(ganchoOf(k).label)}</button>`).join("")}</div>` : ""}${ganchoOf(p.gancho).record ? `<p class="hint">🎥 La próxima vez: ${esc(ganchoOf(p.gancho).record)}</p>` : ""}</div>` : "")
    + ((p.hook_options || []).length ? `<div class="card"><p class="hint">Otros ganchos para probar (se cambia en segundos):</p><div class="hook-try">${p.hook_options.map(h => `<button type="button" class="ghost small" data-hook-try="${esc(h)}">${esc(h)}</button>`).join("")}</div></div>` : "")
    + (p.hook_line ? `<div class="card"><p>«${esc(p.hook_line)}»</p><p class="hint">Si quieres regrabar el arranque, prueba con esta frase.</p></div>` : "");
  $("#versions-hooks").value = [p.hook_title, ...(p.hook_options || [])].filter(Boolean).join("\n");
  $("#versions-box").open = j.options?.red === "anuncio";
  pollVersions();
  renderViral(r.viral);
  const checks = r.checks || [];
  $("#check-box").hidden = !checks.length;
  $("#check-list").innerHTML = checks.map(c => `<li class="${c.ok ? "ok" : "warn"}">${c.ok ? "✓" : "!"} ${esc(c.text)}${c.ok || !c.tip ? "" : `<small>${esc(c.tip)}</small>`}</li>`).join("");
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
  b.dataset.rhythm ? { rhythm: b.dataset.rhythm } : b.dataset.background !== undefined ? { background: b.dataset.background }
    : b.dataset.voice ? { voice: b.dataset.voice === "true" }
    : b.dataset.ruido ? { ruido: b.dataset.ruido === "true" } : { style: b.dataset.style }));
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
$("#re-look").onchange = e => reedit({ look: e.target.value });
$("#re-letra").onchange = e => reedit({ letra: e.target.value });
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
const FONT_CSS = { ...Object.fromEntries(["Moderna", "Impacto", "Condensada", "Elegante", "Manuscrita", "Bebas", "Hormozi", "Bloque"].map(n => [n, `"Iman ${n}"`])),
  "Cómic": '"Iman Comic"', "Mía": '"Iman Mia"' };
async function loadMyFont(name) {
  if (!name) return;
  try {
    // La fuente subida se carga en el navegador para que la vista previa la enseñe tal cual.
    const face = new FontFace("Iman Mia", `url(/api/brand/font?t=${Date.now()})`);
    document.fonts.add(await face.load());
  } catch { /* si no carga, la vista previa usa la de por defecto */ }
}
function renderBrand(b) {
  state.brand = b;
  renderToday();
  renderInstrIdeas();
  const f = brandForm;
  for (const k of ["name", "cta", "contact", "handle", "description", "company", "voice", "voice_examples", "avoid"]) f[k].value = b[k] || "";
  f.no_emojis.checked = !!b.no_emojis;
  renderPhrases(b.phrases || []);
  f.primary.value = b.primary || "#FF5547"; f.secondary.value = b.secondary || "#141518";
  f.logo_corner.checked = b.logo_corner; f.end_card.checked = b.end_card;
  f.sector.value = b.sector || "general";
  $("#brand-fonts").innerHTML = ["", ...b.fonts].map(n => `
    <label class="choice"><input type="radio" name="font" value="${n}" ${n === (b.font || "") ? "checked" : ""}>
    <span style="font-family:${FONT_CSS[n] || "inherit"}">${n === "Mía" ? `Mía: ${esc(b.my_font)}` : n || "La del estilo"}</span></label>`).join("");
  $("#font-remove").hidden = !b.my_font;
  loadMyFont(b.my_font);
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
// Paletas de 3 colores armónicos: según el sector y el color que ya tengas (o uno de partida).
const SECTOR_PALETTES = {
  viajes: [["#0E7C86", "#F4A259", "#F7EFE5"], ["#1D3557", "#E63946", "#F1FAEE"], ["#264653", "#E9C46A", "#F4F1EA"]],
  cursos: [["#3A0CA3", "#F72585", "#F8F7FF"], ["#14213D", "#FCA311", "#F5F5F5"], ["#2B2D42", "#EF233C", "#EDF2F4"]],
  productos: [["#111111", "#FF5547", "#FFF4E8"], ["#2D6A4F", "#F4A261", "#FAF7F0"], ["#5F0F40", "#FB8B24", "#FFF8F0"]],
  empresas: [["#0B3954", "#087E8B", "#F5F7FA"], ["#1B263B", "#C9A227", "#F4F4F4"], ["#22223B", "#4A4E69", "#F2E9E4"]],
};
function hsl(h, s, l) {
  l /= 100; const a = s * Math.min(l, 1 - l) / 100;
  const f = n => { const k = (n + h / 30) % 12; const c = l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
    return Math.round(255 * c).toString(16).padStart(2, "0"); };
  return `#${f(0)}${f(8)}${f(4)}`;
}
function hueOf(hex) {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255);
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  if (!d) return 0;
  const h = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return (h * 60 + 360) % 360;
}
function makePalettes() {
  const sector = brandForm.sector.value;
  const base = brandForm.primary.value && brandForm.primary.value !== "#000000" ? brandForm.primary.value : null;
  const h = base ? hueOf(base) : Math.floor(Math.random() * 360);
  const harmonic = [
    [hsl(h, 70, 38), hsl((h + 180) % 360, 80, 58), hsl(h, 30, 95)],  // complementarios
    [hsl(h, 65, 35), hsl((h + 35) % 360, 75, 55), hsl((h + 10) % 360, 25, 94)],  // análogos
    [hsl(h, 70, 40), hsl((h + 120) % 360, 70, 55), hsl((h + 240) % 360, 20, 95)],  // tríada
  ];
  return [...(SECTOR_PALETTES[sector] || []), ...harmonic];
}
$("#palette-btn").onclick = () => {
  const box = $("#palettes");
  box.innerHTML = makePalettes().map(p => `<button type="button" class="palette" data-p="${p.join(",")}" title="Usar estos colores">
    ${p.map(c => `<span style="background:${c}"></span>`).join("")}</button>`).join("")
    + `<p class="hint">Principal, secundario y fondo claro. Pulsa una para usarla; vuelve a pedir para ver más.</p>`;
  box.hidden = false;
};
$("#palettes").onclick = e => {
  const b = e.target.closest(".palette");
  if (!b) return;
  const [p1, p2] = b.dataset.p.split(",");
  brandForm.primary.value = p1; brandForm.secondary.value = p2;
  $$("#palettes .palette").forEach(x => x.classList.toggle("on", x === b));
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
$("#font-file").onchange = async e => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file) return;
  brandError("");
  const fd = new FormData(); fd.append("font", file);
  try { renderBrand(await api("/api/brand/font", { method: "POST", body: fd })); } catch (err) { brandError(err.message); }
};
$("#font-remove").onclick = async () => renderBrand(await api("/api/brand/font", { method: "DELETE" }));
function brandBody() {
  const f = brandForm;
  return { name: f.name.value, description: f.description.value.trim(), company: f.company.value.trim(), phrases: readPhrases(),
    voice: f.voice.value.trim(), voice_examples: f.voice_examples.value.trim(), avoid: f.avoid.value.trim(), no_emojis: f.no_emojis.checked, cta: f.cta.value, contact: f.contact.value, handle: f.handle.value,
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

function startupError(err) {
  go("upload");
  $("#drop-title").textContent = "No puedo hablar con Imán";
  $("#drop-hint").textContent = `Cierra la app y vuelve a abrirla. (${err.message})`;
}
loadOptions().then(() => api("/api/brand").then(renderBrand)).catch(startupError);
loadSettings().catch(() => {});
api("/api/reels").then(r => go(r.reels.length ? "home" : "upload")).catch(startupError);

// Herramientas de foto: quitar fondo, mejorar y reiluminar (en local).
const photoFile = $("#photo-file");
$("#open-photos").onclick = () => $("#photos").showModal();
photoFile.onchange = () => {
  const f = photoFile.files[0];
  if (!f) return;
  const img = $("#photo-before");
  if (state.photoUrl) URL.revokeObjectURL(state.photoUrl);
  state.photoUrl = img.src = URL.createObjectURL(f);
  img.hidden = false;
  $("#photo-empty").hidden = true;
  $("#photo-result").hidden = true;
  $("#photo-status").textContent = "";
};
document.querySelectorAll("[data-tool]").forEach(btn => btn.onclick = async () => {
  const f = photoFile.files[0];
  const status = $("#photo-status");
  if (!f) { status.textContent = "Primero elige una foto."; return; }
  const fd = new FormData();
  fd.append("foto", f);
  fd.append("accion", btn.dataset.tool);
  fd.append("luz", $("#photo-light").value);
  fd.append("lado", $("#photo-side").value);
  document.querySelectorAll("[data-tool]").forEach(b => b.disabled = true);
  status.textContent = "Trabajando en tu foto…";
  try {
    const r = await api("/api/imagen", { method: "POST", body: fd });
    const url = `${r.url}?v=${Date.now()}`;
    $("#photo-after").src = url;
    $("#photo-download").href = r.url;
    $("#photo-download").setAttribute("download", r.name);
    $("#photo-result").hidden = false;
    status.textContent = `Listo (${r.width}×${r.height}).`;
  } catch (err) {
    status.textContent = err.message || "No se ha podido.";
  } finally {
    document.querySelectorAll("[data-tool]").forEach(b => b.disabled = false);
  }
});

// Probar otro gancho: se vuelve a montar con ese título, sin volver a escuchar el vídeo.
document.addEventListener("click", e => {
  const b = e.target.closest("[data-hook-try]");
  if (b) reedit({ hook_title: b.dataset.hookTry });
  const g = e.target.closest("[data-gancho-try]");
  if (g) reedit({ gancho: g.dataset.ganchoTry });
});

// Versiones para anuncios: el mismo reel con otros ganchos y llamadas a la acción.
const linesOf = id => $(id).value.split("\n").map(s => s.trim()).filter(Boolean);
$("#versions-btn").onclick = async () => {
  const status = $("#versions-status");
  try {
    await postJSON(`/api/jobs/${state.job.id}/versiones`, { hooks: linesOf("#versions-hooks"), ctas: linesOf("#versions-ctas") });
    pollVersions();
  } catch (err) { status.textContent = err.message; }
};
async function pollVersions() {
  if (!state.job) return;
  const id = state.job.id;
  const v = await api(`/api/jobs/${id}/versiones`).catch(() => null);
  if (!v || state.job.id !== id) return;
  const status = $("#versions-status");
  $("#versions-btn").disabled = v.status === "working";
  status.textContent = v.status === "working" ? `Montando la versión ${v.done + 1} de ${v.total}…`
    : v.status === "error" ? v.error : v.status === "done" ? `Listas las ${v.total} versiones.` : "";
  $("#versions-list").innerHTML = v.files.map(f => `<a class="ghost small" href="/api/jobs/${id}/versiones/${f.name}" download>${esc(f.name)} · ${esc(f.hook)}${f.cta ? " · " + esc(f.cta) : ""}</a>`).join("")
    + (v.status === "done" ? `<a class="primary small" href="/api/jobs/${id}/versiones/versiones.zip" download>Descargar todas (.zip)</a>` : "");
  clearTimeout(state.versionsTimer);
  if (v.status === "working") state.versionsTimer = setTimeout(() => pollVersions(), 2000);
}

// Método cascada: del vídeo largo, el resto de piezas en un clic.
document.addEventListener("click", async e => {
  if (e.target.id !== "cascade-btn") return;
  try { await api(`/api/jobs/${state.longId}/cascada`, { method: "POST" }); pollCascade(); }
  catch (err) { $("#cascade-status").textContent = err.message; }
});
async function pollCascade() {
  const id = state.longId;
  const c = await api(`/api/jobs/${id}/cascada`).catch(() => null);
  if (!c || state.longId !== id || !$("#cascade-btn")) return;
  $("#cascade-btn").disabled = c.status === "working";
  $("#cascade-status").textContent = c.status === "working" ? `${c.step}… ${Math.round(c.progress * 100)} %`
    : c.status === "error" ? c.error : "";
  if (c.status === "done") {
    const base = `/api/jobs/${id}/cascada`;
    const r = c.result || {};
    $("#cascade-out").innerHTML = `<div class="cascade-links">
      <a class="primary small" href="${base}/cascada.zip" download>Descargar todo (.zip)</a>
      <a class="ghost small" href="${base}/video-largo.mp4" download>Vídeo largo${r.duration ? " · " + fmt(r.duration) : ""}</a>
      <a class="ghost small" href="${base}/podcast.mp3" download>Audio del podcast</a>
      <a class="ghost small" href="${base}/newsletter.txt" target="_blank">Newsletter</a></div>
      ${(r.carousel || []).length ? `<div class="kit-strip">${r.carousel.map(n => `<img src="${base}/citas/${n}" alt="">`).join("")}</div>` : ""}`;
  }
  clearTimeout(state.cascadeTimer);
  if (c.status === "working") state.cascadeTimer = setTimeout(pollCascade, 2000);
}

// Reel desde un comentario: respuesta para el seguidor y un guion que le responde.
$("#comment-form").captura.onchange = e => { $("#comment-file").textContent = e.target.files[0]?.name || ""; };
$("#comment-form").onsubmit = async e => {
  e.preventDefault();
  const f = e.target, btn = f.querySelector("button[type=submit]"), out = $("#comment-out");
  btn.disabled = true; btn.textContent = "Leyendo el comentario…";
  try {
    const fd = new FormData(f);
    if (!f.captura.files[0]) fd.delete("captura");
    const r = await api("/api/comentario", { method: "POST", body: fd });
    state.comment = { text: r.comment, author: r.author };
    out.innerHTML = `
      <div class="card"><p class="hint">Respuesta para el comentario</p><p id="comment-reply">${esc(r.reply)}</p>
        <button class="ghost small" type="button" id="comment-copy">Copiar respuesta</button></div>
      <div class="card"><h4>${esc(r.hook)}</h4><p class="script">${esc(r.script).replace(/\n/g, "<br>")}</p>
        <p class="hint">${esc(r.why)}${r.ai ? "" : " (Sin IA conectada: guion hecho con las frases del comentario.)"}</p>
        <label class="check"><input type="checkbox" id="comment-bubble" checked> Poner su comentario en pantalla al principio</label>
        <button class="primary" type="button" id="comment-use" data-hook="${esc(r.hook)}">Grabar este →</button></div>`;
  } catch (err) {
    out.innerHTML = `<p class="error">${esc(err.message)}</p>`;
  } finally { btn.disabled = false; btn.textContent = "Hazme la respuesta y el reel"; }
};
document.addEventListener("click", async e => {
  if (e.target.id === "comment-copy") {
    await copyText($("#comment-reply").textContent);
    e.target.textContent = "Copiada ✓";
  }
  if (e.target.id === "comment-use") {
    showHook(e.target.dataset.hook);
    if (!$("#comment-bubble").checked) state.comment = null;
    go("upload");
  }
});

// Frases de marca: eslogan, promesa, llamada a la acción, actitud…
const PHRASE_KINDS = { eslogan: "Eslogan", promesa: "Promesa", cta: "Llamada a la acción", actitud: "Actitud", otra: "Otra" };
function phraseRow(p = {}) {
  return `<div class="phrase-row">
    <select aria-label="Tipo">${Object.entries(PHRASE_KINDS).map(([k, v]) => `<option value="${k}" ${k === (p.kind || "eslogan") ? "selected" : ""}>${v}</option>`).join("")}</select>
    <input class="ph-text" maxlength="160" placeholder="La frase" value="${esc(p.text || "")}">
    <input class="ph-where" maxlength="200" placeholder="Dónde va (opcional)" value="${esc(p.where || "")}">
    <button type="button" class="link ph-del" aria-label="Quitar">✕</button></div>`;
}
function showHook(text) { $("#hook-title").value = text; $("#fine-hook").open = !!text; }
function renderPhrases(list) { $("#brand-phrases").innerHTML = list.map(phraseRow).join(""); }
function readPhrases() {
  return [...document.querySelectorAll("#brand-phrases .phrase-row")].map(r => ({
    kind: r.querySelector("select").value, text: r.querySelector(".ph-text").value.trim(), where: r.querySelector(".ph-where").value.trim(),
  })).filter(p => p.text);
}
$("#phrase-add").onclick = () => $("#brand-phrases").insertAdjacentHTML("beforeend", phraseRow({ kind: readPhrases().length ? "otra" : "eslogan" }));
$("#brand-phrases").onclick = e => { if (e.target.closest(".ph-del")) e.target.closest(".phrase-row").remove(); };

// Qué hace cada opción: se ve al pasar el ratón (o con el teclado) y en el desplegable de color.
const LOOK_HELP = {
  auto: "Imán mira tu vídeo y elige el color que mejor le va.",
  natural: "Corrige la luz y el blanco sin cambiar el estilo: como lo viste, pero mejor.",
  calido: "Tonos dorados y piel bonita: atardeceres, playas, comida.",
  teal: "Cielos y mar azules con la piel cálida: el look de los vídeos de viajes.",
  cine: "Contraste suave y sombras profundas, como una película.",
  grano: "Grano de película de 35 mm con polvo: nostálgico y artesanal.",
  retro: "Televisor antiguo con los colores separados: divertido y llamativo.",
  bn: "Blanco y negro con contraste: serio, elegante o emotivo.",
};
const QUICK_HELP = {
  "rhythm:rapido": "Quita más pausas y repeticiones: el reel dura menos y engancha más.",
  "rhythm:natural": "Deja respirar tus pausas: suena más tranquilo y cercano.",
  "style:impacto": "Subtítulos grandes con la palabra que dices resaltada.",
  "style:editorial": "Letra fina de revista: elegante, para marcas premium.",
  "style:palabra": "Una palabra cada vez, en el centro: máxima atención.",
  "style:neon": "Letras que brillan como un letrero de neón.",
  "style:karaoke": "La frase entera y se va coloreando lo que dices.",
  "style:caja": "Texto sobre una caja de color: se lee en cualquier fondo.",
  "style:gigante": "Palabras enormes que ocupan la pantalla.",
  "style:mezcla": "Mezcla letra normal y manuscrita en las palabras clave.",
  "style:elegante": "Serif fina y discreta: lujo y viajes premium.",
  "style:marcador": "Como si subrayaras con rotulador las palabras clave.",
  "style:hormozi": "Mayúsculas gordas con palabras clave de color: el estilo que más retiene.",
  "style:bebas": "Letra alta y estrecha, muy de YouTube.",
  "style:comic": "Letra de cómic con borde: divertido y desenfadado.",
  "style:bloque": "Bloques de color detrás de cada línea.",
  "style:cursiva": "Palabras sueltas en blanco y las clave en cursiva dorada: estilo de vida, belleza, hogar.",
  "background:desenfoque": "Te recorta y desenfoca lo de detrás: tú nítido delante.",
  "background:color": "Fondo oscuro con una luz de tu color de marca.",
  "background:marca_degradado": "Fondo con un degradado de tus colores.",
  "background:marca_bokeh": "Luces desenfocadas de tus colores detrás de ti.",
  "background:marca_logo": "Tu logo repetido y suave detrás de ti.",
  "background:": "Vuelve a tu fondo tal cual se grabó.",
  "voice:false": "Tu voz sin tocar (si la limpieza la deja rara).",
  "voice:true": "Menos ruido y volumen estable en toda la toma.",
  "ruido:true": "Quita tráfico, viento o gente de fondo. Úsalo solo si se oye mucho.",
  "ruido:false": "Deja el ambiente como estaba.",
};
function quickKey(b) {
  for (const k of ["rhythm", "style", "background", "voice", "ruido"]) if (k in b.dataset) return `${k}:${b.dataset[k]}`;
  return "";
}
(function wireHelp() {
  const box = $("#quick-box"), help = $("#quick-help"), base = help.textContent;
  box.querySelectorAll("button").forEach(b => { const t = QUICK_HELP[quickKey(b)]; if (t) b.title = t; });
  const show = e => { const b = e.target.closest("button"); help.textContent = (b && QUICK_HELP[quickKey(b)]) || base; };
  box.addEventListener("mouseover", show); box.addEventListener("focusin", show);
  box.addEventListener("mouseleave", () => help.textContent = base);
  const look = $("#look"), lookHelp = $("#look-help");
  const setLook = () => lookHelp.textContent = LOOK_HELP[look.value] || "";
  look.addEventListener("change", setLook); setLook();
  const reLook = $("#re-look");
  if (reLook) reLook.title = "Cambia el color de todo el reel. " + (LOOK_HELP[reLook.value] || "");
})();

// Publicar: por ahora, copiar el texto y abrir la red con el vídeo a mano (subirlo directo llegará con las cuentas conectadas).
const SHARE = {
  instagram: { url: "https://www.instagram.com/", help: "En Instagram pulsa ＋ › Reel, elige el vídeo y pega el texto. Desde el móvil, pásatelo por WhatsApp o AirDrop." },
  tiktok: { url: "https://www.tiktok.com/upload", help: "Se abre la página de subir de TikTok: arrastra el vídeo y pega el texto." },
  youtube: { url: "https://studio.youtube.com/", help: "En YouTube Studio pulsa Crear › Subir vídeos. Si dura menos de 3 minutos y es vertical, sale como Short. Pega el título y la descripción." },
  facebook: { url: "https://www.facebook.com/reels/create", help: "En Facebook, Crear reel: sube el vídeo y pega el texto." },
  anuncio_meta: { url: "https://adsmanager.facebook.com/", help: "En el Administrador de anuncios de Meta, crea una campaña de mensajes o de clientes potenciales, sube el vídeo y pega el texto principal y el titular. Así el anuncio busca reservas, no likes." },
  anuncio_tiktok: { url: "https://ads.tiktok.com/", help: "En TikTok Ads Manager, crea un anuncio con el vídeo y pega el texto. Elige el objetivo de mensajes o de clientes potenciales." },
  whatsapp: { url: "https://web.whatsapp.com/", help: "En WhatsApp Web, adjunta el vídeo ligero («Para WhatsApp») en el chat o en tu estado y pega el texto." },
};
function setShare(which) {
  const s = SHARE[which] || SHARE.instagram;
  $("#share-go").textContent = `Copiar texto y abrir ${PLATFORM_NAMES[which] || "la red"}`;
  $("#share-help").textContent = s.help;
}
$("#share-go").onclick = async () => {
  const which = state.postWhich || "instagram";
  await copyText($("#post-text").value, $("#post-text"));
  if (which === "whatsapp") $("#download-wa-mp4").click(); else $("#download").click();
  window.open(SHARE[which].url, "_blank", "noopener");
};
$("#share-folder").onclick = () => api(`/api/jobs/${state.job.id}/mostrar`, { method: "POST" }).catch(err => $("#share-help").textContent = err.message);
