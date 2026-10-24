"""Packs por sector: lo que la IA debe buscar en el vídeo y los efectos que encajan con cada negocio.

El creador elige su sector una vez (o por reel) y la IA ya sabe que en un reel de viajes
el destino lleva chincheta, el precio va en una oferta y el itinerario se cuenta por días.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Pack:
    key: str
    label: str
    description: str
    guide: str  # lo que se añade a las instrucciones de la IA
    style: str = ""  # estilo de subtítulos recomendado
    hooks: tuple[str, ...] = field(default_factory=tuple)


PACKS = {p.key: p for p in [
    Pack(
        "general", "General", "Para cualquier tema",
        "",
    ),
    Pack(
        "viajes", "Viajes", "Destinos y ofertas",
        """PACK VIAJES. El creador vende o cuenta viajes. Además de los efectos de siempre, busca:
- "ubicacion" la primera vez que nombra el destino o un sitio concreto (text: el lugar; subtitle: país o zona).
- "oferta" si dice un precio o una promoción (text: destino; subtitle: el precio tal cual, "desde 899 €";
  title: lo que incluye en pocas palabras, "7 noches · vuelo + hotel").
- "lista" con look "itinerario" si cuenta el viaje por días o etapas (un punto por día, 2 a 4 palabras).
- "ruta" si dice de dónde a dónde se viaja (text: origen; subtitle: destino; title: duración o vacío).
- "viaje" (el mapa 3D, con coordenadas de cada parada) si nombra el recorrido con tres o más sitios: es el
  efecto estrella del pack, úsalo siempre que el creador cuente por dónde pasa el viaje.
- "cta" al final si invita a escribir o reservar.
El gancho debe despertar ganas de viajar: un lugar concreto, un precio sorprendente o un secreto del destino.""",
        style="editorial",
        hooks=("El destino que nadie te recomienda y deberías ver", "Así es viajar a X por menos de Y €",
               "3 errores que te hacen pagar de más en X", "Lo que no te cuentan antes de ir a X"),
    ),
    Pack(
        "cursos", "Cursos", "Formación y coaching",
        """PACK CURSOS. El creador enseña o vende formación. Además de los efectos de siempre, busca:
- "lista" con look "capitulos" si recorre módulos o pasos del método.
- "testimonio" si cita lo que dijo un alumno (text: la frase del alumno, máx. 100 caracteres;
  subtitle: nombre y qué es, "Laura, alumna").
- "plazas" si habla de plazas, fechas límite o cupos (text: la frase corta, "Solo 7 plazas").
- "cifra" o "dato" para resultados de alumnos.
- "cta" al final si pide comentar una palabra para recibir información.
El gancho debe prometer un resultado concreto o señalar un error común del alumno.""",
        style="karaoke",
        hooks=("El error que te impide aprender X", "Lo que aprendí después de enseñar X a 500 personas",
               "Si quieres X, empieza por aquí", "Nadie te enseña esto sobre X"),
    ),
    Pack(
        "productos", "Productos", "Tiendas y marcas",
        """PACK PRODUCTOS. El creador enseña o vende un producto. Además de los efectos de siempre, busca:
- "precio" si dice el precio o un descuento (text: precio nuevo, "39 €"; subtitle: precio anterior,
  "59 €", o vacío; title: la etiqueta, "-30%" u "Oferta").
- "lista" con look "checklist" para las ventajas o lo que incluye.
- "testimonio" si cita a un cliente.
- "plazas" si hay unidades limitadas o la oferta acaba pronto (text: "Últimas 20 unidades").
- "cta" al final si pide comentar para recibir el enlace.
El gancho debe enseñar el problema que resuelve el producto o el resultado, no el producto en sí.""",
        style="impacto",
        hooks=("Esto ha cambiado mi forma de X", "Por qué todo el mundo está comprando X",
               "Lo que nadie te dice antes de comprar X", "Probé X durante 30 días"),
    ),
    Pack(
        "empresas", "Empresas", "Servicios y negocios",
        """PACK EMPRESAS. Un negocio presenta su servicio. Además de los efectos de siempre, busca:
- "dato" o "cifra" para años de experiencia, clientes o resultados.
- "lista" con look "checklist" para lo que incluye el servicio.
- "testimonio" si cita a un cliente.
- "ubicacion" si dice dónde está el negocio.
- "cta" al final si invita a escribir, llamar o reservar.
Tono profesional y cercano: titulares limpios (look "elegante" o "pizarra"), sin abusar de golpes de color.""",
        style="caja",
        hooks=("Lo que hacemos distinto en X", "Por qué nuestros clientes repiten",
               "La pregunta que más nos hacen sobre X", "Así trabajamos un X de principio a fin"),
    ),
]}


def get(key: str) -> Pack:
    return PACKS.get(key or "general", PACKS["general"])
