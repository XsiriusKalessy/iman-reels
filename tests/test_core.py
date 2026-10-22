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
