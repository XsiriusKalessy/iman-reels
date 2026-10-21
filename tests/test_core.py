from reelia import ai
from reelia.captions import STYLES, build_ass, group_words
from reelia.models import Word
from reelia.rhythm import RHYTHMS, TimeMap, detect_retakes, is_filler, keep_spans, remap_words


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
