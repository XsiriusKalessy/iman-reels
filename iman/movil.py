"""Enviar desde el móvil: una página que abres en el móvil (escaneando un QR) y que habla con Imán en tu ordenador.

Sin app que instalar ni tiendas: el ordenador sirve una página pequeña en la wifi de casa, solo mientras tú lo
activas, y solo a quien tiene el enlace con su clave (el QR). Desde el móvil eliges o grabas el vídeo, dices qué
quieres y le das a «Enviar»: Imán lo monta en el ordenador y el reel terminado vuelve al móvil para guardarlo o
compartirlo. Ese servidor de la wifi es otro distinto al de la app: no da acceso a nada más de Imán.
"""

from __future__ import annotations

import inspect
import io
import secrets
import socket
import threading
import time

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

PORT = 8770
_state: dict = {"server": None, "thread": None, "token": "", "port": 0, "jobs": [], "started": 0.0}
_lock = threading.Lock()
MAX_JOBS = 50

app = FastAPI(title="Imán (móvil)", docs_url=None, redoc_url=None, openapi_url=None)


def lan_ip() -> str:
    """La IP de este ordenador en la wifi (sin mandar nada: un socket UDP solo elige la salida)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except OSError:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def _free_port(start: int) -> int:
    for p in range(start, start + 30):
        with socket.socket() as s:
            try:
                s.bind(("0.0.0.0", p))
                return p
            except OSError:
                continue
    raise RuntimeError("No encuentro un puerto libre para el móvil")


def url() -> str:
    return f"http://{lan_ip()}:{_state['port']}/m/{_state['token']}" if _state["token"] else ""


def qr_svg(text: str) -> str:
    import segno

    buf = io.BytesIO()
    segno.make(text, error="m").save(buf, kind="svg", scale=6, border=2, dark="#111215", light="#FFFFFF",
                                     xmldecl=False, svgns=True)
    return buf.getvalue().decode("utf-8")


def status() -> dict:
    on = _state["server"] is not None
    return {"on": on, "url": url() if on else "", "qr": qr_svg(url()) if on else "", "jobs": list(_state["jobs"])}


def start() -> dict:
    """Enciende la página del móvil (si ya estaba encendida, la deja como está)."""
    import uvicorn

    with _lock:
        if _state["server"] is None:
            port = _free_port(PORT)
            server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning"))
            t = threading.Thread(target=server.run, daemon=True, name="iman-movil")
            _state.update(server=server, thread=t, token=secrets.token_urlsafe(12), port=port, started=time.time())
            t.start()
            for _ in range(50):
                if server.started:
                    break
                time.sleep(0.05)
    return status()


def stop() -> dict:
    with _lock:
        server = _state["server"]
        if server is not None:
            server.should_exit = True
        _state.update(server=None, thread=None, token="", port=0)
    return status()


def _check(token: str) -> None:
    if not _state["token"] or not secrets.compare_digest(token.encode(), _state["token"].encode()):
        raise HTTPException(404)


def _mine(job_id: str) -> dict:
    from . import server

    if job_id not in _state["jobs"]:
        raise HTTPException(404)
    job = server._job(job_id)
    if job is None:
        raise HTTPException(404)
    return job


@app.get("/m/{token}", response_class=HTMLResponse)
def page(token: str):
    _check(token)
    return HTMLResponse(PAGE.replace("{{TOKEN}}", token), headers={"Cache-Control": "no-store"})


@app.post("/m/{token}/subir")
async def upload(token: str, video: UploadFile = File(...), instructions: str = Form(""),
                 red: str = Form("instagram"), mode: str = Form("camara")):
    """El vídeo del móvil entra como un reel más de Imán (sale también en «Mis reels» del ordenador)."""
    from . import server

    _check(token)
    if len(_state["jobs"]) >= MAX_JOBS:
        raise HTTPException(429, "Ya has mandado muchos vídeos: termina con estos y vuelve a abrir el QR")
    # Se usa el mismo alta de reels que la app, con sus valores de siempre y lo elegido en el móvil.
    kwargs = {}
    for name, p in inspect.signature(server.create_job).parameters.items():
        d = p.default
        kwargs[name] = getattr(d, "default", d)
    kwargs.update(video=[video], instructions=instructions[:2000], red=red if red in ("instagram", "tiktok", "youtube") else "instagram",
                  mode=mode if mode in ("camara", "largo") else "camara", music_file=None, background_photo=None,
                  broll=None)
    job = await server.create_job(**kwargs)
    with _lock:
        _state["jobs"].append(job["id"])
    return {"id": job["id"]}


@app.get("/m/{token}/estado/{job_id}")
def job_status(token: str, job_id: str):
    _check(token)
    job = _mine(job_id)
    out = {"status": job.get("status"), "step": job.get("step", ""), "progress": job.get("progress", 0),
           "error": job.get("error")}
    res = job.get("result") or {}
    if res.get("clips"):  # vídeo largo: varios reels
        with _lock:
            for cl in res["clips"]:
                if cl["id"] not in _state["jobs"]:
                    _state["jobs"].append(cl["id"])
        out["clips"] = [{"id": cl["id"], "title": cl.get("title", "")} for cl in res["clips"]]
    elif res:
        out["title"] = (res.get("plan") or {}).get("hook_title", "")
    return JSONResponse(out, headers={"Cache-Control": "no-store"})


@app.get("/m/{token}/reel/{job_id}.mp4")
def job_video(token: str, job_id: str):
    from . import server

    _check(token)
    job = _mine(job_id)
    p = server._dir(job_id) / "reel.mp4"
    if job.get("status") != "done" or not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="video/mp4", filename=f"reel-{job_id}.mp4")


PAGE = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Imán · desde el móvil</title>
<style>
:root{--bg:#111215;--panel:#1A1B1F;--line:#2A2C31;--text:#F2F2EF;--muted:#A2A5AC;--accent:#FF5547}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;padding:20px 16px 40px}
h1{font-size:26px;margin:0 0 4px}p{color:var(--muted);margin:0 0 16px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:16px;margin:0 0 14px}
label{display:block;font-weight:600;margin:0 0 8px}
input[type=file]{display:none}
.pick{display:flex;gap:10px}.pick label{flex:1;text-align:center;padding:18px 8px;border:1px dashed var(--line);border-radius:14px;cursor:pointer;font-weight:700}
textarea,select{width:100%;background:#0c0d0f;color:var(--text);border:1px solid var(--line);border-radius:12px;padding:10px;font:inherit}
button{width:100%;padding:16px;border:0;border-radius:14px;background:var(--accent);color:#fff;font:700 17px system-ui;cursor:pointer}
button:disabled{opacity:.5}.bar{height:8px;background:#0c0d0f;border-radius:8px;overflow:hidden;margin:10px 0}.bar i{display:block;height:100%;width:0;background:var(--accent);transition:width .3s}
video{width:100%;border-radius:14px;background:#000;margin:8px 0}a.dl{display:block;text-align:center;padding:14px;border:1px solid var(--line);border-radius:14px;color:var(--text);text-decoration:none;font-weight:700;margin:6px 0}
.name{color:var(--muted);font-size:14px;margin-top:8px;word-break:break-all}
</style></head><body>
<h1>Imán ✦</h1><p>Elige o graba tu vídeo y te devuelvo el reel montado. El móvil y el ordenador tienen que estar en la misma wifi, con Imán abierto.</p>
<div class="card" id="form">
  <div class="pick"><label>🎥 Grabar<input id="cam" type="file" accept="video/*" capture="user"></label><label>🖼 Elegir de la galería<input id="gal" type="file" accept="video/*"></label></div>
  <div class="name" id="name"></div>
  <label style="margin-top:14px">¿Algo que deba saber? (opcional)</label>
  <textarea id="ins" rows="3" placeholder="Ej.: pon el precio en grande y termina con «escríbeme INFO»"></textarea>
  <label style="margin-top:14px">¿Para dónde es?</label>
  <select id="red"><option value="instagram">Instagram</option><option value="tiktok">TikTok</option><option value="youtube">YouTube Shorts</option></select>
  <label style="margin-top:14px"><input type="checkbox" id="largo" style="width:auto"> Es un vídeo largo: sácame varios reels</label>
  <button id="go" style="margin-top:16px" disabled>Enviar a Imán</button>
</div>
<div class="card" id="work" hidden><strong id="step">Subiendo…</strong><div class="bar"><i id="bar"></i></div><p id="hint">No cierres esta página.</p></div>
<div id="done"></div>
<script>
const T="{{TOKEN}}",B="/m/"+T,$=s=>document.querySelector(s);let file=null;
for(const id of ["#cam","#gal"])$(id).onchange=e=>{file=e.target.files[0];$("#name").textContent=file?file.name+" · "+(file.size/1048576).toFixed(0)+" MB":"";$("#go").disabled=!file};
const show=(s,p)=>{$("#work").hidden=false;$("#step").textContent=s;$("#bar").style.width=Math.round(p*100)+"%"};
$("#go").onclick=()=>{if(!file)return;$("#go").disabled=true;const fd=new FormData();fd.append("video",file);fd.append("instructions",$("#ins").value);fd.append("red",$("#red").value);fd.append("mode",$("#largo").checked?"largo":"camara");
const x=new XMLHttpRequest();x.open("POST",B+"/subir");x.upload.onprogress=e=>{if(e.lengthComputable)show("Subiendo tu vídeo…",e.loaded/e.total*0.3)};
x.onload=()=>{let d={};try{d=JSON.parse(x.responseText)}catch{}if(x.status!==200){show(d.detail||"No he podido subirlo",0);$("#go").disabled=false;return}$("#form").hidden=true;poll(d.id)};
x.onerror=()=>{show("Se ha cortado la conexión con el ordenador. ¿Sigue Imán abierto y en la misma wifi?",0);$("#go").disabled=false};x.send(fd)};
async function poll(id){let d;try{d=await (await fetch(B+"/estado/"+id)).json()}catch{return setTimeout(()=>poll(id),3000)}
if(d.status==="working"){show(d.step||"Montando tu reel…",0.3+0.7*(d.progress||0));return setTimeout(()=>poll(id),2000)}
if(d.status==="error"){show(d.error||"Algo ha fallado",0);$("#form").hidden=false;$("#go").disabled=false;return}
$("#work").hidden=true;const list=d.clips?d.clips:[{id,title:d.title}];
$("#done").innerHTML=list.map(c=>`<div class="card"><strong>${(c.title||"Tu reel").replace(/[<>&]/g,"")}</strong><video src="${B}/reel/${c.id}.mp4" controls playsinline></video><a class="dl" href="${B}/reel/${c.id}.mp4" download>⬇ Guardar en el móvil</a><a class="dl" href="#" data-share="${c.id}">↗ Compartir</a></div>`).join("")+`<a class="dl" href="">＋ Mandar otro vídeo</a>`;}
document.addEventListener("click",async e=>{const s=e.target.closest("[data-share]");if(!s)return;e.preventDefault();
try{const blob=await (await fetch(B+"/reel/"+s.dataset.share+".mp4")).blob();const f=new File([blob],"reel.mp4",{type:"video/mp4"});
if(navigator.canShare&&navigator.canShare({files:[f]}))await navigator.share({files:[f]});else location.href=B+"/reel/"+s.dataset.share+".mp4"}catch{}});
</script></body></html>"""

