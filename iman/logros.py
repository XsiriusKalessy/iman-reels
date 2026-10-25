"""Logros y racha: lo que llevas hecho con Imán, para que publicar sea un hábito y no un esfuerzo.

Todo sale de tu biblioteca (ningún dato se manda a ningún sitio): reels hechos, semanas seguidas publicando,
minutos de vídeo que Imán te ha quitado de encima, reels con nota de viralidad alta y resultados anotados.
"""
from __future__ import annotations

import datetime as dt

LOGROS = [
    ("primero", "Primer reel", "Tu primer reel con Imán.", lambda s: s["total"] >= 1),
    ("cinco", "5 reels", "Ya le has cogido el truco.", lambda s: s["total"] >= 5),
    ("veinte", "20 reels", "Esto ya es constancia.", lambda s: s["total"] >= 20),
    ("cincuenta", "50 reels", "Medio centenar. Pocos llegan.", lambda s: s["total"] >= 50),
    ("racha3", "3 semanas seguidas", "Un reel cada semana, tres semanas.", lambda s: s["racha_semanas"] >= 3),
    ("racha8", "8 semanas seguidas", "Dos meses sin fallar una semana.", lambda s: s["racha_semanas"] >= 8),
    ("hora", "1 hora quitada", "Una hora de silencios y tomas falsas que no has tenido que cortar tú.",
     lambda s: s["segundos_ahorrados"] >= 3600),
    ("viral", "Nota alta", "Un reel con nota de viralidad de 85 o más.", lambda s: s["mejor_nota"] >= 85),
    ("datos", "Aprendiendo", "3 reels con resultados anotados: Imán ya aprende de ti.", lambda s: s["anotados"] >= 3),
    ("tres_dia", "3 en un día", "Tres reels en un mismo día: un día de grabación bien aprovechado.", lambda s: s["max_dia"] >= 3),
]


def _week(d: dt.date) -> tuple[int, int]:
    y, w, _ = d.isocalendar()
    return (y, w)


def _prev_week(yw: tuple[int, int]) -> tuple[int, int]:
    d = dt.date.fromisocalendar(yw[0], yw[1], 1) - dt.timedelta(days=7)
    return _week(d)


def compute(jobs: list[dict], today: dt.date | None = None) -> dict:
    """`jobs`: reels hechos [{created, result:{duration_in, duration_out, viral}, resultados}]."""
    today = today or dt.date.today()
    days = sorted({dt.date.fromtimestamp(float(j.get("created", 0))) for j in jobs if j.get("created")})
    per_day: dict[dt.date, int] = {}
    for j in jobs:
        if j.get("created"):
            d = dt.date.fromtimestamp(float(j["created"]))
            per_day[d] = per_day.get(d, 0) + 1
    weeks = {_week(d) for d in days}
    # Racha de semanas: esta semana cuenta si ya hay reel; si no, se mira desde la anterior.
    racha, w = 0, _week(today)
    if w not in weeks:
        w = _prev_week(w)
    while w in weeks:
        racha += 1
        w = _prev_week(w)
    saved = sum(max(0.0, float((j.get("result") or {}).get("duration_in", 0)) - float((j.get("result") or {}).get("duration_out", 0)))
                for j in jobs)
    stats = {
        "total": len(jobs),
        "semana": sum(n for d, n in per_day.items() if _week(d) == _week(today)),
        "racha_semanas": racha,
        "segundos_ahorrados": int(saved),
        "mejor_nota": max([int(((j.get("result") or {}).get("viral") or {}).get("score", 0)) for j in jobs] or [0]),
        "anotados": sum(1 for j in jobs if j.get("resultados")),
        "max_dia": max(per_day.values()) if per_day else 0,
        "ultimo": days[-1].isoformat() if days else "",
    }
    done = [{"key": k, "label": lab, "hint": hint, "done": bool(f(stats))} for k, lab, hint, f in LOGROS]
    nxt = next((l for l in done if not l["done"]), None)
    stats["logros"] = done
    stats["siguiente"] = f"Siguiente: {nxt['label']} ({nxt['hint']})" if nxt else "Los tienes todos."
    stats["semana_actual"] = _week(today) in weeks
    return stats
