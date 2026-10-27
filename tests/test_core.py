import pytest
from iman import ai
from iman.captions import STYLES, build_ass, group_words
from iman.models import Word
from iman.rhythm import RHYTHMS, TimeMap, detect_retakes, is_filler, keep_spans, remap_words


def W(spec):
    return [Word(t, s, e) for t, s, e in spec]


TAKE = W([
    ("Hoy", 0.2, 0.5), ("te", 0.55, 0.7), ("cuento", 0.75, 1.1), ("el", 1.15, 1.25), ("error", 1.3, 1.7),
    ("eh", 2.2, 2.6),
    ("Hoy", 4.1, 4.35), ("te", 4.4, 4.5), ("cuento", 4.55, 4.9), ("el", 4.95, 5.05), ("error", 5.1, 5.5),
    ("que", 5.55, 5.7), ("comete", 5.75, 6.1), ("todo", 6.15, 6.4), ("el", 6.45, 6.55), ("mundo.", 6.6, 7.0),
    ("Y", 9.2, 9.3), ("es", 9.35, 9.5), ("gratis.", 9.55, 10.0),
])


def test_retake_drops_first_attempt():
    assert detect_retakes(TAKE) == [(0, 5)]


def test_take_retakes_keep_the_last_take():
    from iman.rhythm import detect_take_retakes, take_ranges

    # Dos archivos: el primero es un intento fallido de lo mismo (con una palabra distinta), el segundo es el bueno.
    words = W([("Hoy", 0.2, 0.5), ("te", 0.55, 0.7), ("cuento", 0.75, 1.1), ("el", 1.15, 1.25), ("error", 1.3, 1.7),
               ("tipico", 1.8, 2.2), ("de", 2.3, 2.4), ("Japon", 2.5, 3.0),
               ("Hoy", 5.1, 5.35), ("te", 5.4, 5.5), ("cuento", 5.55, 5.9), ("el", 5.95, 6.05), ("error", 6.1, 6.5),
               ("tipico", 6.6, 7.0), ("de", 7.1, 7.2), ("Japon.", 7.3, 7.8), ("Y", 8.2, 8.3), ("es", 8.35, 8.5), ("gratis.", 8.55, 9.0)])
    tomas = [{"nombre": "a", "inicio": 0, "fin": 5}, {"nombre": "b", "inicio": 5, "fin": 10}]
    takes = take_ranges(words, tomas)
    assert takes == [(0, 7), (8, 18)]
    assert detect_take_retakes(words, takes) == [(0, 7)]
    # Tomas con contenido distinto no se tocan.
    other = W([("Primero", 0.2, 0.5), ("vamos", 0.6, 0.9), ("a", 1.0, 1.1), ("Tokio", 1.2, 1.6), ("hoy", 1.7, 2.0),
               ("Luego", 5.1, 5.4), ("vamos", 5.5, 5.8), ("a", 5.9, 6.0), ("Kioto", 6.1, 6.5), ("manana", 6.6, 7.0)])
    assert detect_take_retakes(other, take_ranges(other, tomas)) == []
    # La IA puede quitar una toma entera aunque sea más de la mitad del vídeo, pero no todo el vídeo.
    from iman import ai
    plan = ai._plan_from({"drop": [{"from": 0, "to": 11}]}, 19, "claude", takes=[(0, 11), (12, 18)])
    assert plan.drop == [(0, 11)]
    assert ai._plan_from({"drop": [{"from": 0, "to": 11}]}, 19, "claude").drop == []
    assert ai._plan_from({"drop": [{"from": 0, "to": 18}]}, 19, "claude", takes=[(0, 18)]).drop == []


def test_fillers():
    assert is_filler(TAKE, 5)
    assert not is_filler(TAKE, 0)
    ws = W([("y", 0, 0.2), ("este", 0.25, 0.5), ("coche", 0.55, 0.9)])
    assert not is_filler(ws, 1)  # "este" dentro de una frase no es muletilla


def test_rapido_cuts_silence_and_retake():
    spans, drops = keep_spans(TAKE, 12.0, RHYTHMS["rapido"])
    assert drops == set(range(0, 6))
    assert len(spans) == 2
    assert spans[0].start >= 2.6  # nada de la toma falsa
    total = sum(s.duration for s in spans)
    assert 3.5 < total < 5.0


def test_sin_tocar_keeps_everything():
    spans, drops = keep_spans(TAKE, 12.0, RHYTHMS["sin_tocar"])
    assert drops == set() and len(spans) == 1 and spans[0].duration == 12.0


def test_natural_keeps_short_pauses():
    spans, _ = keep_spans(TAKE, 12.0, RHYTHMS["natural"])
    rapido, _ = keep_spans(TAKE, 12.0, RHYTHMS["rapido"])
    assert sum(s.duration for s in spans) >= sum(s.duration for s in rapido)


def test_extra_drops_from_ai():
    spans, drops = keep_spans(TAKE, 12.0, RHYTHMS["rapido"], [(16, 18)])
    assert {16, 17, 18} <= drops
    assert spans[-1].end < 9.2


def test_timemap_is_monotonic_and_inside_output():
    spans, drops = keep_spans(TAKE, 12.0, RHYTHMS["rapido"])
    kept, idx = remap_words(TAKE, spans, drops)
    tm = TimeMap(spans)
    assert [TAKE[i].text for i in idx] == [w.text for w in kept]
    starts = [w.start for w in kept]
    assert starts == sorted(starts)
    assert all(0 <= w.start <= w.end <= tm.total + 1e-6 for w in kept)


def test_group_words_respects_limits():
    groups = group_words(TAKE, 3, 16)
    assert all(len(g) <= 3 for g in groups)
    assert sum(len(g) for g in groups) == len(TAKE)


def test_ass_has_hook_and_subs():
    ass = build_ass(TAKE[6:], STYLES["impacto"], 11.0, hook_title="El error de todos", emphasis={2})
    assert "Style: Hook" in ass
    assert "EL ERROR DE TODOS" in ass
    assert ass.count("Dialogue: 1,") == len(TAKE[6:])


def test_plan_edit_validates_indices(monkeypatch):
    monkeypatch.setattr(ai, "_ask_json", lambda *a: {
        "hook_title": "El error de todos", "hook_line": "¿Sabes qué error comete todo el mundo?",
        "drop": [{"from": 0, "to": 5, "reason": "toma falsa"}, {"from": 50, "to": 60, "reason": "fuera"},
                 {"from": 0, "to": 18, "reason": "borra todo"}],
        "emphasis": [13, 99],
    })
    cfg = ai.AIConfig(provider="claude", anthropic_key="x")
    plan = ai.plan_edit(cfg, TAKE)
    assert plan.drop == [(0, 5)]
    assert plan.emphasis == [13]
    assert plan.hook_title == "El error de todos"


def test_transcript_for_prompt_marks_pauses():
    txt = ai.transcript_for_prompt(TAKE)
    assert "[0] Hoy" in txt and "(pausa 1.5s)" in txt


def test_fallback_hook_stops_at_sentence():
    assert ai.fallback_hook(TAKE[6:], 12) == "Hoy te cuento el error que comete todo el mundo"


def test_restore_beats_automatic_cuts_and_cut_removes_good_takes():
    _, drops = keep_spans(TAKE, 12.0, RHYTHMS["rapido"])
    assert 0 in drops
    _, drops = keep_spans(TAKE, 12.0, RHYTHMS["rapido"], restore=[(0, 4)])
    assert not drops & set(range(0, 5))
    _, drops = keep_spans(TAKE, 12.0, RHYTHMS["rapido"], [(16, 18)])
    assert {16, 17, 18} <= drops


def test_meaningful_pause_is_kept_but_capped():
    words = W([("¿Sabes", 0.0, 0.4), ("qué?", 0.45, 0.8), ("Nada.", 1.5, 1.9), ("Fin", 4.0, 4.3)])
    spans, _ = keep_spans(words, 5.0, RHYTHMS["rapido"])
    assert spans[0].end >= 1.5  # la pausa tras la pregunta se queda
    words2 = W([("Dato", 0.0, 0.4), ("importante", 0.45, 0.8), ("Nada", 1.5, 1.9)])
    spans2, _ = keep_spans(words2, 3.0, RHYTHMS["rapido"])
    assert spans2[0].end < 1.0  # sin motivo, el silencio se corta
    spans3, _ = keep_spans(words2, 3.0, RHYTHMS["rapido"], pauses=[1])  # la IA marca la pausa
    assert spans3[0].end >= 1.5
    long = W([("¿Listo?", 0.0, 0.5), ("Vamos", 3.0, 3.4)])
    spans4, _ = keep_spans(long, 4.0, RHYTHMS["rapido"])
    assert len(spans4) == 2 and 0.9 <= spans4[0].end <= 1.2  # una pausa larga se queda en ~0,6 s


def test_review_lists_phrases_with_reasons():
    from iman.models import EditPlan
    from iman.pipeline import review

    rows = review(TAKE, EditPlan(), "rapido")
    assert rows[0]["state"] == "fuera" and rows[0]["reason"] == "Frase repetida"
    assert any(r["state"] == "dentro" and "mundo" in r["text"] for r in rows)
    rows = review(TAKE, EditPlan(cut=[(16, 18)]), "rapido")
    last = rows[-1]
    assert last["state"] == "fuera" and last["reason"] == "La quitaste tú"


def test_switches_and_removals_survive_rerenders():
    """Lo que el creador apaga o pide quitar no vuelve: ni al volver a montar ni tras un cambio por chat."""
    from iman import effects, ganchos, server
    from iman.models import EditPlan

    # El interruptor del efecto de arranque («Detrás de ti») sigue apagado al volver a montar con el mismo gancho.
    plan = EditPlan(hook_title="3 errores en Japón", effects=[
        {"type": "detras", "word": 0, "text": "JAPÓN", "_gancho": True, "off": True},
        {"type": "lista", "word": 6, "items": [{"at_word": 6, "text": "a"}, {"at_word": 8, "text": "b"}]}])
    ganchos.apply(plan, "detras", has_person=True)
    assert plan.effects[0]["type"] == "detras" and plan.effects[0]["off"] is True
    # Tras un chat, la IA devuelve los efectos sin los interruptores: se recuperan, y «quita los textos de
    # detrás» se cumple aunque la IA los haya dejado; el gancho pasa a «titulo» para que no vuelvan.
    old = EditPlan(effects=[{"type": "detras", "word": 0, "text": "JAPÓN", "_gancho": True},
                            {"type": "etiqueta", "word": 10, "text": "Kioto", "off": True}])
    new = EditPlan(gancho="detras", effects=[{"type": "detras", "word": 0, "text": "JAPÓN"},
                                             {"type": "detras", "word": 12, "text": "GERO"},
                                             {"type": "etiqueta", "word": 10, "text": "Kioto"}])
    assert server._carry_switches(old, new, "quita los textos de detrás mía") is True
    assert [fx["type"] for fx in new.effects] == ["etiqueta"] and new.effects[0]["off"] is True
    assert new.gancho == "titulo"
    # Sin petición de quitar, los efectos se quedan y el arranque sigue.
    new2 = EditPlan(gancho="detras", effects=[{"type": "detras", "word": 0, "text": "JAPÓN"}])
    assert server._carry_switches(old, new2, "el titular más corto") is False
    # Nunca dos efectos a la vez: los que empiezan en el mismo momento se quedan en uno.
    words = W([(f"w{i}", i * 0.5, i * 0.5 + 0.4) for i in range(20)])
    clock = effects.WordClock(words, list(range(20)))
    many = [{"type": "etiqueta", "word": 4, "text": "a"}, {"type": "etiqueta", "word": 4, "text": "b"},
            {"type": "titular", "word": 5, "text": "c"}, {"type": "objeto", "word": 5, "text": "d"},
            {"type": "cifra", "word": 12, "text": "e"}]
    kept = effects.dedupe_overlaps(many, clock)
    assert [fx["text"] for fx in kept] == ["a", "d", "e"]


def test_effects_never_pile_up_and_lists_avoid_the_face():
    """Un efecto que empieza mientras una lista sigue en pantalla se salta; la lista se pone lejos de la cara;
    el círculo con el creador solo si se pide."""
    from iman import effects
    from iman.captions import STYLES

    words = W([(f"w{i}", i * 0.5, i * 0.5 + 0.4) for i in range(40)])
    clock = effects.WordClock(words, list(range(40)))
    lista = {"type": "lista", "word": 2, "title": "2 tipos", "until_word": 20,
             "items": [{"at_word": 2, "text": "Con eSIM"}, {"at_word": 10, "text": "Sin wifi"}]}
    frase = {"type": "frase", "word": 8, "text": "Sin internet, nada"}
    later = {"type": "titular", "word": 30, "text": "Luego"}
    lines, wins = effects.build_effects([lista, frase, later], clock, STYLES["impacto"], 20.0)
    text = "\n".join(lines)
    assert "Con eSIM" in text and "Luego" in text and "nada" not in text
    assert wins[0].start < 2 and wins[0].end > 10  # la ventana es la de la lista
    # Cara arriba → lista abajo; cara abajo → lista arriba.
    low, _ = effects.lista_events({**lista, "_face_y": 0.3}, clock, STYLES["impacto"], 20.0)
    high, _ = effects.lista_events({**lista, "_face_y": 0.7}, clock, STYLES["impacto"], 20.0)
    ys = lambda ev: [int(l.split("\\pos(250,")[1].split(")")[0]) for l in ev if "\\pos(250," in l]  # noqa: E731
    assert min(ys(low)) > 900 and max(ys(low)) < 1250
    assert max(ys(high)) < 900
    # Círculo con el creador: solo si se pide.
    tarj = {"type": "tarjetas", "word": 2, "text": "✈️ Vuelos|🏨 Hoteles|🚄 Trenes", "title": "Todo incluido", "until_word": 12}
    ops = effects.video_ops([tarj], clock, 20.0, accent="&H00FFD200")
    assert ops and ops[0].face == ""
    ops = effects.video_ops([tarj], clock, 20.0, accent="&H00FFD200", face=True)
    assert ops[0].face == "abajo"


def test_words_do_not_stretch_into_silence():
    from iman.rhythm import clip_to_silence
    words = W([("Hola", 0.2, 0.5), ("mundo", 0.6, 3.4), ("eh", 4.0, 4.2), ("sigo", 6.0, 6.3)])
    out = clip_to_silence(words, [(1.0, 5.0)])
    assert [w.text for w in out] == ["Hola", "mundo", "sigo"]  # «eh» cae entero dentro del silencio
    assert out[1].end == pytest.approx(1.05)  # «mundo» acaba donde empieza el silencio medido
    assert out[0] is words[0] and out[2] is words[3]  # lo demás no se toca
    assert clip_to_silence(words, []) == words


def test_escena_is_a_known_hook():
    from iman import ganchos
    assert "escena" in ai.GANCHO_KEYS and "escena" in ganchos.GANCHOS
    assert "escena" in ganchos.alternatives("titulo", n=20)
    shifted = [Word(w.text, w.start + 3.0, w.end + 3.0) for w in TAKE]
    assert ai.transcript_for_prompt(shifted).startswith("(empieza con 3s sin hablar")
    assert not ai.transcript_for_prompt(TAKE).startswith("(empieza")
