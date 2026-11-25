"""Funciones «Pro» para estar a la altura de la competencia: línea de tiempo, historias, marcas por reel…"""

import json
import shutil
import subprocess
import time

import pytest

from iman import linea, pipeline
from iman.models import EditPlan, Word

from .test_core import TAKE

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="necesita ffmpeg")


@pytest.fixture
def sample(tmp_path):
    p = tmp_path / "toma.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=12",
        "-f", "lavfi", "-i", "sine=frequency=220:duration=12", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(p),
    ], check=True)
    return p


LINE = {"words": [[6, 0.0, 0.3], [7, 0.35, 0.5], [8, 0.55, 0.9], [9, 0.95, 1.1], [10, 1.15, 1.5], [11, 1.6, 1.8],
                  [12, 1.85, 2.2], [16, 2.6, 2.8], [17, 2.85, 3.0], [18, 3.05, 3.5]]}


def test_timeline_moves_resizes_and_writes():
    plan = EditPlan(effects=[{"type": "frase", "word": 7, "text": "Hola", "until_word": None},
                             {"type": "lista", "word": 8, "items": [{"text": "a", "at_word": 8}, {"text": "b", "at_word": 10}],
                              "until_word": 12}])
    words = list(TAKE)
    opts = {"music": "epica", "sfx": True}
    done = linea.apply(plan, words, LINE, [
        {"op": "move", "i": 0, "t": 2.9},
        {"op": "text", "i": 0, "text": "Nuevo texto"},
        {"op": "move", "i": 1, "t": 0.4},
        {"op": "resize", "i": 0, "t1": 3.5},
        {"op": "add", "type": "titular", "t": 1.2, "text": "TITULAR"},
        {"op": "add", "type": "inventado", "t": 1.2},
        {"op": "cut", "t0": 1.5, "t1": 2.3},
        {"op": "word", "k": 18, "text": "gratis!"},
        {"op": "music", "style": "tranquila", "volume": 60},
        {"op": "sfx", "t": 1.234},
        {"op": "hook", "text": "Mi gancho"},
        {"op": "delete", "i": 99},
    ], opts)
    a, b = plan.effects[0], plan.effects[1]
    assert a["word"] == 17 and a["text"] == "Nuevo texto" and a["pedido"] and a["until_word"] == 18
    assert b["word"] == 7 and [it["at_word"] for it in b["items"]] == [7, 9] and b["until_word"] == 11
    assert plan.effects[2] == {"type": "titular", "word": 10, "text": "TITULAR", "pedido": True, "until_word": None}
    assert len(plan.effects) == 3  # el tipo inventado no entra
    assert plan.cut == [(11, 12)]
    assert words[18].text == "gratis!" and words[18].start == TAKE[18].start
    assert opts["music"] == "tranquila" and opts["volumen_musica"] == 60 and opts["sfx_fuera"] == [1.23]
    assert plan.hook_title == "Mi gancho" and opts["hook_title"] == "Mi gancho"
    assert len(done) == 10


def test_removed_sounds_stay_out():
    evs = [(0.0, "hit", 1.0), (1.23, "pop", 0.5), (2.0, "pop", 0.5)]
    assert linea.drop_sfx(evs, [1.25]) == [evs[0], evs[2]]


@needs_ffmpeg
def test_timeline_endpoint_edits_and_rerenders(sample, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from iman import config, server

    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    real_run = pipeline.run
    monkeypatch.setattr(pipeline, "run", lambda *a, **k: real_run(*a, **{**k, "words": TAKE}))
    c = TestClient(server.app)
    c.post("/api/settings", json={"provider": "none"})

    def wait(jid):
        for _ in range(240):
            j = c.get(f"/api/jobs/{jid}").json()
            if j["status"] != "working":
                return j
            time.sleep(0.5)
        raise AssertionError("no termina")

    with sample.open("rb") as f:
        job = c.post("/api/jobs", files={"video": ("toma.mp4", f, "video/mp4")}, data={"rhythm": "dinamico"}).json()
    job = wait(job["id"])
    assert job["status"] == "done", job
    line = c.get(f"/api/jobs/{job['id']}/linea").json()
    assert line["video"] and line["captions"] and line["words"] and line["total"] > 0
    assert {"frase", "titular"} <= set(line["addable"])
    r = c.post(f"/api/jobs/{job['id']}/linea", json={"ops": [
        {"op": "add", "type": "frase", "t": 0.5, "text": "Escrito a mano"},
        {"op": "music", "volume": 50},
    ]})
    assert r.status_code == 200, r.text
    assert len(r.json()["cambios"]) == 2
    job = wait(job["id"])
    assert job["status"] == "done", job
    plan = json.loads((tmp_path / "jobs" / job["id"] / "plan.json").read_text())
    assert any(fx.get("text") == "Escrito a mano" and fx.get("pedido") for fx in plan["effects"])
    assert job["options"]["volumen_musica"] == 50
    line = c.get(f"/api/jobs/{job['id']}/linea").json()
    assert any(b["text"] == "Escrito a mano" and not b.get("off") for b in line["blocks"])
    assert c.post(f"/api/jobs/{job['id']}/linea", json={"ops": []}).status_code == 400


def test_kit_always_has_eight_slides_and_a_sticker_story(tmp_path):
    from iman import brand, kit

    words = [Word(w, i * 0.4, i * 0.4 + 0.3) for i, w in enumerate(
        "Hoy te cuento cómo viajar a Japón sin gastar de más. Reserva con tiempo los vuelos y el tren.".split())]
    data = kit.complete({"carousel": [{"title": "Portada", "body": ""}, {"title": "Reserva", "body": "ya"}],
                         "stories": [{"text": "Nuevo", "sticker": "Mira"}]}, words, "Japón", "Escríbeme")
    assert len(data["carousel"]) == 8 and data["carousel"][-1]["title"] == "Reserva"
    assert len(data["stories"]) == 4 and data["stories"][-1]["kind"] == "enlace"
    names = kit.render(data, tmp_path / "kit", brand.Brand(), [])
    assert len(names["carousel"]) == 8 and len(names["stories"]) == 4
    assert (tmp_path / "kit" / "kit.zip").exists()


def test_each_reel_keeps_its_brand(tmp_path, monkeypatch):
    from iman import brand, clientes, config

    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.undo()  # conftest fija brand_dir; aquí probamos el de verdad
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    a = clientes.crear("Hotel Sol")
    b = clientes.crear("Bar Luna")
    clientes.activar(b["id"])
    assert brand.brand_dir() == clientes.dir_for(b["id"]) / "marca"
    with brand.using(a["id"]):
        assert brand.brand_dir() == clientes.dir_for(a["id"]) / "marca"
    with brand.using(""):
        assert brand.brand_dir() == tmp_path / "marca"
    with brand.using("borrado123"):
        assert brand.brand_dir() == tmp_path / "marca"
    with brand.using("activo"):
        assert brand.brand_dir() == clientes.dir_for(b["id"]) / "marca"


def test_prompter_follows_the_voice():
    from iman.apuntador import locate

    s = "Hoy te cuento los tres errores que cometen todos al viajar a Japón por primera vez".split()
    assert locate(s, "te cuento los tres errores", 0) == 6
    assert locate(s, "al viajar a Japón por", 5) == 14
    assert locate(s, "hoy te cuento hoy te cuento los", 0) == 4  # repetir no adelanta
    assert locate(s, "patata frita con queso", 3) is None


def test_prompter_endpoint_answers(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from iman import apuntador, config, server

    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(apuntador, "hear", lambda pcm, *a, **k: "los tres errores")
    c = TestClient(server.app)
    r = c.post("/api/apuntador?cursor=2", files={"audio": ("voz.pcm", b"\0" * 32000, "application/octet-stream")},
               data={"script": "Hoy te cuento los tres errores que cometen todos"})
    assert r.status_code == 200 and r.json() == {"heard": "los tres errores", "at": 6}

    def boom(*a, **k):
        raise RuntimeError("sin modelo")

    monkeypatch.setattr(apuntador, "hear", boom)
    r = c.post("/api/apuntador", files={"audio": ("voz.pcm", b"\0" * 32000, "application/octet-stream")},
               data={"script": "Hola"})
    assert r.status_code == 503


def test_long_video_from_my_youtube(sample, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from iman import config, server, youtube

    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    got = {}

    def fake_download(url, folder, progress=lambda p: None):
        got["url"] = url
        dst = folder / "original.mp4"
        shutil.copy(sample, dst)
        return dst

    def fake_long(job_id, src, workdir, opts):
        got.update(src=src, reels=opts.reels)
        server._set(job_id, status="done", result={"clips": []})

    monkeypatch.setattr(youtube, "download", fake_download)
    monkeypatch.setattr(youtube, "available", lambda: True)
    monkeypatch.setattr(server, "_work_long", fake_long)
    c = TestClient(server.app)
    url = "https://www.youtube.com/watch?v=abc123"
    assert c.post("/api/jobs", data={"mode": "largo", "youtube": url}).status_code == 400  # sin «es mío»
    assert c.post("/api/jobs", data={"mode": "largo", "youtube": "https://vimeo.com/1", "youtube_mio": "true"}).status_code == 400
    assert c.post("/api/jobs", data={"mode": "camara", "youtube": url, "youtube_mio": "true"}).status_code == 400
    assert c.post("/api/jobs", data={"mode": "largo"}).status_code == 400
    job = c.post("/api/jobs", data={"mode": "largo", "youtube": url, "youtube_mio": "true", "reels": "3"}).json()
    for _ in range(40):
        if c.get(f"/api/jobs/{job['id']}").json()["status"] != "working":
            break
        time.sleep(0.1)
    assert got["url"] == url and got["reels"] == 3 and got["src"].name == "original.mp4"
    assert youtube.valid("https://youtu.be/xyz") and not youtube.valid("https://evil.com/youtube.com/watch?v=1")


def test_clips_ask_for_30_to_60_seconds():
    from iman import ai

    words = [Word(f"w{i}", i * 0.5, i * 0.5 + 0.4) for i in range(300)]
    data = {"clips": [{"from": 0, "to": 20, "title": "corto"}, {"from": 30, "to": 120, "title": "bien"},
                      {"from": 130, "to": 299, "title": "largo"}]}
    out = ai.clean_clips(data, words, 5)
    assert [c["title"] for c in out] == ["bien"]


def test_send_from_the_phone(sample, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from iman import config, movil, server

    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    real_run = pipeline.run
    monkeypatch.setattr(pipeline, "run", lambda *a, **k: real_run(*a, **{**k, "words": TAKE}))
    monkeypatch.setitem(movil._state, "token", "clave-secreta")
    monkeypatch.setitem(movil._state, "jobs", [])
    c = TestClient(movil.app)
    assert c.get("/m/otra").status_code == 404
    assert c.get("/api/options").status_code == 404  # en la wifi solo existe la página del móvil
    assert "Enviar a Imán" in c.get("/m/clave-secreta").text
    with sample.open("rb") as f:
        r = c.post("/m/clave-secreta/subir", files={"video": ("movil.mp4", f, "video/mp4")},
                   data={"instructions": "corto", "red": "tiktok"})
    assert r.status_code == 200, r.text
    jid = r.json()["id"]
    for _ in range(240):
        st = c.get(f"/m/clave-secreta/estado/{jid}").json()
        if st["status"] != "working":
            break
        time.sleep(0.5)
    assert st["status"] == "done", st
    assert c.get(f"/m/clave-secreta/reel/{jid}.mp4").status_code == 200
    assert server.JOBS[jid]["options"]["red"] == "tiktok"
    assert c.get("/m/clave-secreta/estado/otro1234").status_code == 404  # solo los reels mandados desde el móvil
    assert "<svg" in movil.qr_svg("http://192.168.1.5:8770/m/x")


def test_reel_without_me_over_pictures(tmp_path, monkeypatch):
    from iman import config, escenas
    from PIL import Image

    from .test_render import _api, _wait

    monkeypatch.setattr(config, "HOME", tmp_path)
    voz = tmp_path / "voz.m4a"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=200:duration=11",
                    "-c:a", "aac", str(voz)], check=True)
    foto = tmp_path / "japon.jpg"
    Image.new("RGB", (900, 1400), "#3366aa").save(foto)
    c, _ = _api(tmp_path, monkeypatch, TAKE)
    with voz.open("rb") as v, foto.open("rb") as b:
        job = c.post("/api/jobs", data={"mode": "ilustrado", "imagenes": "auto"}, files=[
            ("video", ("voz.m4a", v, "audio/mp4")), ("broll", ("japon.jpg", b, "image/jpeg"))]).json()
    job = _wait(c, job)
    assert job["status"] == "done", job.get("error")
    work = tmp_path / "jobs" / job["id"]
    assert (work / "lienzo.mp4").exists() and job["options"]["mode"] == "ilustrado"
    laminas = sorted((work / "escenas").glob("lamina-*.jpg"))
    assert laminas  # la primera escena es tu foto; las demás, láminas con tu marca (sin Pexels ni IA)
    assert media_ok(work / "reel.mp4")
    # Las escenas siguen lo que dices.
    scn = escenas.scenes(TAKE, [3.0, 7.5])
    assert len(scn) == 3 and "gratis" in scn[-1]["text"]
    assert escenas.keywords("Hoy te cuento el error que comete todo el mundo") == "cuento error comete"


def media_ok(p):
    from iman import media

    info = media.probe(p)
    return (info.width, info.height) == (1080, 1920) and info.has_audio


def test_cinema_trailer_from_photos(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from PIL import Image

    from iman import config, server, trailer

    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    config.save({"provider": "none"})
    fotos = []
    for i, col in enumerate(["#335577", "#aa5533", "#228844"]):
        p = tmp_path / f"f{i}.jpg"
        Image.new("RGB", (1000, 1500), col).save(p)
        fotos.append(p)
    c = TestClient(server.app)
    one = [("fotos", ("a.jpg", fotos[0].read_bytes(), "image/jpeg"))]
    assert c.post("/api/trailer", data={"title": "X"}, files=one).status_code == 400  # hacen falta 2
    files = [("fotos", (p.name, p.read_bytes(), "image/jpeg")) for p in fotos]
    job = c.post("/api/trailer", files=files, data={"title": "Japón 2027", "tagline": "Treinta viajeros, un destino",
                                                    "fecha": "Noviembre", "cta": "Reserva", "estilo": "epico"}).json()
    for _ in range(400):
        j = c.get(f"/api/jobs/{job['id']}").json()
        if j["status"] != "working":
            break
        time.sleep(0.5)
    assert j["status"] == "done", j
    assert j["result"]["trailer"]["cards"][0] == "NOVIEMBRE"
    from iman import media

    info = media.probe(tmp_path / "jobs" / job["id"] / "reel.mp4")
    assert (info.width, info.height) == (1080, 1920) and info.has_audio and info.duration > 10
    assert any(r["id"] == job["id"] for r in c.get("/api/reels").json()["reels"])
    sc = trailer.script("Lanzamiento", "Algo nuevo. Llega pronto")
    assert sc["cards"] == ["ALGO NUEVO", "LLEGA PRONTO"] and sc["final"] == "MUY PRONTO"
