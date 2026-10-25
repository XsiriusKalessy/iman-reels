"""Perfiles por red: para qué se publica el reel cambia cómo se edita.

- Instagram: lo de siempre.
- TikTok: bucle perfecto (el final enlaza con el principio y el vídeo se repite sin que se note), subtítulos más
  arriba (la zona de abajo la tapa el texto de TikTok) y gancho en el primer segundo.
- YouTube Shorts: tres ganchos para probar, capítulos si el vídeo los tiene y cierre que invita a suscribirse.
- Anuncio: estilo UGC (casero y creíble, subtítulos nativos), copy resaltado tipo VSL y una llamada a la acción
  clara; desde aquí se sacan varias versiones de golpe cambiando gancho y llamada.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Red:
    key: str
    label: str
    description: str
    note: str  # lo que se añade a las instrucciones de la IA
    caption_y: int = 0  # altura máxima del centro de los subtítulos (0 = la del estilo)
    loop: bool = False


REDES = {r.key: r for r in [
    Red("instagram", "Instagram", "Reels de Instagram", ""),
    Red("tiktok", "TikTok", "Bucle perfecto y zonas seguras de TikTok",
        """PERFIL TIKTOK. El vídeo se repite en bucle: busca que la última frase enlace con la primera (por ejemplo,
termina en "y por eso…" o en una pregunta que el principio responde) y quita con "drop" lo que sobre después de
esa frase final (despedidas, "bueno, pues eso"). El gancho tiene que funcionar en el primer segundo. Nada de
llamadas tipo "link en la bio": en TikTok, mejor "sígueme para la parte 2" o una pregunta para comentarios.""",
        caption_y=1240, loop=True),
    Red("youtube", "YouTube Shorts", "Tres ganchos para probar, capítulos y cierre para suscribirse",
        """PERFIL YOUTUBE SHORTS. Propón en "hook_options" tres ganchos distintos (cifra, problema y curiosidad)
para que el creador los pruebe. Si el vídeo tiene partes claras, usa "lista" con look "capitulos". Si al final
invita a algo, que sea a suscribirse o a ver el vídeo largo.""", caption_y=1300),
    Red("anuncio", "Anuncio", "Estilo UGC y VSL: casero, creíble y con llamada a la acción",
        """PERFIL ANUNCIO (UGC / VSL). Tiene que parecer un vídeo grabado por una persona real, no un anuncio:
pocos efectos llamativos (nada de 3D, anillos ni partículas), subtítulos limpios. Resalta el copy que vende con
"titular" o "frase" (el problema, la promesa y la prueba), usa "captura" si enseña resultados y termina siempre
con "cta" (text: la acción concreta, "Reserva tu plaza", "Escríbeme por WhatsApp"). Propón en "hook_options"
tres ganchos distintos para probar el anuncio (dolor, resultado y curiosidad).""", caption_y=1300),
]}

# Efectos que no pegan en un anuncio con estilo casero.
ANUNCIO_FUERA = {"texto3d", "anillo", "particulas", "lluvia", "detras", "fantasma", "color", "choque"}


def get(key: str) -> Red:
    return REDES.get(key) or REDES["instagram"]


def loop(src: Path, dst: Path, blend: float = 0.4) -> Path:
    """Bucle perfecto: los últimos `blend` segundos se funden con el primer fotograma del reel y el sonido se
    apaga justo al final, así al repetirse no hay salto."""
    from .media import FFMPEG, probe

    d = probe(src).duration
    if d < 3 * blend:
        return src
    a = d - blend
    graph = (f"[0:v]split[v][h];[h]trim=end={blend:.3f},setpts=PTS-STARTPTS,format=yuva420p,"
             f"fade=t=in:st=0:d={blend:.3f}:alpha=1,setpts=PTS+{a:.3f}/TB[head];"
             f"[v][head]overlay=eof_action=pass,format=yuv420p[vo];"
             f"[0:a]afade=t=in:d=0.04,afade=t=out:st={d - 0.25:.3f}:d=0.25[ao]")
    subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(src), "-filter_complex", graph, "-map", "[vo]", "-map",
                    "[ao]", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dst)], check=True)
    return dst
