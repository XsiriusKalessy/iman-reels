"""Nota de viralidad: de 0 a 100, antes de publicar, con lo que más conviene cambiar.

No adivina las visitas (nadie puede): mide lo que sí se sabe que retiene en reels (gancho inmediato, empezar
a hablar enseguida, duración, ritmo de palabra, algo nuevo en pantalla cada pocos segundos, subtítulos,
música, llamada a la acción) y lo convierte en una nota y en tres consejos concretos.
"""
from __future__ import annotations

from .models import EditPlan, Word


def _item(key: str, got: float, top: float, text: str, tip: str) -> dict:
    return {"key": key, "points": round(got, 1), "max": top, "text": text, "tip": tip}


def score(plan: EditPlan, kept: list[Word], total: float, active: list[dict], *, captions: bool = True,
          music: bool = True, hook: bool = True, cta: bool = False) -> dict:
    """`kept`: palabras que quedan en el reel; `active`: efectos que salen; `total`: duración final."""
    items: list[dict] = []
    # 1. Gancho: título corto en pantalla y, mejor aún, un gancho visual que no sea el básico.
    title = (plan.hook_title or "").strip()
    n_title = len(title.split())
    pts = 0.0
    if hook and title:
        pts = 10 if n_title <= 7 else 6
        if plan.gancho and plan.gancho != "titulo":
            pts += 5
    items.append(_item("gancho", pts, 15, "Gancho en pantalla desde el primer segundo",
                       "Escribe un gancho de 7 palabras o menos y prueba otro gancho visual (zoom seco, congelado…)."
                       if pts < 15 else ""))
    # 2. Empiezas a hablar enseguida.
    first = kept[0].start if kept else 9.9
    pts = 10 if first < 0.6 else 6 if first < 1.2 else 0
    items.append(_item("arranque", pts, 10, "Empiezas a hablar enseguida",
                       f"Tardas {first:.1f} s en decir la primera palabra: usa el ritmo «Más rápido» o el gancho «mano»."
                       if pts < 10 else ""))
    # 3. Duración.
    if 15 <= total <= 45:
        pts = 15
    elif 7 <= total < 15 or 45 < total <= 60:
        pts = 10
    elif 60 < total <= 90:
        pts = 5
    else:
        pts = 2
    items.append(_item("duracion", pts, 15, f"Duración ({total:.0f} s)",
                       ("Entre 15 y 45 s se ve entero más veces: quita frases en «Revisa lo que dices»." if total > 45
                        else "Es muy corto: cuenta algo más para que haya tiempo de engancharse.") if pts < 15 else ""))
    # 4. Ritmo de palabra: 140-190 palabras por minuto se sigue sin cansar.
    wpm = len(kept) / total * 60 if total > 0 else 0
    pts = 10 if 140 <= wpm <= 190 else 6 if 110 <= wpm < 140 or 190 < wpm <= 220 else 2
    items.append(_item("ritmo", pts, 10, f"Ritmo de palabra ({wpm:.0f} por minuto)",
                       ("Hablas despacio: el ritmo «Más rápido» quita los huecos." if wpm < 140
                        else "Vas muy rápido: pide «respira» en «Dímelo como a tu editor».") if pts < 10 else ""))
    # 5. Algo nuevo en pantalla cada 5-8 s.
    n_fx = len(active)
    ideal = max(2, round(total / 6.5))
    pts = 15 if n_fx >= ideal else 9 if n_fx >= ideal * 0.6 else 3 if n_fx else 0
    items.append(_item("efectos", pts, 15, f"Algo cambia en pantalla a menudo ({n_fx} efectos)",
                       f"Faltan cambios: con {total:.0f} s conviene tener unos {ideal}. Pide «más efectos» en el chat."
                       if pts < 15 else ""))
    # 6. Subtítulos.
    items.append(_item("subtitulos", 10 if captions else 0, 10, "Subtítulos (la mayoría lo ve sin sonido)",
                       "" if captions else "Activa los subtítulos."))
    # 7. Música y silencio dramático.
    pts = (5 if music else 0) + (3 if plan.silence else 0)
    items.append(_item("sonido", pts, 8, "Música de fondo y un silencio dramático",
                       ("Pon música de fondo." if not music else "Marca una frase clave como silencio dramático en el chat.")
                       if pts < 8 else ""))
    # 8. Llamada a la acción.
    items.append(_item("cta", 10 if cta else 0, 10, "Llamada a la acción al final",
                       "" if cta else "Pide una sola cosa al final (comenta X, sígueme, reserva) o activa el cierre en «Mi marca»."))
    # 9. Palabras clave destacadas.
    n_emp = len(plan.emphasis or [])
    pts = 7 if n_emp >= 3 else 3 if n_emp else 0
    items.append(_item("enfasis", pts, 7, "Palabras clave destacadas en los subtítulos",
                       "Destaca 3 o más palabras clave (cifras, nombres) para que se lean de un vistazo." if pts < 7 else ""))
    value = int(round(sum(i["points"] for i in items)))
    value = max(0, min(100, value))
    tips = [i["tip"] for i in sorted(items, key=lambda i: i["max"] - i["points"], reverse=True)
            if i["tip"] and i["max"] - i["points"] >= 3][:3]
    if value >= 85:
        label = "Muy alta"
    elif value >= 70:
        label = "Alta"
    elif value >= 50:
        label = "Media"
    else:
        label = "Baja"
    return {"score": value, "label": label, "items": items, "tips": tips}
