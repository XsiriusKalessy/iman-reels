"""Aprende de tus resultados: apunta cómo le fue a cada reel y Imán ajusta los siguientes.

El creador escribe lo que ve en su red (visualizaciones, retención media, guardados, compartidos, comentarios)
en la tarjeta del reel. Con tres o más reels anotados, Imán compara: qué gancho visual, qué estilo de
subtítulos, qué ritmo, qué duración y qué música le funcionan mejor A ESE creador, y se lo cuenta a la IA que
monta los siguientes («a este creador le retienen más los reels con cifra gigante y de 20-35 s»). No hay
números inventados: solo los suyos, y solo cuando hay bastantes para que signifiquen algo.
"""
from __future__ import annotations

from statistics import median

FIELDS = {"views": "visualizaciones", "retention": "retención media (%)", "saves": "guardados",
          "shares": "compartidos", "comments": "comentarios", "followers": "seguidores nuevos"}
MIN_REELS = 3
MIN_GROUP = 2
EDGE = 1.15  # un grupo «gana» cuando su nota media supera en un 15 % a la del resto

LABELS = {
    "gancho": ("gancho visual", {"titulo": "título y zoom", "zoom_seco": "zoom seco", "congelado": "congelado",
                                 "detras": "palabra detrás de ti", "numero": "cifra gigante", "pov": "POV",
                                 "aviso": "aviso de «comenta»", "mano": "mano que tapa", "entrada": "entrar en cuadro",
                                 "objeto": "objeto a cámara", "color": "golpe de color", "comentario": "comentario"}),
    "style": ("estilo de subtítulos", {}),
    "rhythm": ("ritmo", {"rapido": "rápido", "dinamico": "dinámico", "natural": "natural", "sin_tocar": "sin tocar"}),
    "duracion": ("duración", {"corto": "menos de 20 s", "medio": "20-35 s", "largo": "35-60 s", "muylargo": "más de 60 s"}),
    "music": ("música", {"": "sin música", "mia": "tu propia música"}),
    "hook_len": ("gancho escrito", {"corto": "de 5 palabras o menos", "medio": "de 6 a 8 palabras", "largo": "de más de 8 palabras"}),
    "red": ("red", {}),
}


def normalize(body: dict) -> dict:
    """Solo los campos conocidos, como enteros sin negativos (la retención, de 0 a 100)."""
    out = {}
    for k in FIELDS:
        v = body.get(k)
        if v in (None, ""):
            continue
        try:
            n = float(str(v).replace(".", "").replace(",", ".")) if k != "retention" else float(str(v).replace(",", "."))
        except ValueError:
            continue
        if k == "retention":
            n = max(0.0, min(100.0, n))
            out[k] = round(n, 1)
        else:
            out[k] = int(max(0, n))
    return out


def _bucket_duration(d: float) -> str:
    return "corto" if d < 20 else "medio" if d <= 35 else "largo" if d <= 60 else "muylargo"


def _bucket_hook(title: str) -> str:
    n = len((title or "").split())
    return "corto" if n <= 5 else "medio" if n <= 8 else "largo"


def _traits(reel: dict) -> dict:
    opts, plan = reel.get("options") or {}, reel.get("plan") or {}
    style = opts.get("style") if opts.get("style") not in ("auto", "", None) else plan.get("caption_style", "")
    music = opts.get("music")
    music = plan.get("music", "") if music == "auto" else "mia" if music is True else (music or "")
    return {
        "gancho": plan.get("gancho") or ("titulo" if opts.get("hook", True) else ""),
        "style": style or "",
        "rhythm": opts.get("rhythm", ""),
        "duracion": _bucket_duration(float(reel.get("duration") or 0)),
        "music": music,
        "hook_len": _bucket_hook(plan.get("hook_title", "")),
        "red": opts.get("red", ""),
    }


def _notas(reels: list[dict]) -> list[tuple[dict, float]]:
    """Nota de cada reel frente a la mediana del propio creador: 1 = en su media, 2 = el doble."""
    with_data = [r for r in reels if any((r.get("resultados") or {}).get(k) for k in ("views", "retention", "saves", "shares"))]
    if len(with_data) < MIN_REELS:
        return []
    meds = {}
    for k in ("views", "retention", "saves", "shares", "comments"):
        vals = [float(r["resultados"][k]) for r in with_data if r["resultados"].get(k)]
        meds[k] = median(vals) if len(vals) >= MIN_REELS else 0
    out = []
    for r in with_data:
        res, parts = r["resultados"], []
        for k, w in (("views", 1.0), ("retention", 1.2), ("saves", 0.8), ("shares", 0.8), ("comments", 0.5)):
            if meds.get(k) and res.get(k) is not None:
                parts.append((min(3.0, float(res[k]) / meds[k]), w))
        if parts:
            out.append((r, sum(v * w for v, w in parts) / sum(w for _, w in parts)))
    return out


def insights(reels: list[dict]) -> dict:
    """`reels`: [{id, title, duration, options, plan, resultados}]. Devuelve lo aprendido o n < 3."""
    scored = _notas(reels)
    n = len(scored) or sum(1 for r in reels if any((r.get("resultados") or {}).get(k) for k in FIELDS))
    if len(scored) < MIN_REELS:
        return {"n": n, "needed": MIN_REELS, "lessons": [], "best": {}, "top": []}
    best, lessons = {}, []
    for dim, (name, names) in LABELS.items():
        groups: dict[str, list[float]] = {}
        for r, nota in scored:
            groups.setdefault(_traits(r)[dim], []).append(nota)
        cands = {k: sum(v) / len(v) for k, v in groups.items() if len(v) >= MIN_GROUP and k != ""}
        if len(groups) < 2 or not cands:
            continue
        top = max(cands, key=cands.get)
        rest = [x for k, v in groups.items() if k != top for x in v]
        if not rest:
            continue
        rest_avg = sum(rest) / len(rest)
        if cands[top] >= rest_avg * EDGE:
            pct = int(round((cands[top] / rest_avg - 1) * 100)) if rest_avg else 0
            label = names.get(top, top.replace("_", " "))
            best[dim] = top
            lessons.append(f"Te funciona mejor el {name} «{label}»: un {pct} % por encima de tus otros reels "
                           f"({len(groups[top])} reels).")
    tops = sorted(scored, key=lambda x: -x[1])[:3]
    return {"n": n, "needed": MIN_REELS, "lessons": lessons, "best": best,
            "top": [{"id": r.get("id"), "title": r.get("title", ""), "nota": round(nota, 2)} for r, nota in tops]}


def prompt(ins: dict) -> str:
    """Lo aprendido, para la IA que monta el siguiente reel (vacío si aún no hay datos)."""
    if not ins.get("lessons"):
        return ""
    return ("LO QUE FUNCIONA EN LOS RESULTADOS REALES DE ESTE CREADOR (dale prioridad salvo que el vídeo pida otra cosa):\n"
            + "\n".join(f"- {l}" for l in ins["lessons"][:6]))
