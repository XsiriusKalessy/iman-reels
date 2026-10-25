"""Ganchos visuales: qué pasa en pantalla en los primeros 3 segundos.

El texto del gancho (plan.hook_title) es el "qué"; el gancho visual es el "cómo": zoom seco, congelado con
el título, palabra detrás de la persona, cifra gigante, aviso de "comenta X"… Siempre con el vídeo real del
creador. Cada gancho sabe qué efecto pone al principio, qué entrada de cámara usa y qué conviene grabar
("graba esto al principio") para que luzca.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import EditPlan


@dataclass(frozen=True)
class Gancho:
    key: str
    label: str
    description: str  # lo que ve quien lo mira
    record: str = ""  # «graba esto al principio» (vacío: vale cualquier toma)
    effect: str = ""  # efecto que se pone en la primera palabra ("" = solo el título)
    look: str = ""
    punch: str = "suave"  # entrada de cámara: suave | seco | "" (ninguna)
    title: bool = True  # el título grande se queda en pantalla
    prefix: str = ""  # se antepone al título ("POV: ")
    needs: str = ""  # "" | persona (hay que recortar a alguien) | manos
    packs: tuple[str, ...] = field(default_factory=tuple)  # sectores donde brilla más (vacío: todos)


GANCHOS: dict[str, Gancho] = {g.key: g for g in [
    Gancho("titulo", "Título y zoom",
           "El título grande entra con un pequeño zoom y un golpe de sonido. Vale para todo.",
           "Empieza hablando ya: nada de «hola» ni de presentarte."),
    Gancho("zoom_seco", "Zoom seco",
           "La cámara entra de golpe a tu cara con el título: imposible pasar de largo.",
           "Mira a cámara desde el primer fotograma y di la frase fuerte de entrada.", punch="seco"),
    Gancho("congelado", "Congelado con título",
           "El primer fotograma se queda quieto medio segundo con el título encima y arranca de golpe.",
           "Haz un gesto grande al empezar (señalar, levantar algo, taparte la boca): el congelado lo clava.",
           effect="congelado", punch=""),
    Gancho("detras", "Palabra detrás de ti",
           "La palabra clave aparece gigante detrás de tu cuerpo, como un cartel.",
           "Grábate de medio cuerpo, con aire por encima de la cabeza y sin moverte de sitio los 2 primeros segundos.",
           effect="detras", punch="", title=False, needs="persona"),
    Gancho("numero", "Cifra gigante",
           "Un número que impresiona ocupa la pantalla dos segundos («3», «2.000 €», «x10»).",
           "Que lo primero que digas sea la cifra: «Tres errores…», «Dos mil euros…».",
           effect="cifra", punch="suave", title=False),
    Gancho("pov", "POV",
           "El título va en modo «POV: …», como si quien mira estuviera viviéndolo.",
           "Graba en primera persona o desde tu punto de vista, mostrando lo que ves.", prefix="POV: "),
    Gancho("aviso", "Aviso de «comenta»",
           "Sale un aviso tipo notificación con la palabra que hay que comentar para recibir algo.",
           "Sostén la mano abierta a la altura de la cara: el aviso cae ahí.", effect="notificaciones", punch="suave"),
    Gancho("mano", "Mano que tapa la cámara",
           "Empiezas con la mano tapando el objetivo; al quitarla, el reel arranca con un latigazo.",
           "Tapa el objetivo con la mano, destápala y empieza a hablar. Imán quita el tramo tapado.",
           punch="seco", needs="manos"),
    Gancho("entrada", "Entras en cuadro",
           "La cámara ya graba y tú entras en plano andando o asomándote: el movimiento engancha.",
           "Deja la cámara fija grabando y entra en plano desde un lado; empieza a hablar nada más llegar.",
           punch="seco"),
    Gancho("objeto", "Objeto a cámara",
           "Acercas algo a la cámara (un billete, el móvil, un pasaporte) y el título entra con él.",
           "Lleva el objeto hacia el objetivo en el primer segundo y luego sepáralo; habla mientras.",
           punch="seco", packs=("viajes", "productos", "viajero")),
    Gancho("color", "Golpe de color",
           "Un flash de tu color de marca con la frase clave, y de ahí a tu cara.",
           "", effect="color", look="amarillo", punch="suave", title=False),
    Gancho("comentario", "Respondiendo a un comentario",
           "El comentario de un seguidor aparece en una burbuja arriba y tú le respondes.",
           "Lee el comentario en voz alta o empieza con «me preguntáis mucho…».", effect="comentario", punch="suave",
           title=False),
]}

AUTO = "auto"
KEYS = list(GANCHOS)


def get(key: str) -> Gancho:
    return GANCHOS.get(key or "", GANCHOS["titulo"])


def pick(hook_title: str, pack: str = "", comentario: str = "", has_person: bool = True) -> str:
    """Sin IA: el gancho que más encaja con el texto y el sector."""
    if comentario:
        return "comentario"
    t = (hook_title or "").strip()
    if any(ch.isdigit() for ch in t[:12]):
        return "numero"
    if t.lower().startswith("pov"):
        return "pov"
    if has_person and pack in ("viajes", "viajero", "general"):
        return "detras"
    return "zoom_seco" if pack in ("cursos", "empresas") else "titulo"


def alternatives(chosen: str, pack: str = "", has_person: bool = True, n: int = 3) -> list[str]:
    """Otros ganchos para probar con un clic, los que lucen con este sector y este vídeo."""
    order = ["titulo", "zoom_seco", "congelado", "detras", "numero", "pov", "aviso", "color", "objeto", "entrada", "mano"]
    out = []
    for k in order:
        g = GANCHOS[k]
        if k == chosen or (g.needs == "persona" and not has_person):
            continue
        if g.packs and pack not in g.packs:
            continue
        out.append(k)
    return out[:n]


def number_in(text: str) -> str:
    """La cifra que abre el gancho («3 errores al ir a Japón» → «3»; «Japón por 2.000 €» → «2.000 €»)."""
    import re

    m = re.search(r"(\d[\d.,]*\s?(?:€|%|x|h|km|min)?)", text or "")
    return m.group(1).strip() if m else ""


def apply(plan: EditPlan, key: str, has_person: bool = True, comentario: str = "") -> str:
    """Deja el plan listo para ese gancho: el efecto de arranque en la primera palabra, el título con su
    prefijo y la entrada de cámara en plan.punch. Devuelve la clave que ha quedado (puede cambiar si el vídeo
    no da para ella: sin persona recortable no hay «detrás de ti»)."""
    g = get(key)
    # Si el reel se vuelve a montar con otro gancho, fuera lo que dejó el anterior.
    plan.effects = [fx for fx in plan.effects if not fx.get("_gancho")]
    for pre in ("POV: ",):
        if plan.hook_title.startswith(pre) and g.prefix != pre:
            plan.hook_title = plan.hook_title[len(pre):]
    if g.needs == "persona" and not has_person:
        g = GANCHOS["titulo"]
    if g.key == "comentario" and not comentario and not any(fx.get("type") == "comentario" for fx in plan.effects):
        g = GANCHOS["titulo"]
    plan.gancho = g.key
    plan.punch = g.punch
    plan.hook_shown = g.title
    if g.prefix and plan.hook_title and not plan.hook_title.lower().startswith(g.prefix.lower().strip()):
        plan.hook_title = g.prefix + plan.hook_title
    if not g.effect or g.key == "comentario":
        return g.key
    # Un solo efecto de arranque: fuera los que la IA hubiera puesto en la primera palabra.
    plan.effects = [fx for fx in plan.effects if not (int(fx.get("word", -1) or 0) == 0 and fx.get("type") in
                                                      ("detras", "cifra", "color", "notificaciones", "congelado",
                                                       "titular", "palabra"))]
    text = plan.hook_title
    sub = ""
    if g.effect == "cifra":
        num = number_in(plan.hook_title)
        if not num:  # sin cifra no hay cifra gigante: título normal
            plan.gancho, plan.hook_shown = "titulo", True
            return "titulo"
        text, sub = num, plan.hook_title.replace(num, "").strip(" ,.:;-") or ""
    elif g.effect == "detras":
        words = [w for w in plan.hook_title.replace("¿", "").replace("?", "").split() if len(w) > 2]
        text = max(words, key=len) if words else plan.hook_title
    elif g.effect == "notificaciones":
        word = next((w.strip('«»"\'.,') for w in plan.hook_title.split() if w.isupper() and len(w) > 2), "")
        text = f"Comenta {word} y te lo mando" if word else plan.hook_title
    plan.effects.insert(0, {"type": g.effect, "word": 0, "text": text[:140], "subtitle": sub[:60], "title": "",
                            "look": g.look, "until_word": None, "_gancho": True})
    return g.key


def as_dict(g: Gancho) -> dict:
    return {"key": g.key, "label": g.label, "description": g.description, "record": g.record, "needs": g.needs}


def catalogue() -> list[dict]:
    return [as_dict(g) for g in GANCHOS.values()]
