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
               "3 errores que te hacen pagar de más en X", "Lo que no te cuentan antes de ir a X",
               "Ese viaje que llevas años aplazando", "X en 10 segundos", "Lo que incluye de verdad un viaje a X",
               "Por qué en noviembre vamos a X", "Lo que nadie te cuenta del X", "Así es un día de nuestro viaje a X"),
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
    Pack(
        "viajero", "Blogger de viajes", "Vlog, diario, qué ver y presupuesto",
        """PACK BLOGGER DE VIAJES. Un creador o influencer cuenta sus viajes (no vende un paquete). Primero mira qué
formato es y edítalo como tal:
- VLOG (va contando mientras viaja): "ubicacion" en cada sitio nuevo, "apoyo" o "pexels" cortos para respirar,
  "viaje" con coordenadas si pasa por tres o más sitios, y "capitulo" si el día tiene partes claras.
- DIARIO («día 3 en…»): "capitulo" con el día al empezar (text: "Día 3"; subtitle: el sitio) y "lista" con look
  "itinerario" si resume el día.
- QUÉ VER EN X (lista de sitios): "lista" numerada o "tarjetas" con cada sitio, "ubicacion" en cada uno y el
  mejor al final (bucle abierto: anúncialo al principio).
- PRESUPUESTO (cuánto cuesta): "grafico" de barras para comparar gastos (vuelo, hotel, comida), "cifra" o
  "contador" para el total y "precio" para lo más barato o lo más caro. Solo cifras que diga el creador.
El gancho tiene que despertar ganas de ir o ahorrar un error: un sitio concreto, un precio real o un "no hagas
esto". Cierre pidiendo guardar el vídeo para el viaje o comentar el destino siguiente.""",
        style="editorial",
        hooks=("Lo que gasté de verdad en X días en Y", "Qué ver en X si solo tienes un día",
               "Día 1 en X y ya me ha pasado esto", "No vayas a X sin saber esto"),
    ),
    Pack(
        "comida", "Comida", "Recetas, foodies y reseñas",
        """PACK COMIDA. Recetas o reseñas de sitios para comer. Busca:
- "lista" con look "checklist" para los ingredientes; "contador" o "cifra" para tiempos y cantidades.
- "ubicacion" con el nombre del sitio si es una reseña; "precio" si dice lo que cuesta.
- "objeto" con el emoji del plato o ingrediente estrella la primera vez que lo nombra.
- color "calido" para que la comida entre por los ojos.
El gancho, el resultado (el plato terminado o el bocado) o un error que estropea la receta.""",
        style="karaoke",
        hooks=("La receta de X que sale bien a la primera", "El error que hace que tu X quede seco",
               "Probé el X más famoso de Y", "X en 10 minutos y sin horno"),
    ),
    Pack(
        "fitness", "Fitness", "Entrenos, nutrición y hábitos",
        """PACK FITNESS. Entrenos, rutinas o hábitos de salud. Busca:
- "lista" con look "checklist" para los ejercicios (nombre y series o tiempo).
- "contador" para repeticiones, días o kilos; "grafico" si compara antes y después con cifras que dice.
- "capitulo" para cada bloque del entreno (calentamiento, fuerza, estiramientos).
Ritmo rápido, cortes al compás de la música. Nunca prometas resultados de salud que no diga el creador.""",
        style="impacto",
        hooks=("El ejercicio que haces mal sin saberlo", "Rutina de X minutos sin material",
               "Lo que cambió cuando dejé de hacer X", "3 hábitos que me cambiaron más que el gimnasio"),
    ),
    Pack(
        "belleza", "Belleza y moda", "Maquillaje, cuidado y looks",
        """PACK BELLEZA Y MODA. Tutoriales, rutinas de cuidado, looks o probadores. Busca:
- "lista" con look "checklist" para los pasos o los productos (marca y para qué sirve).
- "antes y después": "titular" o "frase" al enseñar el resultado; "foco" en el detalle.
- "precio" si dice lo que cuesta un producto; "objeto" con el emoji de la prenda o el producto.
Color "natural" (piel real), titulares elegantes.""",
        style="elegante",
        hooks=("El paso que te falta en tu rutina de X", "3 looks con la misma prenda",
               "Lo que nadie te dice de X", "Probé el X viral y esto pasó"),
    ),
    Pack(
        "coach", "Coach y mentor", "Mentalidad, negocio y desarrollo",
        """PACK COACH. Mentores, coaches o expertos que enseñan con su historia. Busca:
- "frase" para la idea clave que se quiere guardar; "titular" con look "pizarra" para un concepto.
- "lista" con look "capitulos" para los pasos del método; "dato" para su experiencia (años, personas).
- "testimonio" solo si cita a alguien de verdad.
Tono cercano y seguro. El gancho rompe una creencia ("Nadie te dice que…") o nombra un dolor concreto.""",
        style="caja",
        hooks=("Nadie te dice esto sobre X", "Lo que aprendí después de X años de Y",
               "Si te pasa X, no es falta de ganas", "El error que más se repite en X"),
    ),
    Pack(
        "inmobiliaria", "Inmobiliaria", "Pisos, casas y zonas",
        """PACK INMOBILIARIA. Visitas a viviendas, zonas o consejos de compra y alquiler. Busca:
- "ubicacion" con la zona o el barrio; "precio" con el precio que dice; "dato" para metros, habitaciones o baños.
- "lista" con look "checklist" para lo que tiene la vivienda; "tarjetas" para resumir las claves.
- "cta" al final para pedir visita.
Titulares limpios, look "natural". Nunca inventes precios ni metros.""",
        style="caja",
        hooks=("Esto es lo que te dan por X € en Y", "El piso de X que se va a ir en días",
               "Lo que miro siempre antes de comprar un piso", "3 cosas que nadie revisa en una visita"),
    ),
    Pack(
        "restaurante", "Restaurante", "Platos, carta y local",
        """PACK RESTAURANTE. Un restaurante, bar o cafetería enseña su cocina y su local. Busca:
- "ubicacion" con el nombre y el barrio; "precio" para el menú o un plato; "objeto" con el emoji del plato.
- "lista" con look "checklist" para lo que lleva el menú; "dato" para años o lo que se sirve.
- "cta" al final para reservar o pasar (con el teléfono o la web del negocio).
Look "calido", ritmo de cocina (cortes al compás) y el plato estrella al final.""",
        style="karaoke",
        hooks=("El plato que pide todo el mundo aquí", "Así se hace nuestro X desde las 7 de la mañana",
               "Menú de X € en Y y esto entra", "Lo que no sabías de nuestra cocina"),
    ),
]}

# Viajes primero (agencias y creadores de viajes); los demás nichos detrás.
_ORDER = ["general", "viajes", "viajero"]
PACKS = {k: PACKS[k] for k in _ORDER + [k for k in PACKS if k not in _ORDER]}


def get(key: str) -> Pack:
    return PACKS.get(key or "general", PACKS["general"])
