"""Efectos con las manos: gestos a partir de puntos de la mano (sin vídeo real) y montaje con ffmpeg."""

import shutil
import subprocess

import pytest

from iman import effects, gestos, hands, media, pipeline
from iman.captions import STYLES
from iman.models import EditPlan, Span

from .test_core import TAKE, W


def hand(dy: float = 0.0, point: bool = True) -> list[list[float]]:
    """Mano derecha señalando hacia arriba (o abierta), desplazada `dy` en vertical."""
    pts = [[0.5, 0.8]] + [[0.45, 0.72]] * 4  # muñeca y pulgar
    pts += [[0.5, 0.65], [0.5, 0.58], [0.5, 0.53], [0.5, 0.48]]  # índice estirado
    for x in (0.53, 0.56, 0.59):
        tip = [x, 0.68] if point else [x, 0.45]  # recogido (cerca de la muñeca) o estirado
        pts += [[x, 0.66], [x, 0.62], [x, 0.64], tip]
    return [[x, y + dy] for x, y in pts]


def test_finger_up_is_a_rising_gesture():
    frames = [{"t": k / 10, "hands": [hand(-0.02 * k)]} for k in range(10)]
    found = hands.gestures(frames)
    assert [g.kind for g in found] == ["sube"]
    assert found[0].path[0][2] > found[0].path[-1][2]  # la yema sube


def test_open_hand_is_not_pointing():
    assert hands.pointing(hand(point=False)) is None
    assert hands.pointing(hand()) is not None


def test_mapping_keeps_the_centre():
    info = media.MediaInfo(width=1920, height=1080, duration=10, fps=30, has_audio=True, hdr=False)
    assert gestos._to_reel(0.5, 0.5, False, info, "recortar") == pytest.approx((0.5, 0.5))
    x, _ = gestos._to_reel(0.6, 0.5, False, info, "recortar")
    assert x > 0.6  # el recorte vertical amplía lo de los lados
    x2, _ = gestos._to_reel(0.6, 0.5, True, info, "recortar")
    assert x2 > x  # y el zoom aún más


def test_auto_effect_takes_the_number():
    words = W([("y", 0, .2), ("cuesta", .3, .6), ("noventa", .7, 1.0), ("90", 1.1, 1.3), ("euros", 1.4, 1.7)])
    clock = effects.WordClock(words, list(range(5)))
    g = hands.Gesture("senala", 0.6, 1.8, [(0.6, .5, .4), (1.8, .5, .4)], (1.0, 0.0))
    out = gestos.auto_effects([], [g], clock)
    assert out == [{"type": "aparece", "word": 1, "text": "90 euros", "until_word": 4, "auto": True}]


def test_hand_effects_build_with_and_without_hands():
    clock = effects.WordClock(TAKE, list(range(len(TAKE))))
    style = STYLES["impacto"]
    fxs = [{"type": "sube", "word": 6, "text": "+30%"}, {"type": "choque", "word": 11, "text": "Mito"},
           {"type": "aparece", "word": 16, "text": "Gratis"}]
    plain, _ = effects.build_effects(fxs, clock, style, 10)
    assert any("\\move(540,1460" in ln for ln in plain)  # sin manos, sube desde abajo
    frames = [{"t": 4.1 + k / 10, "hands": [hand(-0.03 * k)]} for k in range(12)]
    found = hands.gestures(frames)
    withh = [dict(f) for f in fxs]
    gestos.attach(withh, found, frames, clock)
    assert withh[0].get("_path")
    lines, wins = effects.build_effects(withh, clock, style, 10)
    assert sum("\\move(" in ln for ln in lines) > 5 and wins


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="necesita ffmpeg")
def test_render_with_hand_effects(tmp_path, monkeypatch):
    src = tmp_path / "toma.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=11",
                    "-f", "lavfi", "-i", "sine=frequency=220:duration=11", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", str(src)], check=True)
    monkeypatch.setattr(hands, "available", lambda: True)
    monkeypatch.setattr(hands, "track", lambda *a, **k: [{"t": 4.2 + k / 10, "hands": [hand(-0.03 * k)]} for k in range(12)])
    plan = EditPlan(effects=[{"type": "choque", "word": 16, "text": "Mito"}])
    cfg = {"provider": "none", "anthropic_key": "", "openai_key": "", "claude_model": "", "openai_model": ""}
    res = pipeline.run(src, tmp_path / "w", pipeline.EditOptions(rhythm="natural"), cfg, words=TAKE, plan=plan)
    kinds = [fx["type"] for fx in res.plan.effects]
    assert "choque" in kinds and "sube" in kinds  # el dedo que sube se ha convertido en efecto solo
    assert media.probe(res.video).duration > 3
    assert not any(k.startswith("_") for fx in res.plan.effects for k in fx)  # nada interno en el plan guardado
