import pytest

from iman import ai, effects
from iman.captions import STYLES, build_ass
from iman.models import EditPlan, Span
from iman.rhythm import RHYTHMS, keep_spans, remap_words

from .test_core import TAKE


def _clock():
    spans, drops = keep_spans(TAKE, 12.0, RHYTHMS["rapido"])
    kept, idx = remap_words(TAKE, spans, drops)
    return effects.WordClock(kept, idx), sum(s.duration for s in spans)


def test_wordclock_skips_dropped_words():
    clock, _ = _clock()
    # La palabra 0 está en la toma falsa: se usa la primera que sobrevive.
    assert clock.at(0) == clock.at(6)
    assert clock.at(99) is None


def test_lista_events_and_window():
    clock, dur = _clock()
    fx = {"type": "lista", "title": "Pasos", "items": [{"text": "Uno", "at_word": 6}, {"text": "Dos", "at_word": 11}], "until_word": 15}
    lines, win = effects.lista_events(fx, clock, STYLES["impacto"], dur)
    assert win and win.start < win.end <= dur
    assert any("Uno" in l for l in lines) and any("Dos" in l for l in lines)
    assert any("PASOS" in l for l in lines)


def test_palabra_uses_text_or_word():
    clock, dur = _clock()
    lines, win = effects.palabra_events({"type": "palabra", "word": 18, "text": ""}, clock, STYLES["impacto"], dur)
    assert win and any("GRATIS" in l for l in lines)


def test_captions_hidden_during_effects():
    clock, dur = _clock()
    lines, wins = effects.build_effects([{"type": "palabra", "word": 18, "text": "Gratis"}], clock, STYLES["impacto"], dur)
    ass = build_ass(clock.kept, STYLES["impacto"], dur, extra_events=lines, hide=wins)
    w = wins[0]
    for line in ass.splitlines():
        if line.startswith("Dialogue: 1,"):
            a, b = line.split(",")[1:3]
            to_s = lambda t: int(t.split(":")[0]) * 3600 + int(t.split(":")[1]) * 60 + float(t.split(":")[2])
            assert to_s(b) <= w.start + 0.011 or to_s(a) >= w.end - 0.011


def test_split_and_zoom_flags():
    spans = [Span(4.0, 7.1), Span(9.1, 10.1)]
    split = effects.split_spans(spans, TAKE, [(12, 15)])
    assert len(split) > len(spans)
    flags = effects.zoom_flags(split, TAKE, [(12, 15)], auto=False)
    assert any(flags) and not all(flags)
    auto = effects.zoom_flags(spans, TAKE, [], auto=True)
    assert auto == [False, True]


def test_plan_from_validates_effects():
    data = {
        "hook_title": "x", "hook_line": "", "drop": [], "emphasis": [],
        "effects": [
            {"type": "lista", "title": "", "items": [{"text": "a", "at_word": 1}, {"text": "b", "at_word": 99}], "until_word": -1, "word": -1, "text": ""},
            {"type": "lista", "title": "", "items": [{"text": "a", "at_word": 1}, {"text": "b", "at_word": 3}], "until_word": 5, "word": -1, "text": ""},
            {"type": "palabra", "title": "", "items": [], "until_word": -1, "word": 18, "text": "GRATIS"},
        ],
        "zooms": [{"from": 2, "to": 4}, {"from": 5, "to": 200}],
    }
    plan = ai._plan_from(data, len(TAKE), "claude")
    assert [f["type"] for f in plan.effects] == ["lista", "palabra"]
    assert plan.zooms == [(2, 4)]


def test_plan_roundtrip():
    p = EditPlan(hook_title="h", drop=[(1, 2)], zooms=[(3, 4)], effects=[{"type": "palabra", "word": 1}])
    assert EditPlan.from_dict(p.to_dict()) == p


NEW_EFFECTS = [
    {"type": "titular", "word": 6, "text": "No he editado ni", "subtitle": "un segundo", "look": "revista", "until_word": 12},
    {"type": "titular", "word": 6, "text": "¿Cuánto cuesta", "subtitle": "editar un reel?", "look": "mixto"},
    {"type": "cifra", "word": 6, "text": "90%", "subtitle": "de los creadores"},
    {"type": "frase", "word": 6, "text": "Y es gratis."},
    {"type": "frase", "word": 6, "text": "Imán está hecho para reels cortos", "look": "enfoque"},
    {"type": "tecleo", "word": 6, "title": "Le pido a Imán", "text": "Pon la palabra gigante"},
    {"type": "color", "word": 6, "text": "Rosa", "subtitle": "tu estilo", "look": "rosa"},
    {"type": "comentario", "word": 6, "text": "No me gusta tu estilo", "title": "lucia"},
    {"type": "contador", "word": 6, "text": "-"},
    {"type": "portada", "word": 6, "text": "Imán", "subtitle": "El vídeo entero, editado"},
    {"type": "cta", "word": 6, "text": "Editar", "subtitle": ""},
    {"type": "dato", "word": 6, "text": "12", "subtitle": "horas de vídeo"},
    {"type": "lista", "look": "checklist", "title": "Imán hace",
     "items": [{"text": "Corta", "at_word": 6}, {"text": "Limpia", "at_word": 11}], "until_word": 15},
    {"type": "lista", "look": "capitulos", "title": "",
     "items": [{"text": "Uno", "at_word": 6}, {"text": "Dos", "at_word": 11}], "until_word": 15},
    # Packs por sector
    {"type": "lista", "look": "itinerario", "title": "Italia en 3 días",
     "items": [{"text": "Roma", "at_word": 6}, {"text": "Día 2 · Florencia", "at_word": 11}], "until_word": 15},
    {"type": "ubicacion", "word": 6, "text": "Positano", "subtitle": "Costa Amalfitana"},
    {"type": "oferta", "word": 6, "text": "Japón en primavera", "subtitle": "desde 1.890 €", "title": "10 noches · vuelo + hotel"},
    {"type": "ruta", "word": 6, "text": "Madrid", "subtitle": "Tokio", "title": "14 h de vuelo"},
    {"type": "testimonio", "word": 6, "text": "En dos semanas ya tenía mis primeros clientes", "subtitle": "Laura, alumna"},
    {"type": "plazas", "word": 6, "text": "Solo 7 plazas"},
    {"type": "precio", "word": 6, "text": "39 €", "subtitle": "59 €", "title": "-30%"},
]


@pytest.mark.parametrize("fx", NEW_EFFECTS, ids=lambda f: f["type"] + ":" + f.get("look", ""))
def test_every_effect_draws_inside_the_reel(fx):
    clock, dur = _clock()
    lines, wins = effects.build_effects([fx], clock, STYLES["palabra"], dur, source_duration=12.0)
    assert lines and all(l.startswith("Dialogue: ") for l in lines)
    for w in wins:
        assert 0 <= w.start < w.end <= dur + 1e-6


def test_effects_never_overlap_the_next_one():
    clock, dur = _clock()
    fx = [{"type": "cifra", "word": 6, "text": "90"}, {"type": "color", "word": 11, "text": "Ya", "look": "negro"}]
    _, wins = effects.build_effects(fx, clock, STYLES["impacto"], dur)
    assert wins[0].end <= wins[1].start


def test_contador_counts_from_raw_to_final():
    clock, dur = _clock()
    lines, _ = effects.build_effects([{"type": "contador", "word": 6, "text": "-"}], clock, STYLES["impacto"], dur,
                                     source_duration=80)
    text = "\n".join(lines)
    assert "1:20" in text and effects._mmss(dur) in text


def test_plan_accepts_new_types_and_fixes_bad_looks():
    data = {
        "hook_title": "x", "hook_line": "", "drop": [], "emphasis": [], "zooms": [],
        "effects": [
            {"type": "titular", "title": "", "items": [], "until_word": 3, "word": 1, "text": "Hola", "subtitle": "", "look": "rosa"},
            {"type": "color", "title": "", "items": [], "until_word": -1, "word": 2, "text": "Ya", "subtitle": "", "look": "nada"},
            {"type": "cta", "title": "", "items": [], "until_word": -1, "word": 99, "text": "Editar", "subtitle": "", "look": ""},
            {"type": "frase", "title": "", "items": [], "until_word": -1, "word": 4, "text": "  ", "subtitle": "", "look": ""},
        ],
    }
    plan = ai._plan_from(data, len(TAKE), "claude")
    assert [(f["type"], f["look"]) for f in plan.effects] == [("titular", "revista"), ("color", "rosa")]


def test_caja_style_puts_captions_in_a_box():
    clock, dur = _clock()
    ass = build_ass(clock.kept, STYLES["caja"], dur)
    assert "Style: Box," in ass and ",Box,," in ass


def test_video_effects_become_ffmpeg_overlays():
    from iman import media

    clock, dur = _clock()
    fx = [{"type": "bruto", "word": 6, "text": "-", "until_word": 10}, {"type": "fantasma", "word": 11, "text": "-"},
          {"type": "pagina", "word": 15, "text": "toma revista."}, {"type": "palabra", "word": 18, "text": "x"}]
    ops = effects.video_ops(fx, clock, dur, src_of=lambda t: t + 4.0)
    assert [o.kind for o in ops] == ["bruto", "fantasma", "pagina"]
    assert ops[0].src_start > 0 and all(0 <= o.start < o.end <= dur for o in ops)
    info = media.MediaInfo(width=1280, height=720, duration=12.0, fps=30.0, has_audio=True, hdr=False)
    graph = media.build_filtergraph([Span(0, 5)], info, None, overlays=ops)
    assert "rotate=" in graph and "colorchannelmixer=aa=" in graph and "color=c=0xF4ECDF" in graph


def test_segmentation_effects_are_split_out():
    clock, dur = _clock()
    fx = [{"type": "detras", "word": 6, "text": "Imán", "subtitle": "hoy", "look": "rosa", "until_word": 10},
          {"type": "fondo", "word": 11, "text": "-", "look": "amarillo"}, {"type": "desenfoque", "word": 15, "text": "-"}]
    ops = effects.seg_ops(fx, clock, dur)
    assert [(o.kind, o.color) for o in ops] == [("detras", "#FF4F7B"), ("fondo", "#F5D90A"), ("desenfoque", "#123A35")]
    behind = effects.behind_events(fx, clock, STYLES["impacto"], dur)
    assert len(behind) == 2 and "IMÁN" in behind[0]
    # Nada de esto se pinta en la capa de delante.
    assert effects.build_effects(fx, clock, STYLES["impacto"], dur) == ([], [])


def test_packs_reach_the_ai_and_validate():
    from iman import packs

    assert packs.get("nada").key == "general" and packs.get("viajes").guide
    data = {"hook_title": "x", "hook_line": "", "drop": [], "emphasis": [], "zooms": [], "effects": [
        {"type": "lista", "title": "", "items": [{"text": "Roma", "at_word": 1}, {"text": "Florencia", "at_word": 3}],
         "until_word": 5, "word": -1, "text": "", "subtitle": "", "look": "itinerario"},
        {"type": "oferta", "title": "7 noches", "items": [], "until_word": -1, "word": 2, "text": "Roma",
         "subtitle": "899 €", "look": ""},
    ]}
    plan = ai._plan_from(data, 10, "claude")
    assert plan.effects[0]["look"] == "itinerario" and plan.effects[1]["subtitle"] == "899 €"

    seen = {}
    def fake(cfg, system, user, schema):
        seen["user"] = user
        return {**data, "effects": []}
    import pytest as _p
    mp = _p.MonkeyPatch()
    mp.setattr(ai, "_ask_json", fake)
    try:
        ai.plan_edit(ai.AIConfig(provider="claude", anthropic_key="k"), TAKE, pack="viajes")
    finally:
        mp.undo()
    assert "PACK VIAJES" in seen["user"]
