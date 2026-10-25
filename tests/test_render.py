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
    assert (tmp_path / "w" / "behind.ass").exists() and not res.notices
    assert not list((tmp_path / "w").glob("*.tmp.mp4"))  # los intermedios se borran
    info = media.probe(res.video)
    assert (info.width, info.height) == (1080, 1920) and abs(info.duration - res.duration_out) < 0.3


def test_broken_effect_pass_still_gives_a_reel(sample, tmp_path, monkeypatch):
    from iman import segment
    from iman.models import EditPlan

    if not segment.available():
        pytest.skip("sin el modelo de recorte")

    def broken(*a, **k):
        raise RuntimeError("ffmpeg falló: Invalid NAL unit size")

    monkeypatch.setattr(media, "composite", broken)
    fx = [{"type": "fondo", "word": 15, "text": "-", "look": "rosa"}]
    cfg = {"provider": "none", "anthropic_key": "", "openai_key": "", "claude_model": "", "openai_model": ""}
    res = pipeline.run(sample, tmp_path / "w", pipeline.EditOptions(), cfg, words=TAKE, plan=EditPlan(effects=fx))
    assert res.notices and res.video.name == "reel.mp4"
    assert abs(media.probe(res.video).duration - res.duration_out) < 0.3
    assert not list((tmp_path / "w").glob("*.tmp.mp4"))


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

    # Carrusel e historias, sin IA: salen de las frases del vídeo.
    kit = c.post(f"/api/jobs/{jid}/kit", json={}).json()
    assert len(kit["carousel"]) >= 2 and len(kit["stories"]) == 3
    r = c.get(f"/api/jobs/{jid}/kit/{kit['carousel'][0]}")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert c.get(f"/api/jobs/{jid}/kit/kit.zip").status_code == 200
    assert c.get(f"/api/jobs/{jid}/kit/..%2Fplan.json").status_code == 404
    assert c.post(f"/api/jobs/{jid}/kit", json={"message": "cambia la 3"}).status_code == 400

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


def test_copy_style_from_a_reel(sample, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from iman import ai, config, copystyle, server
    from iman.captions import STYLES, rgb

    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(config, "HOME", tmp_path)
    seen = {}

    def fake(cfg, frames, extra=""):
        seen["n"] = len(frames)
        assert all(f[:2] == b"\xff\xd8" for f in frames)  # JPEG
        return {"name": "Amarillo grande", "font": "Condensada", "uppercase": True, "words_per_line": 2,
                "position": "centro", "size": "grande", "text_color": "#ffffff", "highlight_color": "#FFD400",
                "outline": True, "box": False, "box_color": "", "pop": True, "notes": "Letra alta y amarilla."}

    monkeypatch.setattr(ai, "style_from_frames", fake)
    c = TestClient(server.app)
    config.save({"provider": "none"})
    with sample.open("rb") as f:
        assert c.post("/api/styles/copy", files={"file": ("r.mp4", f, "video/mp4")}).status_code == 400  # sin IA
    config.save({"provider": "iman"})
    with sample.open("rb") as f:
        r = c.post("/api/styles/copy", files={"file": ("r.mp4", f, "video/mp4")}, data={"name": ""}).json()
    assert seen["n"] >= 3 and r["key"] == "mio-amarillo-grande" and r["rhythm"] in ("rapido", "dinamico", "natural")
    st = STYLES[r["key"]]
    assert st.font == "Anton" and st.uppercase and st.max_words == 2 and st.accent == rgb("#FFD400") and st.y == 1000
    assert any(s["key"] == r["key"] and s["mine"] for s in c.get("/api/options").json()["styles"])

    # Se usa como cualquier otro estilo.
    real_run = pipeline.run
    monkeypatch.setattr(pipeline, "run", lambda *a, **k: real_run(*a, **{**k, "words": k.get("words") or TAKE}))
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    config.save({"provider": "none"})
    with sample.open("rb") as f:
        job = c.post("/api/jobs", files={"video": ("toma.mp4", f, "video/mp4")}, data={"style": r["key"]}).json()
    for _ in range(120):
        j = c.get(f"/api/jobs/{job['id']}").json()
        if j["status"] != "working":
            break
        time.sleep(0.5)
    assert j["status"] == "done", j
    assert "Anton" in (tmp_path / "jobs" / job["id"] / "subs.ass").read_text()

    assert c.delete(f"/api/styles/{r['key']}").status_code == 200 and r["key"] not in STYLES
    assert c.delete("/api/styles/impacto").status_code == 400
    copystyle.register()


def test_broll_with_face_bubble(sample, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from iman import config, server

    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    real_run = pipeline.run
    monkeypatch.setattr(pipeline, "run", lambda *a, **k: real_run(*a, **{**k, "words": TAKE}))
    foto, clip = tmp_path / "playa.jpg", tmp_path / "barco.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x2a7fd4:s=1600x900", "-frames:v", "1",
                    str(foto)], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=25:duration=1",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)

    c = TestClient(server.app)
    c.post("/api/settings", json={"provider": "none"})
    with sample.open("rb") as v, foto.open("rb") as a, clip.open("rb") as b:
        job = c.post("/api/jobs", data={"rhythm": "natural"}, files=[
            ("video", ("toma.mp4", v, "video/mp4")), ("broll", ("playa.jpg", a, "image/jpeg")),
            ("broll", ("barco.mp4", b, "video/mp4")), ("broll", ("notas.txt", b"hola", "text/plain"))]).json()
    for _ in range(240):
        job = c.get(f"/api/jobs/{job['id']}").json()
        if job["status"] != "working":
            break
        time.sleep(0.25)
    assert job["status"] == "done", job.get("error")
    work = tmp_path / "jobs" / job["id"]
    assert sorted(p.name for p in (work / "apoyo").iterdir()) == ["01.jpg", "02.mp4"]
    fx = [e for e in job["result"]["plan"]["effects"] if e["type"] == "apoyo"]
    assert [e["text"] for e in fx] == ["1", "2"]
    assert "playa" in job["options"]["instructions"]


def _api(tmp_path, monkeypatch, words):
    from fastapi.testclient import TestClient

    from iman import config, server

    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(pipeline, "_transcribe", lambda *a, **k: list(words))
    monkeypatch.setattr(pipeline.hands, "available", lambda: False)  # las manos tienen su propia prueba
    c = TestClient(server.app)
    c.post("/api/settings", json={"provider": "none"})
    return c, server


def _wait(c, job):
    for _ in range(800):
        job = c.get(f"/api/jobs/{job['id']}").json()
        if job["status"] != "working":
            return job
        time.sleep(0.25)
    return job


def test_voice_only_over_my_clips(tmp_path, monkeypatch):
    voz, clip = tmp_path / "voz.m4a", tmp_path / "playa.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=200:duration=11",
                    "-c:a", "aac", str(voz)], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=25:duration=2",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)
    c, _ = _api(tmp_path, monkeypatch, TAKE)
    with voz.open("rb") as v, clip.open("rb") as b:
        job = c.post("/api/jobs", data={"mode": "voz", "rhythm": "natural"}, files=[
            ("video", ("voz.m4a", v, "audio/mp4")), ("broll", ("playa.mp4", b, "video/mp4"))]).json()
    job = _wait(c, job)
    assert job["status"] == "done", job.get("error")
    work = tmp_path / "jobs" / job["id"]
    assert (work / "lienzo.mp4").exists()
    info = media.probe(work / "reel.mp4")
    assert (info.width, info.height) == (1080, 1920) and info.has_audio
    assert not any(e["type"] == "apoyo" for e in job["result"]["plan"]["effects"])
    # Solo voz y sin vídeos: fondo liso con tu voz.
    with voz.open("rb") as v:
        job = _wait(c, c.post("/api/jobs", data={"mode": "voz"}, files={"video": ("voz.m4a", v, "audio/mp4")}).json())
    assert job["status"] == "done", job.get("error")


def test_visual_cuts_every_few_seconds():
    from .test_core import W

    words = W([(f"p{i}{'.' if i % 5 == 4 else ''}", i * 0.5, i * 0.5 + 0.4) for i in range(40)])
    cuts = pipeline.visual_cuts(words)
    assert cuts and all(2.0 <= b - a <= 4.5 for a, b in zip([0.0, *cuts], cuts))


def test_long_video_to_several_reels(tmp_path, monkeypatch):
    from .test_core import W

    largo = tmp_path / "directo.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=95",
        "-f", "lavfi", "-i", "sine=frequency=220:duration=95", "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(largo)], check=True)
    words = W([(f"palabra{i}{'.' if i % 12 == 11 else ''}", i * 0.6 + 0.3, i * 0.6 + 0.8) for i in range(155)])
    c, server = _api(tmp_path, monkeypatch, words)
    with largo.open("rb") as v:
        job = _wait(c, c.post("/api/jobs", data={"mode": "largo", "rhythm": "natural"},
                              files={"video": ("directo.mp4", v, "video/mp4")}).json())
    assert job["status"] == "done", job.get("error")
    clips = job["result"]["clips"]
    assert len(clips) >= 2
    for cl in clips:
        assert 10 < cl["duration"] < 70
        assert media.probe(tmp_path / "jobs" / cl["id"] / "reel.mp4").duration > 10
    lib = c.get("/api/reels").json()["reels"]
    assert {r["id"] for r in lib} == {cl["id"] for cl in clips}


def test_object_stickers_over_a_list(sample, tmp_path, monkeypatch):
    from iman.models import EditPlan

    monkeypatch.setattr("iman.stickers.HOME", tmp_path / "home")
    fx = [{"type": "lista", "title": "", "items": [{"text": "Adaptador", "at_word": 3}, {"text": "Calcetines", "at_word": 7}],
           "until_word": 12, "look": "checklist"},
          {"type": "objeto", "word": 3, "text": "🔌", "subtitle": "Adaptador"},
          {"type": "objeto", "word": 7, "text": "🧦", "subtitle": "Calcetines 🇯🇵"}]
    cfg = {"provider": "none", "anthropic_key": "", "openai_key": "", "claude_model": "", "openai_model": ""}
    res = pipeline.run(sample, tmp_path / "w", pipeline.EditOptions(), cfg, words=TAKE, plan=EditPlan(effects=fx))
    assert len(list((tmp_path / "home" / "cache" / "stickers").glob("*.png"))) == 2
    info = media.probe(res.video)
    assert (info.width, info.height) == (1080, 1920) and abs(info.duration - res.duration_out) < 0.3


@pytest.mark.parametrize("background", ["foto", "color"])
def test_whole_reel_background(sample, tmp_path, background):
    from iman import segment

    if not segment.available():
        pytest.skip("sin el modelo de recorte")
    work = tmp_path / "w"
    work.mkdir()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0xd43a2a:s=800x600", "-frames:v", "1",
                    str(work / "fondo.jpg")], check=True)
    cfg = {"provider": "none", "anthropic_key": "", "openai_key": "", "claude_model": "", "openai_model": ""}
    res = pipeline.run(sample, work, pipeline.EditOptions(background=background), cfg, words=TAKE)
    assert not res.notices  # la pasada con la persona recortada ha salido bien
    info = media.probe(res.video)
    assert (info.width, info.height) == (1080, 1920) and abs(info.duration - res.duration_out) < 0.3


def test_hook_sound_music_and_punch(sample, tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=330:duration=2",
                    str(work / "musica.mp3")], check=True)
    cfg = {"provider": "none", "anthropic_key": "", "openai_key": "", "claude_model": "", "openai_model": ""}
    res = pipeline.run(sample, work, pipeline.EditOptions(music=True), cfg, words=TAKE)
    assert (work / "sfx.wav").exists()
    info = media.probe(res.video)
    assert (info.width, info.height) == (1080, 1920) and abs(info.duration - res.duration_out) < 0.3
    # El golpe del gancho: el primer cuarto de segundo ya suena fuerte.
    vol = subprocess.run(["ffmpeg", "-v", "info", "-t", "0.25", "-i", str(res.video), "-af", "volumedetect",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    peak = float(vol.split("max_volume:")[1].split("dB")[0])
    assert peak > -12


def test_sfx_bed_places_sounds(tmp_path):
    import wave

    from iman import sfx

    dst = sfx.bed([(0.0, "impact", 1.0), (1.0, "pop", 0.5), (9.0, "whoosh", 1.0)], 2.0, tmp_path / "s.wav")
    with wave.open(str(dst)) as w:
        assert w.getframerate() == sfx.RATE and abs(w.getnframes() / sfx.RATE - 2.05) < 0.01


def test_breathing_beats_leave_a_rest():
    from iman.effects import beat_spans
    from iman.models import Word
    from iman.rhythm import Span

    words = [Word(f"w{i}", i * 0.5, i * 0.5 + 0.4) for i in range(80)]  # 40 s hablando sin parar
    _, beats = beat_spans([Span(0.0, 40.0)], words)
    b = sorted(beats)
    steps = [y - x for x, y in zip([0.0, *b], b)]
    assert len(b) >= 8 and max(steps) > 4.0 and min(steps) > 1.5


def test_dramatic_silence_window():
    from iman import effects, pipeline
    from iman.models import Word

    words = [Word(t, i * 0.5, i * 0.5 + 0.4) for i, t in enumerate("a b c d e f g h i j Y esto lo cambia todo. k l".split())]
    clock = effects.WordClock(words, list(range(len(words))))
    hush = pipeline._hush_windows([10], words, clock)
    assert hush and abs(hush[0][0] - 4.85) < 0.01 and abs(hush[0][1] - 7.5) < 0.01
    evs = pipeline._sfx_events([], clock, True, set(), [], hush)
    assert ("hit" in [n for t, n, g in evs if abs(t - hush[0][1]) < 1e-6])
    assert not any(hush[0][0] - 0.4 <= t < hush[0][1] for t, n, g in evs)


@pytest.mark.parametrize("style", ["epica", "piano"])
def test_iman_music_styles(sample, tmp_path, style):
    from iman import musica

    dst = musica.render(style, 7.3, tmp_path / "m.wav")
    assert abs(media.probe_duration(dst) - 7.3) < 3.5 if hasattr(media, "probe_duration") else dst.stat().st_size > 1000
    cfg = {"provider": "none", "anthropic_key": "", "openai_key": "", "claude_model": "", "openai_model": ""}
    res = pipeline.run(sample, tmp_path / "w", pipeline.EditOptions(music=style), cfg, words=TAKE)
    assert (tmp_path / "w" / "musica_iman.wav").exists()
    assert abs(media.probe(res.video).duration - res.duration_out) < 0.3


def test_everything_sound_and_new_effects_together(sample, tmp_path):
    """Música de Imán + silencio dramático + efectos de sonido + zoom de entrada + los efectos nuevos."""
    from iman.models import EditPlan

    fx = [{"type": "notificaciones", "word": 6, "until_word": 9, "text": "Nuevo pedido|Reserva confirmada",
           "title": "Tienda"},
          {"type": "anillo", "word": 10, "until_word": 13, "text": "SOLO HOY"},
          {"type": "foco", "word": 16, "until_word": 18, "text": "Y es gratis"}]
    plan = EditPlan(hook_title="El error de todos", effects=fx, silence=[16], music="synthwave")
    cfg = {"provider": "none", "anthropic_key": "", "openai_key": "", "claude_model": "", "openai_model": ""}
    res = pipeline.run(sample, tmp_path / "w", pipeline.EditOptions(rhythm="sin_tocar"), cfg, words=TAKE,
                       plan=plan)
    graph = (tmp_path / "w" / "reel.filters.txt").read_text(encoding="utf-8")
    assert "between(t," in graph and "sidechaincompress" in graph and "zoompan" in graph
    assert abs(media.probe(res.video).duration - res.duration_out) < 0.3


@pytest.mark.parametrize("look", ["teal", "retro"])
def test_looks_and_new_templates(sample, tmp_path, look):
    from iman.models import EditPlan

    fx = [{"type": "buscador", "word": 6, "until_word": 10, "text": "cómo ahorrar en vuelos"},
          {"type": "chat", "word": 11, "until_word": 18, "text": "¿Cuánto cuesta?|Desde 2.900 €"}]
    cfg = {"provider": "none", "anthropic_key": "", "openai_key": "", "claude_model": "", "openai_model": ""}
    res = pipeline.run(sample, tmp_path / "w", pipeline.EditOptions(rhythm="sin_tocar", look=look, barra=True),
                       cfg, words=TAKE, plan=EditPlan(effects=fx))
    assert media.LOOKS[look].split("=")[0] in (tmp_path / "w" / "reel.filters.txt").read_text(encoding="utf-8")
    assert abs(media.probe(res.video).duration - res.duration_out) < 0.3


def test_whip_and_glitch_transitions_render(sample, tmp_path):
    from iman.models import Span

    spans = [Span(0.0, 1.5), Span(2.0, 3.5), Span(4.0, 5.5), Span(6.0, 7.5), Span(8.0, 9.5)]
    trans = media.transition_plan(spans)
    assert set(trans.values()) == {"whip", "glitch"}
    info = media.probe(sample)
    out = media.render(sample, tmp_path / "t.mp4", spans, info, None, preset="ultrafast", transitions=trans)
    assert abs(media.probe(out).duration - 7.5) < 0.3


def test_captura_and_collage_from_support_photos(sample, tmp_path):
    from PIL import Image
    from iman.models import EditPlan

    work = tmp_path / "w"
    (work / "apoyo").mkdir(parents=True)
    for i, c in enumerate([(200, 40, 40), (40, 160, 90), (40, 80, 200)]):
        Image.new("RGB", (900, 1200), c).save(work / "apoyo" / f"0{i + 1}.jpg")
    fx = [{"type": "captura", "word": 4, "text": "1", "subtitle": "Mi web"},
          {"type": "collage", "word": 12, "text": "1,2,3", "subtitle": "Tokio|Kioto|Osaka"}]
    cfg = {"provider": "none", "anthropic_key": "", "openai_key": "", "claude_model": "", "openai_model": ""}
    res = pipeline.run(sample, work, pipeline.EditOptions(rhythm="sin_tocar"), cfg, words=TAKE,
                       plan=EditPlan(effects=fx))
    graph = (work / "reel.filters.txt").read_text(encoding="utf-8")
    assert graph.count("overlay") >= 2
    assert abs(media.probe(res.video).duration - res.duration_out) < 0.3


def test_trip_map_3d(sample, tmp_path, monkeypatch):
    from iman import config, mapa
    from iman.models import EditPlan

    monkeypatch.setattr(config, "HOME", tmp_path / "home")
    assert mapa.geocode("Kioto") and mapa.geocode("Nueva York") and mapa.geocode("Sitio inventado") is None
    route = mapa.stops("Tokio › Kioto (35.01, 135.77) › Osaka")
    assert [r[0] for r in route] == ["Tokio", "Kioto", "Osaka"] and route[1][1:] == (35.01, 135.77)
    assert mapa.stops("Tokio › Sitio inventado") is None
    fx = [{"type": "viaje", "word": 4, "text": "Tokio (35.68, 139.69) › Kioto (35.01, 135.77) › Osaka",
           "title": "Japón en grupo", "subtitle": "18–29 nov"}]
    cfg = {"provider": "none", "anthropic_key": "", "openai_key": "", "claude_model": "", "openai_model": ""}
    res = pipeline.run(sample, tmp_path / "w", pipeline.EditOptions(rhythm="sin_tocar"), cfg, words=TAKE,
                       plan=EditPlan(effects=fx))
    maps = list((tmp_path / "home" / "cache" / "mapas").glob("*.mp4"))
    assert len(maps) == 1 and media.probe(maps[0]).duration >= 2.9
    assert abs(media.probe(res.video).duration - res.duration_out) < 0.3


def test_split_for_whatsapp_status():
    assert media.split_points(50, []) == []
    assert media.split_points(130, []) == [59.0, 118.0]
    # Corta en el último silencio que quepa, no a mitad de palabra.
    cuts = media.split_points(100, [(20.0, 20.4), (52.0, 52.6), (58.9, 59.5), (80.0, 80.3)])
    assert cuts == [52.3]


def test_whatsapp_zip_endpoint(tmp_path, monkeypatch):
    import zipfile

    from fastapi.testclient import TestClient

    from iman import server

    monkeypatch.setattr(server, "JOBS_DIR", tmp_path)
    (tmp_path / "j").mkdir()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=270x480:r=30:d=70",
                    "-f", "lavfi", "-i", "sine=frequency=300:duration=70", "-c:v", "libx264", "-preset", "ultrafast",
                    "-c:a", "aac", "-shortest", str(tmp_path / "j" / "reel.mp4")], check=True)
    r = TestClient(server.app).get("/api/jobs/j/whatsapp.zip")
    assert r.status_code == 200
    (tmp_path / "w.zip").write_bytes(r.content)
    names = zipfile.ZipFile(tmp_path / "w.zip").namelist()
    assert names == ["estado-1-de-2.mp4", "estado-2-de-2.mp4"]


def test_bar_chart_effect():
    from iman import packfx
    from iman.captions import STYLES
    from iman.effects import WordClock
    from iman.models import Word

    assert packfx._number("1.200 €") == 1200 and packfx._number("35 %") == 35 and packfx._number("2,5") == 2.5
    words = [Word(f"w{i}", i * 0.4, i * 0.4 + 0.3) for i in range(20)]
    clock = WordClock(words, list(range(20)))
    fx = {"type": "grafico", "word": 2, "until_word": 12, "text": "Enero: 900 €|Junio: 450 €", "title": "Vuelo"}
    lines, win = packfx.grafico_events(fx, clock, STYLES["impacto"], 10.0)
    assert win and sum("\\fscy0" in ln for ln in lines) == 2 and any("450 €" in ln for ln in lines)
    assert packfx.grafico_events({**fx, "text": "sin cifras"}, clock, STYLES["impacto"], 10.0) == ([], None)


def test_takes_are_joined_with_matching_colour(tmp_path):
    a, b = tmp_path / "a.mp4", tmp_path / "b.mov"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=720x1280:rate=30:duration=2",
                    "-f", "lavfi", "-i", "sine=frequency=300:duration=2", "-pix_fmt", "yuv420p", "-shortest", str(a)],
                   check=True)
    # Segunda toma: otra resolución, sin audio, más oscura y más azul.
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=25:duration=2",
                    "-vf", "eq=brightness=-0.15,colorbalance=bm=0.3", "-pix_fmt", "yuv420p", str(b)], check=True)
    before = media.color_stats(b)
    target = media.color_stats(a)
    out = media.join_takes([a, b], tmp_path / "original.mp4")
    info = media.probe(out)
    assert (info.width, info.height) == (720, 1280) and info.has_audio
    assert abs(info.duration - 4) < 0.3
    assert not list(tmp_path.glob("original.*.txt"))
    second = tmp_path / "second.mp4"
    media.cut(out, second, 2.2, 3.8)
    after = media.color_stats(second)
    gap = lambda s: sum(abs(x - y) for x, y in zip(s[0], target[0]))  # noqa: E731
    assert gap(after) < gap(before) * 0.5


def test_broll_speed_ramp_fills_the_slot():
    assert media.ramp_pts(1.0) == "" and media.ramp_need(1.0) == 1.0
    assert media.ramp_pts(3.0, on=False) == ""
    d = 3.0
    need = media.ramp_need(d)
    # El tiempo de salida del último fotograma de entrada cae justo al final del hueco.
    out_end = media.RAMP_FAST_IN / media.RAMP_FAST + (need - media.RAMP_FAST_IN) / media.RAMP_SLOW
    assert abs(out_end - d) < 1e-6


def test_api_accepts_several_takes(sample, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from iman import config, server

    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    real_run = pipeline.run
    monkeypatch.setattr(pipeline, "run", lambda *a, **k: real_run(*a, **{**k, "words": TAKE}))
    c = TestClient(server.app)
    c.post("/api/settings", json={"provider": "none"})
    with sample.open("rb") as v, sample.open("rb") as w:
        job = c.post("/api/jobs", data={"rhythm": "natural"}, files=[
            ("video", ("toma1.mp4", v, "video/mp4")), ("video", ("toma2.mp4", w, "video/mp4"))]).json()
    for _ in range(240):
        job = c.get(f"/api/jobs/{job['id']}").json()
        if job["status"] != "working":
            break
        time.sleep(0.25)
    assert job["status"] == "done", job.get("error")
    work = tmp_path / "jobs" / job["id"]
    assert [p.name for p in work.glob("original.*")] == ["original.mp4"]
    assert abs(media.probe(work / "original.mp4").duration - 24) < 0.5
    assert not list(work.glob("toma-*"))
