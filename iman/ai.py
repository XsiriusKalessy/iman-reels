"""El "editor" con IA: decide gancho, tomas falsas y palabras a destacar.

Funciona con Claude o con ChatGPT (cada uno con tu propia clave). Si no hay
clave, Imán sigue funcionando con heurísticas locales.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .models import EditPlan, Word

CLAUDE_MODEL = "claude-opus-5-5"
OPENAI_MODEL = "gpt-4o"

EFFECT_TYPES = ["lista", "palabra", "titular", "cifra", "frase", "tecleo", "color", "comentario",
                "contador", "portada", "cta", "dato", "bruto", "fantasma", "pagina", "detras", "fondo", "desenfoque",
                "ubicacion", "oferta", "ruta", "testimonio", "plazas", "precio", "apoyo", "sube", "choque", "aparece",
                "objeto", "viaje", "notificaciones", "foco", "anillo", "buscador", "chat", "captura", "collage"]
FREE_TEXT_TYPES = ("titular", "cifra", "frase", "tecleo", "color", "comentario", "contador", "portada", "cta", "dato",
                   "bruto", "fantasma", "pagina", "detras", "fondo", "desenfoque",
                   "ubicacion", "oferta", "ruta", "testimonio", "plazas", "precio", "apoyo", "sube", "choque",
                   "aparece", "objeto", "viaje", "notificaciones", "foco", "anillo", "buscador", "chat", "captura", "collage")
LISTA_LOOKS = ("checklist", "capitulos", "itinerario")
TITULAR_LOOKS = ("revista", "elegante", "pizarra", "mixto")
COLORS = ("rosa", "amarillo", "negro", "azul", "rojo", "verde")
LOOK_ENUM = ["", *TITULAR_LOOKS, *LISTA_LOOKS, "enfoque", *COLORS]

CAPTION_STYLES = ["", "impacto", "editorial", "palabra", "karaoke", "caja", "neon", "gigante", "mezcla", "minimal",
                  "elegante", "manuscrita", "marcador", "hormozi", "bebas", "comic", "bloque"]
MUSIC_STYLES = ["", "tranquila", "alegre", "cinematica", "tropical", "phonk", "corporativa", "epica", "emotiva", "inspiracional", "suspense", "acustica", "romantica", "piano", "piano_alegre", "piano_cine", "synthwave"]

EDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "hook_title": {"type": "string", "description": "Título corto en pantalla para los primeros segundos (máx. 7 palabras)."},
        "hook_line": {"type": "string", "description": "Una frase de gancho alternativa que el creador podría grabar."},
        "drop": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "from": {"type": "integer"},
                    "to": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["from", "to", "reason"],
                "additionalProperties": False,
            },
        },
        "emphasis": {"type": "array", "items": {"type": "integer"}},
        "effects": {
            "type": "array",
            "description": "Efectos en pantalla, variados: uno cada 5 a 8 segundos (en un reel de 60 s, de 7 a 11).",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": EFFECT_TYPES},
                    "title": {"type": "string", "description": "lista: título corto opcional, o vacío"},
                    "items": {
                        "type": "array",
                        "description": "lista: de 2 a 5 puntos, cada uno con el índice de la palabra donde se empieza a decir",
                        "items": {
                            "type": "object",
                            "properties": {"text": {"type": "string"}, "at_word": {"type": "integer"}},
                            "required": ["text", "at_word"],
                            "additionalProperties": False,
                        },
                    },
                    "until_word": {"type": "integer", "description": "lista: índice de la última palabra del bloque"},
                    "word": {"type": "integer", "description": "palabra, titular, cifra, frase: índice de la palabra donde aparece"},
                    "text": {"type": "string", "description": "texto principal del efecto"},
                    "subtitle": {"type": "string", "description": "titular: remate en letra manuscrita; cifra: qué mide la cifra; si no, vacío"},
                    "look": {"type": "string", "enum": LOOK_ENUM,
                             "description": "titular: revista, elegante, pizarra o mixto; lista: checklist, capitulos o vacío; "
                                            "frase: enfoque o vacío; color: el color; si no, vacío"},
                },
                "required": ["type", "title", "items", "until_word", "word", "text", "subtitle", "look"],
                "additionalProperties": False,
            },
        },
        "zooms": {
            "type": "array",
            "description": "Rangos [desde, hasta] de palabras donde acercar la cámara para dar énfasis (3 a 8).",
            "items": {
                "type": "object",
                "properties": {"from": {"type": "integer"}, "to": {"type": "integer"}},
                "required": ["from", "to"],
                "additionalProperties": False,
            },
        },
        "pauses": {
            "type": "array",
            "description": "Índices de palabras tras las que la pausa da fuerza y NO se corta (0 a 4).",
            "items": {"type": "integer"},
        },
        "color": {"type": "string", "enum": ["natural", "calido", "teal", "cine", "grano", "retro", "bn"],
                  "description": "Look de color y textura para todo el reel."},
        "caption_style": {"type": "string", "enum": CAPTION_STYLES,
                          "description": "Estilo de subtítulos que mejor encaja con el vídeo."},
        "music": {"type": "string", "enum": MUSIC_STYLES,
                  "description": "Estilo de música de fondo que mejor encaja con el vídeo."},
        "silence": {
            "type": "array",
            "description": "Índice de la primera palabra de la frase más crítica (0 a 2): ahí se corta la música en seco.",
            "items": {"type": "integer"},
        },
    },
    "required": ["hook_title", "hook_line", "drop", "emphasis", "effects", "zooms", "pauses", "silence", "music", "color",
                 "caption_style"],
    "additionalProperties": False,
}

EDIT_SYSTEM = """Eres el editor de vídeo de un creador de contenido que publica reels.
Recibes la transcripción palabra a palabra de una toma en bruto. Cada palabra lleva su índice entre corchetes
y las pausas largas aparecen como (pausa Xs).

Tu trabajo:
1. drop: rangos de índices (ambos incluidos) que hay que quitar porque son errores: frases empezadas y repetidas
   (quita SIEMPRE la versión fallida y deja la buena, normalmente la última), muletillas, "espera, lo repito",
   comentarios al equipo, ruido. Nunca quites contenido bueno. Si no hay nada que quitar, devuelve [].
2. hook_title: el texto que aparece grande en pantalla al principio. Corto, concreto, que genere curiosidad,
   con las palabras del propio creador cuando sea posible. Sin emojis ni comillas. Usa una de estas fórmulas,
   la que mejor encaje con lo que dice: una cifra concreta ("3 errores que…"), un problema que duele ("Si te pasa
   esto…"), romper una creencia ("Nadie te dice que…") o una promesa clara ("Así ahorras…"). Nada genérico.
3. hook_line: una frase de gancho alternativa por si el creador quiere regrabar el arranque.
4. emphasis: índices de 3 a 8 palabras clave que conviene resaltar en los subtítulos (cifras, conceptos clave).
5. effects: el reel tiene que entrar por los ojos, como los de los creadores que más enganchan. Pon un efecto
   cada 5 a 8 segundos (en un reel de 60 s, de 7 a 11), repartidos de principio a fin y MUY variados: mezcla
   textos grandes (titular, palabra, cifra, frase), efectos de vídeo (detras, fondo, desenfoque, fantasma, pagina),
   tarjetas (ubicacion, dato, lista, objeto) y un cierre (cta). Que el primer segundo ya tenga algo potente
   (detras, titular o color). No repitas el mismo tipo dos veces seguidas. Que cada uno tenga sentido con lo
   que se dice en ese momento: nada de relleno.
   - "lista": cuando el creador enumera pasos, razones o cosas ("uno…, dos…, tres…", "3 cosas", "lo primero…,
     lo segundo…"). OBLIGATORIA siempre que enumere: es de lo que más gusta y nunca debe faltar; mientras dura,
     no pongas otro efecto encima salvo las pegatinas "objeto". Cada punto, en 2 a 5 palabras,
     con el índice donde empieza a decirlo. Para "lista" deja word en -1 y text vacío.
   - "palabra": una palabra clave que salta gigante en pantalla un segundo.
   - "titular": la frase más potente del vídeo como titular de revista en la parte de arriba (text: 3 a 6
     palabras; subtitle: 1 a 3 palabras de remate en letra manuscrita, que no repitan text; look: revista,
     elegante, pizarra o mixto; mixto = palabras en mayúsculas sobre cajitas y el remate grande en cursiva,
     ideal para preguntas tipo "¿CUÁNTO CUESTA…?"). Dura hasta until_word.
   - "cifra": un número que impresiona (text: solo la cifra, p. ej. "80" o "3x"; subtitle: qué mide, 3 a 7
     palabras). Ocupa la pantalla dos segundos.
   - "frase": una frase corta y emocional (1 a 4 palabras) a pantalla completa en letra manuscrita. Con look
     "enfoque", una afirmación de hasta 12 palabras en serif que entra desenfocada sobre fondo oscuro.
   - "dato": etiqueta pequeña junto a la cara con un dato (text: la cifra, "12"; subtitle: "horas de vídeo").
   - "contador": cuando el creador habla de cuánto dura la toma en bruto o del tiempo que ahorra; muestra la
     duración real de la toma bajando hasta la del reel. Deja text en "-" y title y subtitle vacíos.
   - "portada": el vídeo convertido en portada de revista (text: la cabecera, 1 palabra corta, p. ej. la
     marca o el tema; subtitle: un titular de portada de 4 a 8 palabras). Úsalo como mucho una vez.
   - "bruto": tarjeta inclinada con la toma original sin cortar, cuando el creador habla de cómo grabó o de
     que no ha editado (title: etiqueta corta, p. ej. "Bruto"; subtitle: nota a mano, p. ej. "tal cual, sin tocar").
   - "fantasma": un eco semitransparente del propio creador durante una frase dramática o de sorpresa
     (text: "-"). Muy de vez en cuando.
   - "pagina": el vídeo encogido dentro de una hoja de revista (text: titular de la hoja, 2 a 6 palabras;
     subtitle: remate a mano o vacío).
   - "detras": una palabra gigante DETRÁS del creador, que le tapa parte de las letras (text: 1 palabra,
     la marca o el concepto clave; subtitle: 1 a 3 palabras encima o vacío; look: color o vacío). Es el efecto
     más llamativo: úsalo en el gancho o en el momento clave, una vez.
   - "fondo": el fondo cambia a un color liso detrás del creador (look: el color; text: palabra blanca
     detrás o "-"). Para un remate o un cambio de tema.
   - "desenfoque": el fondo se desenfoca y el creador queda nítido, para una frase íntima o importante
     (text: "-").
   - "cta": al final, si el creador pide comentar una palabra para recibir algo (text: esa palabra;
     subtitle: el aviso, p. ej. "Te envío el enlace por privado").
   - "tecleo": una caja que se escribe sola con una petición o mensaje que el creador cuenta que escribe
     (text: hasta 120 caracteres; title: etiqueta corta, p. ej. "Le pido a la IA").
   - "color": golpe de color a pantalla completa durante un segundo, con una palabra enorme (text: 1 palabra;
     subtitle: 1 a 3 palabras o vacío; look: el color). Para cambios de tema o remates. Puede haber hasta 3
     seguidos, uno por palabra, si el creador enumera.
   - "comentario": burbuja de un comentario de un seguidor al principio, solo si el creador responde a un
     comentario (text: el comentario; title: nombre de usuario o vacío). word suele ser 0.
   - "ubicacion": chincheta con el nombre de un lugar (text: el lugar; subtitle: país o zona).
   - "oferta": tarjeta de oferta (text: qué se vende o el destino; subtitle: el precio; title: lo que incluye).
   - "ruta": avión de un sitio a otro (text: origen; subtitle: destino; title: duración o vacío).
   - "testimonio": reseña con cinco estrellas (text: lo que dijo el cliente o alumno; subtitle: quién lo dijo).
   - "plazas": aviso rojo de escasez arriba (text: "Solo 7 plazas", "Acaba el domingo").
   - "notificaciones": notificaciones del móvil que caen apiladas, cuando habla de resultados que llegan (pedidos,
     reservas, mensajes, ventas) (text: de 2 a 4 avisos cortos separados por "|", "Nuevo pedido · 49 €|Reserva
     confirmada"; title: de dónde vienen, "Tienda", "Reservas").
   - "foco": los bordes se oscurecen y queda la luz sobre el creador, para la frase más seria o íntima
     (text: 2 a 5 palabras que la resumen, o "-" para solo el foco).
   - "anillo": texto que gira alrededor de su cabeza (text: 1 a 3 palabras que se repiten, "PLAZAS LIMITADAS",
     "NUEVO", "SOLO HOY"). Una vez como mucho, en un momento de urgencia o novedad.
   - "buscador": una barra de búsqueda en la que se escribe sola una frase, cuando el creador cuenta lo que la
     gente busca o pregunta (text: la búsqueda, "cómo ahorrar en vuelos", máx. 40 letras).
   - "chat": conversación de mensajes que van apareciendo, cuando cuenta lo que le escribe un cliente o amigo
     (text: 2 a 4 mensajes cortos separados por "|", alternando: el primero es del otro y el segundo la respuesta).
   - "precio": etiqueta de precio (text: precio nuevo; subtitle: precio anterior tachado o vacío; title: "-30%" o vacío).
   - "apoyo": SOLO si te pasan VÍDEOS DE APOYO. Mientras el creador habla de lo que se ve en ese vídeo (el destino,
     el producto, el local), el vídeo de apoyo ocupa la pantalla y el creador queda en un círculo abajo
     (text: el número del vídeo de apoyo, "1", "2"…; until_word: hasta dónde). De 2 a 5 segundos cada uno;
     usa cada vídeo una vez y aquí sí puede haber varios efectos del mismo tipo.
   - "captura": SOLO con vídeos o fotos de apoyo. Una foto o captura de apoyo en una tarjeta con etiqueta, cuando
     habla de algo que se puede enseñar (su web, un resultado, un mensaje) (text: número del archivo, "2";
     subtitle: etiqueta corta, "Mi web").
   - "collage": SOLO con 2 o más apoyos. Dos o tres fotos flotando con etiquetas, al enumerar sitios o productos
     (text: números separados por comas, "1,2,3"; subtitle: etiquetas separadas por "|", "Tokio|Kioto|Osaka").
   Efectos con las manos (Imán ve dónde están las manos del creador y los ajusta solo; si no las ve, salen igual):
   - "sube": una palabra sale de su dedo y sube con él (text: 1 o 2 palabras de lo que crece: "+30 %", "VENTAS",
     "MÁS CLIENTES"). Cuando habla de subir, crecer, más.
   - "choque": una palabra enorme en el centro que salta en pedazos cuando la mano la golpea o al final
     (text: 1 palabra; "ADIÓS", "MITO", "EXCUSAS"). Para romper con algo: un mito, un error, una excusa.
   - "aparece": lo que dice aparece donde señala con el dedo (text: lo que nombra, corto: "90 €", "Roma",
     "mi socio"). Cuando presenta algo concreto: un precio, un sitio, una persona.
   En "lista", look "itinerario" muestra los días de un viaje en una línea de tiempo; look "capitulos" muestra un índice numerado que se ilumina por partes; look "checklist" muestra casillas arriba que se marcan al decir cada punto (bueno para
   "lo que hace" o "lo que no necesitas"); vacío muestra la lista grande en el centro.
   - "viaje": itinerario de un viaje con varias paradas: la ruta se dibuja de ciudad en ciudad con un avión
     sobre un mapa 3D real (text: las paradas en orden separadas por "›", cada una con sus coordenadas
     aproximadas (lat, lon), p. ej. "Tokio (35.68, 139.69) › Kioto (35.01, 135.77) › Gero (35.81, 137.24)";
     en pantalla solo salen los nombres; title: el viaje en
     2 a 4 palabras, p. ej. "Japón en grupo"; subtitle: las fechas, p. ej. "18–29 nov", o vacío). Cuando el
     creador cuenta el recorrido de un viaje. Mejor que "ruta" si hay más de dos sitios.
   - "objeto": pegatina con el dibujo de una cosa concreta que el creador nombra (text: UN emoji que la dibuje,
     p. ej. 🔌 adaptador, 🧦 calcetines, 💊 medicinas, 📱 móvil, 💶 dinero, ✈️ vuelo, 🍣 comida, 🏨 hotel;
     subtitle: el nombre en 1 a 3 palabras). Dura unos 2 segundos. Úsalo cada vez que nombre objetos, sobre todo
     al enumerar (uno por cosa, aunque haya una "lista" a la vez: es la única excepción).
   Rellena siempre todos los campos: los que no use el tipo van vacíos, [] o -1. Cada tipo como mucho dos
   veces (portada, detras, contador, comentario y cta una sola; objeto y apoyo, las que hagan falta) y nunca
   dos efectos a la vez, salvo objeto con lista.
6. zooms: rangos cortos (una frase) donde acercar la cámara para subrayar una idea fuerte: de 3 a 8, para
   que el plano no se quede quieto.
7. pauses: los silencios se cortan, pero no por segundos: con sentido. Si el creador hace una pausa a propósito
   para dar fuerza (antes de revelar un dato, tras una pregunta, antes del remate), pon el índice de la palabra
   tras la que va esa pausa y se respetará. Solo las que de verdad suman.
8. silence: el silencio repentino es un efecto brutal. Elige la frase más crítica del reel (la revelación, el
   dato que cambia todo, el remate) y pon el índice de su primera palabra: justo antes se cortan en seco la
   música y los efectos, solo queda la voz, y vuelven con un golpe al terminar la frase. Una, como mucho dos,
   y nunca en los 3 primeros segundos. Si no hay una frase así, devuelve [].
9. music: la música de fondo que pide el vídeo por su tema y su tono: "epica" (retos, logros, grandes viajes),
   "emotiva" (historias personales, despedidas), "inspiracional" (superación, motivación, viajes), "tranquila"
   (consejos relajados, rutinas), "alegre" (planes, productos, buen rollo), "tropical" (playa, verano, fiesta),
   "phonk" (energía, deporte, coches, retos rápidos), "corporativa" (empresas, servicios, formación),
   "cinematica" (paisajes, revelaciones), "suspense" (misterios, errores, "lo que nadie te cuenta"),
   "acustica" (naturaleza, cercanía), "romantica" (parejas, bodas, escapadas), "piano" (reflexiones, emoción
   íntima), "piano_alegre" (consejos amables, hogar), "piano_cine" (momentos solemnes, recuerdos, homenajes).
   "synthwave" (autoridad, negocios agresivos, tecnología, noche, coches). "" si mejor sin música.
10. color: el look de todo el reel. "natural" por defecto; "calido" (comida, hogar, atardeceres, cercanía);
   "teal" (viajes, playa, ciudad: turquesas en agua y cielo, piel cálida); "cine" (historias, documental);
   "grano" (nostalgia, recuerdos); "retro" (gaming, cripto, años 80-90); "bn" (reflexión seria, dramático).
11. caption_style: los subtítulos que mejor venden este vídeo. "hormozi" (consejos directos, negocios, ventas:
   palabra clave en color, letra gruesa), "impacto" (energía, retos, TikTok), "editorial" (viajes, estilo de
   vida, marcas cuidadas), "palabra" (frases cortas con mucho ritmo, una palabra cada vez), "karaoke" (cursos,
   explicaciones largas), "caja" (anuncios, ofertas, mucho contraste), "neon" (noche, ocio, tecnología),
   "gigante" (pocas palabras muy fuertes), "mezcla" (reflexiones, frases para guardar), "minimal" (lujo,
   moda, calma), "elegante" (bodas, hoteles, gastronomía), "manuscrita" (diario personal, cercanía),
   "marcador" (enseñar, datos, listas), "bebas" (deporte, motor, titulares), "comic" (humor, niños, juegos),
   "bloque" (avisos, polémicas, opiniones fuertes).
Respeta el idioma del vídeo. Sigue las instrucciones del creador si las hay."""

REVISE_SYSTEM = EDIT_SYSTEM + """

Ahora el reel ya está montado y el creador te pide cambios, como a su editor. Recibes el plan actual en JSON.
Devuelve el plan COMPLETO actualizado: conserva todo lo que no te pide cambiar y aplica solo lo que pide.
Si pide cambiar el ritmo o el estilo de subtítulos, indícalo en settings (si no, deja los campos vacíos).
En reply, responde al creador en una frase corta diciendo qué has cambiado."""


def transcript_for_prompt(words: list[Word]) -> str:
    out = []
    for i, w in enumerate(words):
        if i:
            gap = w.start - words[i - 1].end
            if gap >= 0.5:
                out.append(f"(pausa {gap:.1f}s)")
        out.append(f"[{i}] {w.text}")
    return " ".join(out)


@dataclass
class AIConfig:
    provider: str = "none"  # iman | claude | openai | none
    anthropic_key: str | None = None
    openai_key: str | None = None
    claude_model: str = CLAUDE_MODEL
    openai_model: str = OPENAI_MODEL
    license_key: str | None = None
    license_instance: str | None = None

    @property
    def enabled(self) -> bool:
        return (
            self.provider == "iman"  # con licencia, o en prueba gratis limitada
            or (self.provider == "claude" and bool(self.anthropic_key))
            or (self.provider == "openai" and bool(self.openai_key))
        )


def _ask_json(cfg: AIConfig, system: str, user: str, schema: dict, images: list[bytes] | None = None) -> dict:
    """Pregunta a la IA y devuelve JSON con el esquema dado. `images` son JPEG (fotogramas)."""
    import base64

    b64 = [base64.b64encode(img).decode() for img in images or []]
    if cfg.provider == "claude":
        import anthropic

        client = anthropic.Anthropic(api_key=cfg.anthropic_key)
        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": d}} for d in b64]
        resp = client.beta.messages.create(
            model=cfg.claude_model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": [*content, {"type": "text", "text": user}] if b64 else user}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError("Claude no ha podido procesar este vídeo")
        text = next(b.text for b in resp.content if b.type == "text")
        return json.loads(text)
    if cfg.provider == "openai":
        from openai import OpenAI

        client = OpenAI(api_key=cfg.openai_key)
        resp = client.chat.completions.create(
            model=cfg.openai_model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": [
                {"type": "text", "text": user},
                *({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{d}"}} for d in b64)
            ] if b64 else user}],
            response_format={"type": "json_schema", "json_schema": {"name": "respuesta", "schema": schema, "strict": True}},
        )
        return json.loads(resp.choices[0].message.content)
    raise RuntimeError("No hay proveedor de IA configurado")


def plan_edit(cfg: AIConfig, words: list[Word], instructions: str = "", hook_template: str = "",
              pack: str = "") -> EditPlan:
    if cfg.provider == "iman":
        from . import cloud

        data = cloud.call(cfg, "plan", {"words": [w.__dict__ for w in words], "instructions": instructions,
                                        "hook_template": hook_template, "pack": pack})
        return _plan_from(data, len(words), "iman")
    return _plan_from(plan_edit_raw(cfg, words, instructions, hook_template, pack), len(words), cfg.provider)


def plan_edit_raw(cfg: AIConfig, words: list[Word], instructions: str = "", hook_template: str = "",
                  pack: str = "") -> dict:
    from . import packs

    user = "TRANSCRIPCIÓN:\n" + transcript_for_prompt(words)
    if packs.get(pack).guide:
        user += "\n\n" + packs.get(pack).guide
    if hook_template:
        user += f"\n\nPLANTILLA DE GANCHO elegida por el creador (adáptala a lo que dice el vídeo): {hook_template}"
    if instructions.strip():
        user += f"\n\nINSTRUCCIONES DEL CREADOR:\n{instructions.strip()}"
    return _ask_json(cfg, EDIT_SYSTEM, user, EDIT_SCHEMA)


def _look(kind: str, look: str) -> str:
    if kind == "titular":
        return look if look in TITULAR_LOOKS else "revista"
    if kind == "color":
        return look if look in COLORS else "rosa"
    if kind in ("detras", "fondo"):
        return look if look in COLORS else ""
    if kind == "frase" and look == "enfoque":
        return look
    return ""


def _plan_from(data: dict, n: int, source: str) -> EditPlan:
    drops, reasons = [], []
    for d in data.get("drop", []):
        a, b = int(d["from"]), int(d["to"])
        if 0 <= a <= b < n and (b - a) < n * 0.5:  # nunca dejar que borre medio vídeo
            drops.append((a, b))
            reasons.append(d.get("reason", ""))
    effects = []
    for fx in data.get("effects", []):
        if fx.get("type") == "lista":
            items = [it for it in fx.get("items", []) if 0 <= int(it.get("at_word", -1)) < n and it.get("text")]
            if len(items) >= 2:
                until = int(fx.get("until_word", -1))
                effects.append({"type": "lista", "title": fx.get("title", ""), "items": items,
                                "until_word": until if 0 <= until < n else None,
                                "look": fx.get("look") if fx.get("look") in LISTA_LOOKS else ""})
        elif fx.get("type") == "palabra" and 0 <= int(fx.get("word", -1)) < n:
            effects.append({"type": "palabra", "word": int(fx["word"]), "text": fx.get("text", "")})
        elif fx.get("type") in FREE_TEXT_TYPES and 0 <= int(fx.get("word", -1)) < n \
                and str(fx.get("text", "")).strip():
            until = int(fx.get("until_word", -1))
            effects.append({"type": fx["type"], "word": int(fx["word"]), "text": str(fx["text"]).strip()[:140],
                            "subtitle": str(fx.get("subtitle", "")).strip()[:60],
                            "title": str(fx.get("title", "")).strip()[:40],
                            "look": _look(fx["type"], fx.get("look", "")),
                            "until_word": until if int(fx["word"]) < until < n else None})
    zooms = [(int(z["from"]), int(z["to"])) for z in data.get("zooms", [])
             if 0 <= int(z["from"]) <= int(z["to"]) < n]
    pauses = sorted({int(i) for i in data.get("pauses", []) if 0 <= int(i) < n - 1})[:6]
    silence = sorted({int(i) for i in data.get("silence", []) if 0 < int(i) < n - 1})[:2]
    return EditPlan(
        hook_title=data.get("hook_title", "").strip(),
        hook_line=data.get("hook_line", "").strip(),
        drop=drops,
        drop_reasons=reasons,
        emphasis=[i for i in data.get("emphasis", []) if 0 <= int(i) < n],
        effects=effects,
        zooms=zooms,
        pauses=pauses,
        silence=silence,
        music=data.get("music", "") if data.get("music", "") in MUSIC_STYLES else "",
        color=str(data.get("color", "")),
        caption_style=data.get("caption_style", "") if data.get("caption_style", "") in CAPTION_STYLES else "",
        source=source,
    )


REVISE_SCHEMA = {
    **EDIT_SCHEMA,
    "properties": {
        **EDIT_SCHEMA["properties"],
        "settings": {
            "type": "object",
            "properties": {
                "rhythm": {"type": "string", "enum": ["", "rapido", "dinamico", "natural", "sin_tocar"]},
                "style": {"type": "string", "enum": ["", "impacto", "editorial", "palabra", "karaoke", "caja", "neon", "gigante",
                                                    "mezcla", "minimal", "elegante", "manuscrita", "marcador", "hormozi", "bebas", "comic", "bloque"]},
            },
            "required": ["rhythm", "style"],
            "additionalProperties": False,
        },
        "reply": {"type": "string"},
    },
    "required": EDIT_SCHEMA["required"] + ["settings", "reply"],
}


def _plan_to_prompt(plan: EditPlan) -> dict:
    return {
        "hook_title": plan.hook_title,
        "hook_line": plan.hook_line,
        "drop": [{"from": a, "to": b, "reason": r} for (a, b), r in
                 zip(plan.drop, plan.drop_reasons + [""] * len(plan.drop))],
        "emphasis": plan.emphasis,
        "effects": plan.effects,
        "zooms": [{"from": a, "to": b} for a, b in plan.zooms],
        "pauses": plan.pauses,
        "silence": plan.silence,
        "music": plan.music,
        "color": plan.color,
        "caption_style": plan.caption_style,
    }


def revise_plan(cfg: AIConfig, words: list[Word], plan: EditPlan, message: str,
                rhythm: str, style: str) -> tuple[EditPlan, dict, str]:
    """Aplica un cambio pedido en lenguaje natural. Devuelve (plan, ajustes, respuesta)."""
    if cfg.provider == "iman":
        from . import cloud

        data = cloud.call(cfg, "revise", {"words": [w.__dict__ for w in words], "plan": plan.to_dict(),
                                          "message": message, "rhythm": rhythm, "style": style})
        settings = {k: v for k, v in (data.get("settings") or {}).items() if v}
        return _plan_from(data, len(words), "iman"), settings, data.get("reply", "").strip()
    data = revise_plan_raw(cfg, words, plan, message, rhythm, style)
    settings = {k: v for k, v in (data.get("settings") or {}).items() if v}
    return _plan_from(data, len(words), cfg.provider), settings, data.get("reply", "").strip()


def revise_plan_raw(cfg: AIConfig, words: list[Word], plan: EditPlan, message: str, rhythm: str, style: str) -> dict:
    user = (
        "TRANSCRIPCIÓN:\n" + transcript_for_prompt(words)
        + "\n\nPLAN ACTUAL:\n" + json.dumps(_plan_to_prompt(plan), ensure_ascii=False)
        + f"\n\nAJUSTES ACTUALES: ritmo={rhythm}, estilo={style}"
        + f"\n\nEL CREADOR PIDE:\n{message.strip()}"
    )
    return _ask_json(cfg, REVISE_SYSTEM, user, REVISE_SCHEMA)


# --- Agente de ideas (paso 0: antes de grabar) ---------------------------------

IDEA_SCHEMA = {
    "type": "object",
    "properties": {
        "ideas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "hook": {"type": "string"},
                    "script": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["hook", "script", "why"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["ideas"],
    "additionalProperties": False,
}

IDEA_SYSTEM = """Eres el guionista de reels de un creador. Le das ideas listas para grabar en una sola toma
de 30 a 60 segundos con el móvil. Para cada idea: un gancho que se dice en los 3 primeros segundos, un guion
corto escrito como habla el creador (frases cortas, sin tecnicismos, con una llamada a la acción al final) y
una línea explicando por qué puede funcionar. Si te pasa ejemplos de cómo habla, imita su estilo."""


def generate_ideas(cfg: AIConfig, topic: str, audience: str = "", voice_samples: str = "", n: int = 3) -> list[dict]:
    if cfg.provider == "iman":
        from . import cloud

        return cloud.call(cfg, "ideas", {"topic": topic, "audience": audience,
                                         "voice_samples": voice_samples[:6000], "n": n}).get("ideas", [])
    user = f"Tema: {topic}\nNúmero de ideas: {n}"
    if audience:
        user += f"\nPúblico: {audience}"
    if voice_samples:
        user += f"\n\nASÍ HABLA EL CREADOR (transcripciones de reels anteriores):\n{voice_samples[:6000]}"
    return _ask_json(cfg, IDEA_SYSTEM, user, IDEA_SCHEMA).get("ideas", [])


# --- Kit de marca: la IA escribe el cierre a partir de una frase -------------------

BRAND_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "cta": {"type": "string"},
        "font": {"type": "string", "enum": ["Moderna", "Impacto", "Condensada", "Elegante", "Manuscrita"]},
        "sector": {"type": "string", "enum": ["general", "viajes", "cursos", "productos", "empresas"]},
    },
    "required": ["name", "cta", "font", "sector"],
    "additionalProperties": False,
}

BRAND_SYSTEM = """Preparas el kit de marca de un negocio o creador para sus reels de Instagram y TikTok.
Te describen el negocio en una frase. Devuelve: el nombre de la marca tal cual lo dicen (o vacío si no lo
dicen), una llamada a la acción para el cierre del reel (máximo 5 palabras, en imperativo, concreta para ese
negocio, p. ej. "Reserva tu viaje por WhatsApp", "Apúntate al curso", "Pide el tuyo hoy") y la fuente que mejor
encaja: Moderna (limpia, versátil), Impacto (fuerte, ventas), Condensada (titulares, deporte), Elegante (lujo,
moda, viajes premium) o Manuscrita (cercana, artesanal). Y el sector: viajes, cursos (formación, coaching),
productos (tienda, marca de producto), empresas (servicios, negocio local) o general."""


def brand_copy(cfg: AIConfig, description: str) -> dict:
    if cfg.provider == "iman":
        from . import cloud

        return cloud.call(cfg, "brand", {"description": description})
    data = _ask_json(cfg, BRAND_SYSTEM, f"Negocio: {description}", BRAND_SCHEMA)
    return {"name": data.get("name", "")[:40], "cta": data.get("cta", "")[:40], "font": data.get("font", ""),
            "sector": data.get("sector", "")}


# --- Texto para publicar ------------------------------------------------------------

POST_SCHEMA = {
    "type": "object",
    "properties": {
        "caption": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["caption", "hashtags"],
    "additionalProperties": False,
}

POST_SYSTEM = """Escribes el texto que acompaña a un reel en Instagram y TikTok, con la voz del creador.
Estructura: una primera línea que engancha (no repitas el título del vídeo tal cual), 2 a 4 frases cortas con
el valor del vídeo, y una llamada a la acción al final (usa la del creador si te la pasa). Máximo 600
caracteres, saltos de línea entre bloques, como mucho 2 emojis. Hashtags: de 5 a 8, en el idioma del vídeo,
mezclando de nicho y generales, sin el símbolo # y sin espacios."""


def post_copy(cfg: AIConfig, transcript: str, hook: str = "", pack: str = "", cta: str = "", handle: str = "") -> dict:
    if cfg.provider == "iman":
        from . import cloud

        data = cloud.call(cfg, "post", {"transcript": transcript[:6000], "hook": hook, "pack": pack,
                                        "cta": cta, "handle": handle})
    else:
        user = f"LO QUE DICE EL VÍDEO:\n{transcript[:6000]}\n\nTítulo en pantalla: {hook}"
        if pack and pack != "general":
            user += f"\nSector: {pack}"
        if cta:
            user += f"\nLlamada a la acción del creador: {cta}"
        if handle:
            user += f"\nCuenta: {handle}"
        data = _ask_json(cfg, POST_SYSTEM, user, POST_SCHEMA)
    tags = []
    for t in data.get("hashtags", []):
        t = "".join(str(t).split()).lstrip("#")
        if t and t.lower() not in (x.lower() for x in tags):
            tags.append(t)
    return {"caption": str(data.get("caption", "")).strip()[:2000], "hashtags": tags[:10]}


# --- Copiar el estilo de un reel ------------------------------------------------------

STYLE_FONTS = ["Moderna", "Impacto", "Condensada", "Elegante", "Manuscrita"]
STYLE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Nombre corto para el estilo (2 o 3 palabras)."},
        "font": {"type": "string", "enum": STYLE_FONTS},
        "uppercase": {"type": "boolean"},
        "words_per_line": {"type": "integer", "description": "Palabras que se ven a la vez en los subtítulos (1 a 7)."},
        "position": {"type": "string", "enum": ["arriba", "centro", "abajo"]},
        "size": {"type": "string", "enum": ["pequeño", "mediano", "grande"]},
        "text_color": {"type": "string", "description": "#RRGGBB"},
        "highlight_color": {"type": "string", "description": "#RRGGBB de la palabra que se está diciendo"},
        "outline": {"type": "boolean", "description": "borde o sombra oscura alrededor de las letras"},
        "box": {"type": "boolean", "description": "caja de color detrás del texto"},
        "box_color": {"type": "string", "description": "#RRGGBB o vacío"},
        "pop": {"type": "boolean", "description": "la palabra que se dice crece o salta"},
        "notes": {"type": "string", "description": "En una frase: cómo es el estilo (letra, colores, ritmo, efectos)."},
    },
    "required": ["name", "font", "uppercase", "words_per_line", "position", "size", "text_color",
                 "highlight_color", "outline", "box", "box_color", "pop", "notes"],
    "additionalProperties": False,
}

STYLE_SYSTEM = """Eres diseñador de reels. Te paso fotogramas de un reel que le gusta al creador. Fíjate SOLO en el
estilo de los subtítulos y los textos en pantalla, no en el contenido ni en la persona: qué tipo de letra es
(Moderna = sans limpia; Impacto = sans muy gruesa; Condensada = alta y estrecha; Elegante = con serifa;
Manuscrita = a mano), si va en mayúsculas, cuántas palabras se ven a la vez, dónde está, de qué tamaño, los
colores (texto y palabra destacada), si lleva borde o caja detrás y si la palabra activa salta. Inspírate en el
estilo; no copies logotipos ni marcas. Si no hay subtítulos visibles, deduce un estilo limpio que encaje."""


def style_from_frames(cfg: AIConfig, frames: list[bytes], extra: str = "") -> dict:
    if cfg.provider == "iman":
        import base64

        from . import cloud

        return cloud.call(cfg, "style", {"frames": [base64.b64encode(f).decode() for f in frames[:8]],
                                         "extra": extra})
    return _ask_json(cfg, STYLE_SYSTEM, "Fotogramas del reel, en orden." + (f"\n{extra}" if extra else ""),
                     STYLE_SCHEMA, images=frames[:8])


# --- Kit de publicación: carrusel e historias ----------------------------------------

KIT_SCHEMA = {
    "type": "object",
    "properties": {
        "carousel": {
            "type": "array",
            "description": "De 5 a 8 diapositivas. La primera es la portada (gancho), la última la llamada a la acción.",
            "items": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "body": {"type": "string"}},
                "required": ["title", "body"],
                "additionalProperties": False,
            },
        },
        "stories": {
            "type": "array",
            "description": "3 historias para anunciar el reel.",
            "items": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "sticker": {"type": "string"}},
                "required": ["text", "sticker"],
                "additionalProperties": False,
            },
        },
        "reply": {"type": "string"},
    },
    "required": ["carousel", "stories", "reply"],
    "additionalProperties": False,
}

KIT_SYSTEM = """Preparas, a partir de un reel ya editado, el resto de piezas para publicarlo con la voz del creador.
CARRUSEL de Instagram (5 a 8 diapositivas): la 1 es la portada con un gancho fuerte (título de 3 a 8 palabras,
body vacío o una línea); las del medio cuentan las ideas del vídeo, una por diapositiva (título corto de 2 a 7
palabras y body de 1 a 3 frases, máximo 220 caracteres); la última invita a actuar (usa la llamada a la acción
del creador si la hay). HISTORIAS (3): textos muy cortos para anunciar el reel (máx. 90 caracteres) y un sticker
de 1 a 3 palabras ("Nuevo reel", "¿Te pasa?", "Link en bio"…). Nada de inventar datos que no diga el vídeo.
Si te pasan un KIT ACTUAL y un CAMBIO, devuelve el kit completo con solo ese cambio aplicado
("en la diapositiva 3…" = la tercera, contando desde 1). En reply, una frase corta con lo que has hecho."""


def kit_copy(cfg: AIConfig, transcript: str, hook: str = "", pack: str = "", cta: str = "",
             current: dict | None = None, message: str = "") -> dict:
    if cfg.provider == "iman":
        from . import cloud

        data = cloud.call(cfg, "kit", {"transcript": transcript[:6000], "hook": hook, "pack": pack, "cta": cta,
                                       "current": current or {}, "message": message})
    else:
        data = kit_copy_raw(cfg, transcript, hook, pack, cta, current, message)
    return clean_kit(data)


def kit_copy_raw(cfg: AIConfig, transcript: str, hook: str = "", pack: str = "", cta: str = "",
                 current: dict | None = None, message: str = "") -> dict:
    user = f"LO QUE DICE EL VÍDEO:\n{transcript[:6000]}\n\nTítulo del reel: {hook}"
    if pack and pack != "general":
        user += f"\nSector: {pack}"
    if cta:
        user += f"\nLlamada a la acción del creador: {cta}"
    if current and message.strip():
        user += ("\n\nKIT ACTUAL:\n" + json.dumps({k: current.get(k, []) for k in ("carousel", "stories")},
                                                  ensure_ascii=False) + f"\n\nCAMBIO QUE PIDE:\n{message.strip()}")
    return _ask_json(cfg, KIT_SYSTEM, user, KIT_SCHEMA)


def clean_kit(data: dict) -> dict:
    slides = [{"title": str(s.get("title", "")).strip()[:90], "body": str(s.get("body", "")).strip()[:260]}
              for s in data.get("carousel", []) if str(s.get("title", "")).strip()][:10]
    stories = [{"text": str(s.get("text", "")).strip()[:120], "sticker": str(s.get("sticker", "")).strip()[:30]}
               for s in data.get("stories", []) if str(s.get("text", "")).strip()][:5]
    return {"carousel": slides, "stories": stories, "reply": str(data.get("reply", "")).strip()[:300]}


CLIPS_SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "from": {"type": "integer"},
                    "to": {"type": "integer"},
                    "title": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["from", "to", "title", "why"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["clips"],
    "additionalProperties": False,
}

CLIPS_SYSTEM = """Sacas reels de un vídeo largo del creador (un directo, un podcast, una clase, un vídeo de YouTube).
Te paso la transcripción con el número de cada palabra entre corchetes.
Elige los mejores momentos para convertirlos en reels independientes:
- Cada uno se entiende solo, sin haber visto el resto: empieza al principio de una idea y acaba cuando se cierra.
- Entre 20 y 60 segundos cada uno (mira las marcas de tiempo), sin solaparse.
- Prioriza lo que engancha: una opinión fuerte, un consejo concreto, una historia, una cifra que sorprende.
- "from" y "to" son números de palabra; "to" es la última palabra que se queda.
- "title" es el gancho en pantalla, de 3 a 7 palabras, con la voz del creador.
- "why" explica en una frase por qué funciona.
Ordénalos del mejor al peor. Responde solo con el JSON."""


def transcript_with_times(words: list[Word]) -> str:
    """Transcripción con una marca de tiempo cada 10 segundos, para vídeos largos."""
    out, mark = [], -10.0
    for i, w in enumerate(words):
        if w.start - mark >= 10:
            mark = w.start
            out.append(f"<{int(w.start // 60)}:{int(w.start % 60):02d}>")
        out.append(f"[{i}] {w.text}")
    return " ".join(out)


def pick_clips(cfg: AIConfig, words: list[Word], n: int = 4) -> list[dict]:
    if cfg.provider == "iman":
        from . import cloud

        data = cloud.call(cfg, "clips", {"transcript": transcript_with_times(words)[:120000], "n": n})
    else:
        data = pick_clips_raw(cfg, transcript_with_times(words), n)
    return clean_clips(data, words, n)


def pick_clips_raw(cfg: AIConfig, transcript: str, n: int = 4) -> dict:
    user = f"TRANSCRIPCIÓN:\n{transcript}\n\nSaca como mucho {n} reels."
    return _ask_json(cfg, CLIPS_SYSTEM, user, CLIPS_SCHEMA)


def clean_clips(data: dict, words: list[Word], n: int) -> list[dict]:
    """Solo tramos válidos, de 12 a 90 segundos y sin solaparse."""
    out: list[dict] = []
    for c in data.get("clips", []):
        a, b = int(c.get("from", -1)), int(c.get("to", -1))
        if not (0 <= a < b < len(words)):
            continue
        dur = words[b].end - words[a].start
        if not 12 <= dur <= 90 or any(a <= o["to"] and o["from"] <= b for o in out):
            continue
        out.append({"from": a, "to": b, "title": str(c.get("title", "")).strip()[:80],
                     "why": str(c.get("why", "")).strip()[:200]})
        if len(out) >= n:
            break
    return out


def fallback_clips(words: list[Word], n: int = 4, target: float = 40.0) -> list[dict]:
    """Sin IA: corta el vídeo largo en trozos de unos 40 s que acaban en final de frase."""
    out, a = [], 0
    for i, w in enumerate(words):
        long_enough = w.end - words[a].start >= target
        if long_enough and (w.text.rstrip()[-1:] in ".?!" or w.end - words[a].start >= target * 1.5):
            out.append({"from": a, "to": i, "title": fallback_hook(words[a:i + 1]), "why": ""})
            a = i + 1
            if len(out) >= n:
                break
    if len(out) < n and a < len(words) and words[-1].end - words[a].start >= 12:
        out.append({"from": a, "to": len(words) - 1, "title": fallback_hook(words[a:]), "why": ""})
    return out


def fallback_hook(words: list[Word], max_words: int = 6) -> str:
    """Sin IA: usa la primera frase del vídeo como título."""
    out = []
    for w in words:
        out.append(w.text)
        if w.text.rstrip()[-1:] in ".?!" or len(out) >= max_words:
            break
    return " ".join(out).rstrip(",.;:")


SETUP_AI = ("La IA incluida de Imán todavía no está activa. Ve a Ajustes › IA que edita, "
            "elige «Mi Claude» y pega tu clave de Claude (empieza por sk-ant-). "
            "Abre «Usar mi propia clave de IA»: ahí tienes la guía paso a paso.")


def error_message(e: Exception) -> str:
    """Lo que le decimos a la persona cuando falla la IA, en vez de un «Error 500»."""
    msg = str(e)
    if type(e).__name__ == "CloudError":
        return SETUP_AI if msg.startswith(("No hay conexión", "El servidor de Imán respondió")) else msg
    origin = type(e).__module__.split(".")[0]
    if origin in ("anthropic", "openai"):
        who = "Claude" if origin == "anthropic" else "ChatGPT"
        low = msg.lower()
        if type(e).__name__ == "AuthenticationError":
            return f"Tu clave de {who} no es válida. Cópiala otra vez en Ajustes › IA que edita."
        if type(e).__name__ == "PermissionDeniedError":
            return f"Tu clave de {who} no tiene permiso. Crea una clave nueva y pégala otra vez."
        if "credit" in low or "billing" in low or "quota" in low:
            return f"Tu cuenta de {who} no tiene saldo. Añade saldo y vuelve a probar."
        if type(e).__name__ == "RateLimitError":
            return f"Tu cuenta de {who} ha llegado a su límite de gasto o de uso. Espera un minuto o sube el límite en tu cuenta."
        if type(e).__name__ in ("APIConnectionError", "APITimeoutError"):
            return f"No hay conexión con {who}. Revisa internet y vuelve a probar."
        return f"{who} ha fallado: {msg[:200]}"
    return f"Algo ha fallado: {msg[:200]}"


KEY_TEST_MODEL = "claude-haiku-5-5"  # la prueba cuesta una milésima de céntimo


def test_key(provider: str, key: str) -> str:
    """Comprueba de verdad que la clave funciona y tiene saldo. Lanza el error de la API si no."""
    key = key.strip()
    if provider == "claude":
        if not key.startswith("sk-ant-"):
            raise ValueError("Esa no es una clave de Claude: tiene que empezar por sk-ant-. "
                             "Ojo, la licencia de Imán (IMAN-…) va en «Tu licencia», no aquí.")
        import anthropic

        anthropic.Anthropic(api_key=key, max_retries=0, timeout=20).messages.create(
            model=KEY_TEST_MODEL, max_tokens=1, messages=[{"role": "user", "content": "hola"}])
        return "Claude"
    if provider == "openai":
        if not key.startswith("sk-"):
            raise ValueError("Esa no es una clave de OpenAI: tiene que empezar por sk-.")
        from openai import OpenAI

        OpenAI(api_key=key, max_retries=0, timeout=20).chat.completions.create(
            model="gpt-4o-mini", max_tokens=1, messages=[{"role": "user", "content": "hola"}])
        return "ChatGPT"
    raise ValueError("Elige Claude o ChatGPT")
