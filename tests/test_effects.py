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
