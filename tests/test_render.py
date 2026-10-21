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
    (tmp_path / "jobs" / job["id"] / "transcript.json").write_text(json.dumps([w.__dict__ for w in TAKE]))

    c.post("/api/settings", json={"provider": "claude", "anthropic_key": "sk-test"})
    revised = EditPlan(hook_title="Nuevo gancho", effects=[{"type": "palabra", "word": 18, "text": "GRATIS"}], zooms=[(12, 15)])
    monkeypatch.setattr(ai, "revise_plan", lambda *a: (revised, {"style": "neon"}, "Hecho: gancho nuevo y estilo neón."))
    j = c.post(f"/api/jobs/{job['id']}/chat", json={"message": "cambia el gancho y ponlo en neón"}).json()
    assert j["chat"][-1]["text"].startswith("Hecho")
    j = wait(job["id"])
    assert j["status"] == "done", j
    assert j["options"]["style"] == "neon"
    assert j["result"]["plan"]["hook_title"] == "Nuevo gancho"
