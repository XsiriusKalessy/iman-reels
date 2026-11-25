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
