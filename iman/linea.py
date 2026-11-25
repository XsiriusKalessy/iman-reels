"""Editor Pro: la línea de tiempo del reel (vídeo, apoyo, textos, subtítulos, música y sonidos).

Cada montaje deja en la carpeta del reel un `linea.json` con todo lo que sale y cuándo, en segundos del reel
terminado. La app lo pinta como pistas (estilo editor de vídeo) y lo que el creador mueve, alarga, escribe o
borra vuelve aquí como una lista de cambios (`apply`) que se aplican sobre el plan, las palabras y las opciones;
luego el reel se vuelve a montar con ellos. Nada pasa por la IA: lo que tocas a mano sale tal cual.
"""

from __future__ import annotations

import bisect

from . import effects
from .models import EditPlan, Word

# Pista de cada efecto en el editor. Lo que pone un vídeo o una foto encima va en «apoyo»; lo que recorta a la
# persona, en «fondo»; el resto son textos y gráficos.
BROLL = set(effects.VIDEO_KINDS) - {"congelado", "paso"}
BEHIND = set(effects.SEG_KINDS)
DEFAULT_LEN = 2.5
# Lo que se puede añadir desde el editor y con qué texto de ejemplo.
ADDABLE = {
    "frase": "Escribe aquí tu frase",
    "titular": "TITULAR",
    "palabra": "WOW",
    "cifra": "100%",
    "cta": "Escríbeme «INFO»",
    "dato": "Dato curioso",
    "detras": "TEXTO",
    "apoyo": "1",
    "pexels": "playa",
}
TEXT_MAX = 140


def _track(kind: str) -> str:
    if kind in BROLL:
        return "apoyo"
    if kind in BEHIND:
        return "fondo"
    return "textos"


def _length(kind: str) -> float:
    for table in (effects.VIDEO_KINDS, effects.SEG_KINDS):
        if kind in table:
            return table[kind][0]
    return DEFAULT_LEN


def window(fx: dict, clock: effects.WordClock, duration: float) -> tuple[float, float] | None:
    """Cuándo está en pantalla un efecto (en segundos del reel), igual que lo calculan los efectos al pintarse."""
    start = clock.at(effects.word_of(fx))
    if start is None:
        return None
    end = None
    if fx.get("until_word") is not None:
        try:
            end = clock.end_of(int(fx["until_word"]))
        except (TypeError, ValueError):
            end = None
    end = end if end and end > start + 0.3 else start + _length(str(fx.get("type")))
    nxt = fx.get("_next")
    if nxt is not None and nxt > start + 0.3:
        end = min(end, nxt - 0.05)
    return round(start, 3), round(min(duration, end), 3)


def _chunks(kept: list[Word], kept_idx: list[int], max_words: int = 4, gap: float = 0.35) -> list[dict]:
    out: list[dict] = []
    cur: list[tuple[int, Word]] = []
    for i, w in zip(kept_idx, kept):
        if cur and (len(cur) >= max_words or w.start - cur[-1][1].end > gap or cur[-1][1].text.rstrip()[-1:] in ".?!"):
            out.append(cur)
            cur = []
        cur.append((i, w))
    if cur:
        out.append(cur)
    return [{"t0": round(c[0][1].start, 3), "t1": round(c[-1][1].end, 3),
             "words": [{"i": i, "text": w.text} for i, w in c]} for c in out]


def build(*, plan: EditPlan, active: list[dict], kept: list[Word], kept_idx: list[int], spans, zoom,
          total: float, out_duration: float, music: str, music_on: bool, music_vol: int,
          sfx_events: list[tuple[float, str, float]], sfx_on: bool, hook: bool, clips: int) -> dict:
    """Todo lo que sale en el reel, por pistas, para el editor."""
    clock = effects.WordClock(kept, kept_idx)
    video, acc = [], 0.0
    for k, sp in enumerate(spans):
        video.append({"t0": round(acc, 3), "t1": round(acc + sp.duration, 3), "src0": round(sp.start, 3),
                      "src1": round(sp.end, 3), "zoom": bool(zoom[k]) if zoom and k < len(zoom) else False})
        acc += sp.duration
    blocks = []
    shown = {fx.get("_i") for fx in active}
    for fx in active:
        win = window(fx, clock, out_duration)
        if win is None or fx.get("_i") is None:
            continue
        kind = str(fx.get("type"))
        blocks.append({"i": fx["_i"], "type": kind, "track": _track(kind), "t0": win[0], "t1": win[1],
                       "text": str(fx.get("text", ""))[:TEXT_MAX], "pedido": bool(fx.get("pedido"))})
    # Los que el creador apagó o que no han cabido también se ven (en gris), para poder recuperarlos.
    for i, fx in enumerate(plan.effects):
        if i in shown:
            continue
        t = clock.at(effects.word_of(fx))
        if t is None:
            continue
        kind = str(fx.get("type"))
        blocks.append({"i": i, "type": kind, "track": _track(kind), "t0": round(t, 3),
                       "t1": round(min(out_duration, t + _length(kind)), 3), "text": str(fx.get("text", ""))[:TEXT_MAX],
                       "off": True, "pedido": bool(fx.get("pedido"))})
    blocks.sort(key=lambda b: (b["track"], b["t0"]))
    return {
        "version": 1,
        "total": round(total, 3),
        "duration": round(out_duration, 3),
        "hook": {"text": plan.hook_title if hook else "", "t0": 0.0, "t1": round(min(2.8, out_duration), 3)},
        "video": video,
        "blocks": blocks,
        "captions": _chunks(kept, kept_idx),
        "words": [[i, round(w.start, 3), round(w.end, 3)] for i, w in zip(kept_idx, kept)],
        "music": {"style": music or "", "on": bool(music_on), "volume": int(music_vol)},
        "sfx": {"on": bool(sfx_on), "events": [{"t": round(t, 3), "name": n} for t, n, _g in sfx_events]},
        "clips": clips,
        "addable": ADDABLE,
    }


class Clock:
    """De segundos del reel a palabras del vídeo original (lo contrario de effects.WordClock)."""

    def __init__(self, words: list[list]):
        self.rows = sorted((float(t0), float(t1), int(i)) for i, t0, t1 in words)
        self.starts = [r[0] for r in self.rows]

    def word_at(self, t: float) -> int | None:
        """La palabra que suena en `t` (o la siguiente que empieza)."""
        if not self.rows:
            return None
        k = bisect.bisect_right(self.starts, t + 1e-3) - 1
        if k >= 0 and self.rows[k][1] >= t - 0.05:
            return self.rows[k][2]
        k = max(0, min(len(self.rows) - 1, k + 1))
        return self.rows[k][2]

    def word_until(self, t: float) -> int | None:
        """La última palabra que acaba antes de `t`."""
        best = None
        for t0, t1, i in self.rows:
            if t1 <= t + 0.05:
                best = i
            else:
                break
        return best

    def words_in(self, a: float, b: float) -> list[int]:
        return [i for t0, t1, i in self.rows if t0 >= a - 0.05 and t1 <= b + 0.05]


def _num(v, default=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if f == f and abs(f) < 1e6 else default


def apply(plan: EditPlan, words: list[Word], line: dict, ops: list[dict], options: dict) -> list[str]:
    """Aplica los cambios del editor. Cambia `plan`, `words` (textos de los subtítulos) y `options` en el sitio y
    devuelve una frase por cambio hecho (lo que se le cuenta al creador)."""
    clock = Clock(line.get("words") or [])
    done: list[str] = []
    for op in ops[:200]:
        if not isinstance(op, dict):
            continue
        kind = op.get("op")
        i = op.get("i")
        fx = plan.effects[i] if isinstance(i, int) and 0 <= i < len(plan.effects) else None
        if kind == "move" and fx is not None:
            t = _num(op.get("t"))
            w = clock.word_at(t) if t is not None else None
            if w is None:
                continue
            old = effects.word_of(fx)
            delta = w - old
            fx["word"] = w
            items = fx.get("items")
            if isinstance(items, list):  # las listas se mueven enteras
                for it in items:
                    if isinstance(it, dict) and isinstance(it.get("at_word"), int):
                        it["at_word"] = max(0, it["at_word"] + delta)
            if isinstance(fx.get("until_word"), int):
                fx["until_word"] = max(w, fx["until_word"] + delta)
            fx["pedido"], fx["off"] = True, False
            done.append(f"Movido «{fx.get('type')}» al segundo {t:.1f}")
        elif kind == "resize" and fx is not None:
            end = _num(op.get("t1"))
            w = clock.word_until(end) if end is not None else None
            if w is None:
                continue
            fx["until_word"] = max(effects.word_of(fx), w)
            fx["pedido"] = True
            done.append(f"«{fx.get('type')}» dura ahora hasta el segundo {end:.1f}")
        elif kind == "text" and fx is not None:
            text = str(op.get("text", "")).strip()[:TEXT_MAX]
            if not text:
                continue
            fx["text"] = text
            fx["pedido"] = True
            done.append(f"Texto cambiado: «{text}»")
        elif kind == "delete" and fx is not None:
            fx["off"] = True
            done.append(f"Quitado «{fx.get('type')}»")
        elif kind == "restore" and fx is not None:
            fx["off"], fx["pedido"] = False, True
            done.append(f"Recuperado «{fx.get('type')}»")
        elif kind == "add":
            typ = str(op.get("type", ""))
            t = _num(op.get("t"))
            w = clock.word_at(t) if t is not None else None
            if typ not in ADDABLE or w is None:
                continue
            text = str(op.get("text") or ADDABLE[typ]).strip()[:TEXT_MAX]
            new = {"type": typ, "word": w, "text": text, "pedido": True, "until_word": None}
            t1 = _num(op.get("t1"))
            if t1 is not None and t1 > t + 0.3:
                new["until_word"] = clock.word_until(t1)
            plan.effects.append(new)
            done.append(f"Añadido «{typ}» en el segundo {t:.1f}")
        elif kind == "cut":
            a, b = _num(op.get("t0")), _num(op.get("t1"))
            idx = clock.words_in(a, b) if a is not None and b is not None and b > a else []
            if not idx:
                continue
            rng = (min(idx), max(idx))
            plan.restore = [(x, y) for x, y in plan.restore if y < rng[0] or x > rng[1]]
            plan.cut.append(rng)
            done.append(f"Cortado del segundo {a:.1f} al {b:.1f}")
        elif kind == "word":
            k = op.get("k")
            text = str(op.get("text", "")).strip()[:40]
            if isinstance(k, int) and 0 <= k < len(words) and text:
                words[k] = Word(text, words[k].start, words[k].end)
                done.append(f"Subtítulo corregido: «{text}»")
        elif kind == "hook":
            text = str(op.get("text", "")).strip()[:80]
            plan.hook_title = text
            options["hook_title"] = text
            options["hook"] = bool(text)
            done.append("Gancho cambiado" if text else "Gancho quitado")
        elif kind == "music":
            if "style" in op:
                options["music"] = str(op.get("style") or "")[:40]
            if "volume" in op:
                vol = _num(op.get("volume"), 100)
                options["volumen_musica"] = int(max(0, min(200, vol)))
            done.append("Música cambiada")
        elif kind == "sfx":
            if "on" in op:
                options["sfx"] = bool(op.get("on"))
            t = _num(op.get("t"))
            if t is not None:
                gone = list(options.get("sfx_fuera") or [])
                gone.append(round(t, 2))
                options["sfx_fuera"] = gone[-200:]
            done.append("Sonidos cambiados")
    return done


def drop_sfx(events: list[tuple[float, str, float]], gone: list) -> list[tuple[float, str, float]]:
    """Fuera los sonidos que el creador ha quitado en el editor (por su segundo en el reel)."""
    marks = [float(g) for g in gone or [] if isinstance(g, (int, float))]
    return [e for e in events if not any(abs(e[0] - g) < 0.06 for g in marks)]
