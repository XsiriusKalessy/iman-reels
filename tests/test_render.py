"""Prueba de punta a punta con ffmpeg (sin IA ni Whisper: transcripción simulada)."""

import json
import shutil
import subprocess
import time

import pytest

from iman import media, pipeline

from .test_core import TAKE

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="necesita ffmpeg")


@pytest.fixture
def sample(tmp_path):
    p = tmp_path / "toma.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=12",
        "-f", "lavfi", "-i", "sine=frequency=220:duration=12", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(p),
    ], check=True)
    return p


def test_pipeline_renders_vertical_reel(sample, tmp_path):
    cfg = {"provider": "none", "anthropic_key": "", "openai_key": "", "claude_model": "", "openai_model": ""}
    res = pipeline.run(sample, tmp_path / "work", pipeline.EditOptions(), cfg, words=TAKE)
    info = media.probe(res.video)
    assert (info.width, info.height) == (1080, 1920)
    assert abs(info.duration - res.duration_out) < 0.3
    assert res.duration_out < 6
    assert res.plan.hook_title


def test_web_api_flow(sample, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from iman import config, server

    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    # Simulamos la transcripción guardándola antes de que arranque el trabajo.
    real_run = pipeline.run
    monkeypatch.setattr(pipeline, "run", lambda *a, **k: real_run(*a, **{**k, "words": TAKE}))

    c = TestClient(server.app)
    assert c.post("/api/settings", json={"provider": "none", "anthropic_key": "sk-secreta"}).status_code == 200
    s = c.get("/api/settings").json()
    assert s["has_anthropic_key"] and "anthropic_key" not in s

    with sample.open("rb") as f:
        job = c.post("/api/jobs", files={"video": ("toma.mp4", f, "video/mp4")}, data={"rhythm": "dinamico"}).json()
    for _ in range(120):
        job = c.get(f"/api/jobs/{job['id']}").json()
        if job["status"] != "working":
            break
        time.sleep(0.5)
    assert job["status"] == "done", job
    assert c.get(f"/api/jobs/{job['id']}/reel.mp4").status_code == 200
    assert json.loads((tmp_path / "jobs" / job["id"] / "plan.json").read_text())["hook_title"]


def test_chat_applies_revised_plan(sample, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from iman import ai, config, server
    from iman.models import EditPlan

    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    real_run = pipeline.run
    monkeypatch.setattr(pipeline, "run", lambda *a, **k: real_run(*a, **{**k, "words": k.get("words") or TAKE}))

    c = TestClient(server.app)
    c.post("/api/settings", json={"provider": "none"})
    with sample.open("rb") as f:
        job = c.post("/api/jobs", files={"video": ("toma.mp4", f, "video/mp4")}).json()

    def wait(jid):
        for _ in range(120):
            j = c.get(f"/api/jobs/{jid}").json()
            if j["status"] != "working":
                return j
            time.sleep(0.5)

    assert wait(job["id"])["status"] == "done"
    # Sin IA conectada, el chat lo explica en vez de fallar en silencio.
    assert c.post(f"/api/jobs/{job['id']}/chat", json={"message": "hola"}).status_code == 400

    c.post("/api/settings", json={"provider": "claude", "anthropic_key": "sk-test"})
    revised = EditPlan(hook_title="Nuevo gancho", effects=[{"type": "palabra", "word": 18, "text": "GRATIS"}], zooms=[(12, 15)])
    monkeypatch.setattr(ai, "revise_plan", lambda *a: (revised, {"style": "neon"}, "Hecho: gancho nuevo y estilo neón."))
    j = c.post(f"/api/jobs/{job['id']}/chat", json={"message": "cambia el gancho y ponlo en neón"}).json()
    assert j["chat"][-1]["text"].startswith("Hecho")
    j = wait(job["id"])
    assert j["status"] == "done", j
    assert j["options"]["style"] == "neon"
    assert j["result"]["plan"]["hook_title"] == "Nuevo gancho"


def test_text_behind_person_two_pass(sample, tmp_path):
    from iman import segment
    from iman.models import EditPlan

    if not segment.available():
        pytest.skip("sin el modelo de recorte")
    fx = [{"type": "detras", "word": 7, "text": "Imán", "until_word": 12}, {"type": "fondo", "word": 15, "text": "-",
                                                                         "look": "rosa"}]
    cfg = {"provider": "none", "anthropic_key": "", "openai_key": "", "claude_model": "", "openai_model": ""}
    res = pipeline.run(sample, tmp_path / "w", pipeline.EditOptions(), cfg, words=TAKE, plan=EditPlan(effects=fx))
    assert (tmp_path / "w" / "mask.mp4").exists() and (tmp_path / "w" / "behind.ass").exists()
    info = media.probe(res.video)
    assert (info.width, info.height) == (1080, 1920) and abs(info.duration - res.duration_out) < 0.3


def test_library_toggles_and_post(sample, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from iman import ai, config, server

    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    real_run = pipeline.run
    monkeypatch.setattr(pipeline, "run", lambda *a, **k: real_run(*a, **{**k, "words": k.get("words") or TAKE}))
    c = TestClient(server.app)
    c.post("/api/settings", json={"provider": "none"})
    with sample.open("rb") as f:
        job = c.post("/api/jobs", files={"video": ("toma.mp4", f, "video/mp4")}, data={"pack": "viajes"}).json()

    def wait(jid):
        for _ in range(120):
            j = c.get(f"/api/jobs/{jid}").json()
            if j["status"] != "working":
                return j
            time.sleep(0.5)

    jid = job["id"]
    assert wait(jid)["options"]["pack"] == "viajes"
    plan_file = tmp_path / "jobs" / jid / "plan.json"
    plan = json.loads(plan_file.read_text())
    plan["effects"] = [{"type": "palabra", "word": 6, "text": "YA"}, {"type": "plazas", "word": 11, "text": "Solo 3"}]
    plan_file.write_text(json.dumps(plan))

    j = c.post(f"/api/jobs/{jid}/plan", json={"effects_off": [1], "hook_title": "Gancho nuevo"}).json()
    j = wait(jid)
    assert j["status"] == "done", j
    assert [fx.get("off") for fx in j["result"]["plan"]["effects"]] == [False, True]
    ass = (tmp_path / "jobs" / jid / "subs.ass").read_text()
    assert "SOLO 3" not in ass
    assert "YA" in ass
    assert "GANCHO NUEVO" in ass.upper()

    # Revisa lo que dices: recuperar la toma repetida y quitar la última frase.
    rows = c.get(f"/api/jobs/{jid}/review").json()["phrases"]
    first, last = rows[0], rows[-1]
    assert first["state"] == "fuera" and last["state"] == "dentro"
    c.post(f"/api/jobs/{jid}/plan", json={"phrases": [{"from": first["from"], "to": first["to"], "keep": True},
                                                      {"from": last["from"], "to": last["to"], "keep": False}]})
    assert wait(jid)["status"] == "done"
    rows = c.get(f"/api/jobs/{jid}/review").json()["phrases"]
    assert rows[0]["state"] == "dentro" and rows[-1]["state"] == "fuera"
    assert "gratis." in wait(jid)["result"]["removed_words"]

    # Sigue en la biblioteca aunque Imán se reinicie.
    server.JOBS.clear()
    lib = c.get("/api/reels").json()["reels"]
    assert lib[0]["id"] == jid and lib[0]["title"] == "Gancho nuevo"
    assert c.get(f"/api/jobs/{jid}/cover.jpg?t=1.0").status_code == 200

    assert c.post(f"/api/jobs/{jid}/post").status_code == 400  # sin IA
    config.save({"provider": "iman"})
    monkeypatch.setattr(ai, "post_copy", lambda *a: {"caption": "Hola", "hashtags": ["viajes"]})
    assert c.post(f"/api/jobs/{jid}/post").json()["hashtags"] == ["viajes"]

    assert c.delete(f"/api/jobs/{jid}").json()["ok"]
    assert c.get("/api/reels").json()["reels"] == []
    assert c.get("/api/jobs/a..b").status_code == 404
