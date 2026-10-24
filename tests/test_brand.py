"""Kit de marca: colores sacados del logo, estilo con la marca, cierre y API."""

import io
import shutil
import subprocess

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from iman import ai, brand, config, effects, media, pipeline
from iman.captions import STYLES, rgb

from .test_core import TAKE


def _logo_png() -> bytes:
    img = Image.new("RGBA", (600, 300), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 380, 300], fill=(20, 110, 190, 255))  # azul, el color principal
    d.ellipse([400, 80, 560, 240], fill=(250, 170, 30, 255))  # naranja, el secundario
    d.rectangle([60, 120, 300, 180], fill=(255, 255, 255, 255))  # texto blanco: se ignora
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _close(a: str, b: tuple, tol=30) -> bool:
    h = a.lstrip("#")
    return all(abs(int(h[i:i + 2], 16) - v) <= tol for i, v in zip((0, 2, 4), b))


def test_logo_gives_brand_colors():
    b = brand.set_logo(_logo_png())
    assert b.logo_path is not None
    assert _close(b.primary, (20, 110, 190)) and _close(b.secondary, (250, 170, 30))
    # Si el creador ya eligió su color, el logo no se lo pisa.
    b.primary = "#FF0000"
    brand.save(b)
    assert brand.set_logo(_logo_png()).primary == "#FF0000"
    assert brand.remove_logo().logo_path is None


def test_apply_brand_to_style():
    b = brand.Brand(primary="#146EBE", secondary="#FAAA1E", font="Elegante")
    s = brand.apply(STYLES["impacto"], b)
    assert s.accent == rgb("#146EBE") and s.title_box == rgb("#146EBE")
    assert s.font == "Playfair Display ExtraBold"
    boxed = brand.apply(STYLES["caja"], b)
    assert boxed.box == rgb("#146EBE") and boxed.accent == rgb("#FAAA1E")
    assert brand.apply(STYLES["impacto"], brand.Brand()) == STYLES["impacto"]
    assert brand.ink_on("#FFE600") == "#141518" and brand.ink_on("#123A35") == "#FFFFFF"


def test_brand_ops_and_end_card():
    b = brand.set_logo(_logo_png())
    b.cta, b.handle = "Reserva por WhatsApp", "@viajesnelson"
    ops = effects.brand_ops(b, 20.0)
    assert [o.kind for o in ops] == ["logo", "endcard", "logo_end"]
    assert ops[0].end == ops[1].start == 20.0 - effects.END_CARD
    lines, win = effects.end_card_events(b, STYLES["impacto"], 20.0)
    assert win.start == 20.0 - effects.END_CARD and any("Reserva por WhatsApp" in l for l in lines)
    # Reel muy corto: sin cierre, solo el logo.
    assert [o.kind for o in effects.brand_ops(b, 3.0)] == ["logo"]
    assert effects.end_card_events(b, STYLES["impacto"], 3.0) == ([], None)
    brand.remove_logo()
    assert effects.brand_ops(brand.Brand(), 20.0) == []


def test_brand_api(tmp_path, monkeypatch):
    from iman import server

    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    c = TestClient(server.app)
    assert c.get("/api/brand").json()["has_logo"] is False
    r = c.post("/api/brand/logo", files={"logo": ("logo.png", _logo_png(), "image/png")}).json()
    assert r["has_logo"] and r["primary"] and len(r["palette"]) >= 2
    assert c.get("/api/brand/logo.png").status_code == 200
    assert c.post("/api/brand", json={"primary": "rojo"}).status_code == 400
    r = c.post("/api/brand", json={"cta": " Escríbenos ", "font": "Impacto"}).json()
    assert r["cta"] == "Escríbenos" and r["font"] == "Impacto"
    assert c.post("/api/brand/logo", files={"logo": ("x.png", b"nada", "image/png")}).status_code == 400

    config.save({"provider": "iman"})
    monkeypatch.setattr(ai, "brand_copy", lambda cfg, d: {"name": "Viajes Nelson", "cta": "Reserva tu viaje",
                                                         "font": "Elegante"})
    r = c.post("/api/brand/auto", json={"description": "agencia de viajes en Valencia"}).json()
    assert r["name"] == "Viajes Nelson" and r["cta"] == "Reserva tu viaje" and r["font"] == "Elegante"
    assert c.delete("/api/brand/logo").json()["has_logo"] is False


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="necesita ffmpeg")
def test_reel_with_brand(tmp_path):
    src = tmp_path / "toma.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:size=1280x720:rate=30:duration=12",
        "-f", "lavfi", "-i", "sine=frequency=220:duration=12", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(src),
    ], check=True)
    b = brand.set_logo(_logo_png())
    b.cta = "Reserva por WhatsApp"
    brand.save(b)
    cfg = {**config.DEFAULTS, "provider": "none"}
    res = pipeline.run(src, tmp_path / "work", pipeline.EditOptions(rhythm="natural"), cfg, words=TAKE)
    if res.duration_out <= effects.END_CARD + 1:
        pytest.skip("toma demasiado corta para el cierre")
    # En el cierre, el fondo es el color de la marca (esquina de abajo, lejos del logo y los textos).
    frame = tmp_path / "end.png"
    media.thumbnail(res.video, frame, res.duration_out - 0.4)
    px = Image.open(frame).convert("RGB").getpixel((60, 1860))
    assert _close("#%02X%02X%02X" % px, tuple(int(b.primary[i:i + 2], 16) for i in (1, 3, 5)), tol=40)
    # Durante el reel, el logo está arriba a la derecha y el fondo sigue gris.
    mid = tmp_path / "mid.png"
    media.thumbnail(res.video, mid, 0.8)
    im = Image.open(mid).convert("RGB")
    assert _close("#%02X%02X%02X" % im.getpixel((60, 1000)), (128, 128, 128), tol=40)
    assert _close("#%02X%02X%02X" % im.getpixel((1080 - 40 - 60, 230)), (20, 110, 190), tol=45)


def test_memory_is_saved_and_reaches_new_reels(tmp_path, monkeypatch):
    from iman import config

    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(config, "HOME", tmp_path)
    assert config.memory_prompt(config.load()) == ""
    config.remember("Subtítulos grandes y nada de música")
    config.remember("subtítulos grandes y nada de música")  # no se repite
    config.remember("Pon mi web al final")
    mem = config.load()["memory"]
    assert len(mem) == 2
    assert "Pon mi web al final" in config.memory_prompt(config.load())


def test_kit_copy_is_cleaned_and_revision_gets_current_kit(monkeypatch):
    from iman import ai

    seen = {}

    def fake(cfg, system, user, schema):
        seen["user"] = user
        return {"carousel": [{"title": " Portada ", "body": ""}, {"title": "", "body": "sin título"}],
                "stories": [{"text": "Hola", "sticker": "Nuevo"}], "reply": "Hecho"}

    monkeypatch.setattr(ai, "_ask_json", fake)
    cfg = ai.AIConfig(provider="claude", anthropic_key="x")
    k = ai.kit_copy(cfg, "texto", "Gancho", "", "", {"carousel": [{"title": "A", "body": ""}]}, "en la diapositiva 1 pon B")
    assert k["carousel"] == [{"title": "Portada", "body": ""}] and k["reply"] == "Hecho"
    assert "KIT ACTUAL" in seen["user"] and "diapositiva 1" in seen["user"]


def test_own_font_upload_and_render(tmp_path, monkeypatch):
    from iman import server, textfit

    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    c = TestClient(server.app)
    data = (textfit.FONTS_DIR / "Caveat-Bold.ttf").read_bytes()
    assert c.post("/api/brand/font", files={"font": ("x.ttf", b"nada", "font/ttf")}).status_code == 400
    r = c.post("/api/brand/font", files={"font": ("MiLetra.ttf", data, "font/ttf")}).json()
    assert r["font"] == brand.MINE and r["my_font"] and brand.MINE in r["fonts"]
    assert c.get("/api/brand/font").status_code == 200
    c.post("/api/brand", json={"primary": "#D4A537"})
    style = brand.styled(next(iter(STYLES)))
    assert style.font == r["my_font"]
    assert textfit.width("Hola", style.font, 80) > 0
    d = textfit.fonts_dir()
    assert d != textfit.FONTS_DIR and len(list(d.iterdir())) == len(textfit.FILES) + 1
    assert (d / "Anton-Regular.ttf").exists()
    r = c.delete("/api/brand/font").json()
    assert r["font"] == "" and not r["my_font"] and textfit.fonts_dir() == textfit.FONTS_DIR


@pytest.mark.parametrize("variant", ["color", "marca_degradado", "marca_bokeh", "marca_logo"])
def test_brand_backgrounds_are_dark_with_brand_light(tmp_path, variant):
    from iman import fondos

    logo = tmp_path / "logo.png"
    logo.write_bytes(_logo_png())
    img = Image.open(fondos.render(variant, "#D4A537", "#111111", tmp_path / "f.jpg", logo)).convert("RGB")
    assert img.size == (1080, 1920)
    px = [tuple(p) for p in np.asarray(img.resize((54, 96))).reshape(-1, 3).tolist()]
    mean = sum(sum(p) for p in px) / (3 * len(px))
    assert 12 < mean < 120  # oscuro, pero no negro: lleva la luz de la marca
    r, g, b = max(px, key=sum)
    assert r > b + 15  # el tono de la marca (dorado) se nota
