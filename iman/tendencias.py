"""Ideas en tendencia hoy, para tu nicho: lo que se mueve en Google hoy, convertido en ideas de reel.

Fuentes gratis y sin clave: el RSS de tendencias diarias de Google (por país) y, si falla, lo más visto en la
Wikipedia en español el día anterior. Luego la IA del creador (o la de Imán) escoge lo que encaja con su
sector y lo convierte en 3-5 ideas con gancho y guion corto. Sin IA, se enseñan los temas tal cual.
Se guarda en caché unas horas para no pedirlo a cada clic.
"""
from __future__ import annotations

import datetime as dt
import json
import time
import urllib.request
import xml.etree.ElementTree as ET

from . import ai, config, jsonfile, packs

GEOS = {"ES": "España", "MX": "México", "AR": "Argentina", "CO": "Colombia", "CL": "Chile", "US": "Estados Unidos"}
CACHE_HOURS = 6
MAX_TOPICS = 20

TREND_SCHEMA = {
    "type": "object",
    "properties": {
        "ideas": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "El tema en tendencia del que sale la idea."},
                "hook": {"type": "string", "description": "Gancho de 7 palabras o menos para el primer segundo."},
                "script": {"type": "string", "description": "Guion de 40-70 palabras con las palabras del creador."},
                "why": {"type": "string", "description": "Por qué encaja hoy con su sector, en una frase."},
            },
            "required": ["topic", "hook", "script", "why"], "additionalProperties": False}},
    },
    "required": ["ideas"],
    "additionalProperties": False,
}

TREND_SYSTEM = """Eres el guionista de reels de un creador. Te paso los temas que hoy son tendencia en su país y su
sector. Elige SOLO los que se puedan conectar con su sector de forma natural y útil para su público (nada de
forzar: si un tema de deportes no tiene nada que ver con viajes, fuera). Para cada uno, una idea de reel:
gancho corto, guion de 40-70 palabras en su tono y por qué encaja hoy. Entre 3 y 5 ideas. Nada de inventar
datos ni cifras sobre el tema: habla de lo que el creador sabe por su trabajo. No menciones marcas ni personas
privadas; con famosos o equipos, solo como contexto, sin afirmar nada que no esté en el titular."""


def _cache_file():
    return config.HOME / "tendencias.json"


def fetch_google(geo: str = "ES", timeout: float = 8.0) -> list[dict]:
    """Tendencias diarias de Google (RSS público). [{"topic", "traffic", "news"}]"""
    url = f"https://trends.google.com/trending/rss?geo={geo}"
    req = urllib.request.Request(url, headers={"User-Agent": "Iman/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - solo el RSS de Google
        data = r.read(2_000_000)
    return parse_google(data)


def parse_google(data: bytes) -> list[dict]:
    ns = {"ht": "https://trends.google.com/trending/rss"}
    root = ET.fromstring(data)
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        traffic = (item.findtext("ht:approx_traffic", namespaces=ns) or "").strip()
        news = [(x.text or "").strip() for x in item.findall("ht:news_item/ht:news_item_title", ns)]
        news = [n[:120] for n in news if n][:2]
        out.append({"topic": title[:80], "traffic": traffic[:20], "news": news})
    return out[:MAX_TOPICS]


def fetch_wikipedia(timeout: float = 8.0) -> list[dict]:
    """Lo más visto ayer en la Wikipedia en español (API pública), sin portadas ni páginas técnicas."""
    day = dt.date.today() - dt.timedelta(days=1)
    url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/es.wikipedia/all-access/{day:%Y/%m/%d}"
    req = urllib.request.Request(url, headers={"User-Agent": "Iman/1.0 (editor de reels)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        data = json.loads(r.read(2_000_000))
    return parse_wikipedia(data)


def parse_wikipedia(data: dict) -> list[dict]:
    out = []
    for a in ((data.get("items") or [{}])[0].get("articles") or []):
        name = str(a.get("article", "")).replace("_", " ")
        if not name or ":" in name or name.startswith("Wikipedia") or name in ("Página principal",):
            continue
        out.append({"topic": name[:80], "traffic": f"{int(a.get('views', 0)):,}".replace(",", "."), "news": []})
    return out[:MAX_TOPICS]


def topics(geo: str = "ES", force: bool = False) -> dict:
    """Los temas de hoy, de la caché si es reciente. {"topics", "source", "fetched"}"""
    geo = geo if geo in GEOS else "ES"
    cached = jsonfile.load(_cache_file()) if _cache_file().exists() else None
    if not force and isinstance(cached, dict) and cached.get("geo") == geo and \
            time.time() - float(cached.get("fetched", 0)) < CACHE_HOURS * 3600 and cached.get("topics"):
        return cached
    result = {"geo": geo, "topics": [], "source": "", "fetched": time.time(), "ideas": {}}
    try:
        result["topics"], result["source"] = fetch_google(geo), "google"
    except Exception:  # noqa: BLE001 - sin red o Google cambió el RSS: a la Wikipedia
        try:
            result["topics"], result["source"] = fetch_wikipedia(), "wikipedia"
        except Exception:  # noqa: BLE001
            result["topics"], result["source"] = [], ""
    if result["topics"]:
        jsonfile.save(_cache_file(), result)
    return result


def ideas(cfg: ai.AIConfig, found: list[dict], pack: str = "", voice_samples: str = "") -> list[dict]:
    """Ideas de reel a partir de los temas, para ese sector. Sin IA, lista vacía (la app enseña los temas)."""
    if not found or not cfg.enabled:
        return []
    sector = packs.PACKS[pack].label if pack in packs.PACKS else "creador de contenido (sector general)"
    if cfg.provider == "iman":
        from . import cloud

        return cloud.call(cfg, "tendencias", {"topics": found[:MAX_TOPICS], "sector": sector,
                                              "voice_samples": voice_samples[:4000]}).get("ideas", [])
    return ideas_raw(cfg, found, sector, voice_samples)


def ideas_raw(cfg: ai.AIConfig, found: list[dict], sector: str, voice_samples: str = "") -> list[dict]:
    lines = [f"- {t['topic']}" + (f" ({t['traffic']} búsquedas)" if t.get("traffic") else "") +
             (f": {' / '.join(t['news'])}" if t.get("news") else "") for t in found[:MAX_TOPICS]]
    user = f"SECTOR DEL CREADOR: {sector}\nFECHA: {dt.date.today():%d/%m/%Y}\n\nTENDENCIAS DE HOY:\n" + "\n".join(lines)
    if voice_samples:
        user += f"\n\nASÍ HABLA EL CREADOR:\n{voice_samples[:4000]}"
    data = ai._ask_json(cfg, TREND_SYSTEM, user, TREND_SCHEMA)
    return [ai._human_dict(i) for i in data.get("ideas", [])][:5]


def remember_ideas(pack: str, items: list[dict]) -> None:
    """Las ideas de hoy para ese sector van a la caché, junto a los temas."""
    cached = jsonfile.load(_cache_file()) if _cache_file().exists() else None
    if isinstance(cached, dict):
        cached.setdefault("ideas", {})[pack or "general"] = items
        jsonfile.save(_cache_file(), cached)
