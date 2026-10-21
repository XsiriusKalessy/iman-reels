# Imán

Edita tus reels con IA. Subes una toma en bruto grabada con el móvil y Imán te devuelve un reel vertical listo para publicar:

- **Quita los fallos**: silencios, muletillas ("eh", "em") y tomas falsas (frases que empiezas y repites).
- **Ritmo a elegir**: Rápido (recomendado), Dinámico, Natural o Sin tocar.
- **Gancho**: título grande en los primeros segundos. Lo escribes tú, eliges una plantilla o lo propone la IA.
- **Subtítulos animados** con la palabra activa resaltada. Estilos: Impacto, Editorial, Palabra a palabra y Neón.
- **Dímelo como a tu editor**: instrucciones en lenguaje normal ("quita la parte del precio", "resalta «gratis»").
- **Mejora la voz**: menos ruido de fondo y volumen estable.
- **Formato vertical** 1080×1920 o 4K a 30 fps, recortando o con fondo desenfocado. Convierte el HDR del iPhone a SDR.
- **Agente de ideas** (paso 0): gancho y guion corto para grabar en una toma, aprendiendo de cómo hablas en tus reels anteriores.
- **Tu propia IA**: Claude o ChatGPT con tu clave. Sin clave también funciona (cortes y subtítulos, sin gancho inteligente).

## Instalar

Necesitas Python 3.10+ y [ffmpeg](https://ffmpeg.org/download.html).

```bash
git clone https://github.com/XsiriusKalessy/iman-reels.git
cd iman-reels
python -m venv .venv && source .venv/bin/activate   # en Windows: .venv\Scripts\activate
pip install -e .
```

## Usar

```bash
iman web
```

Se abre http://localhost:8765. En **Ajustes** eliges Claude o ChatGPT y pegas tu clave (se guarda solo en tu ordenador, en `~/.iman/config.json`). La primera vez que edites se descarga el modelo de transcripción (unos 500 MB).

También desde la terminal:

```bash
iman editar toma.mp4 --ritmo rapido --estilo editorial --instrucciones "resalta los números"
```

Las claves también se pueden pasar con `ANTHROPIC_API_KEY` u `OPENAI_API_KEY`.

## Cómo funciona

1. **Transcripción** palabra a palabra con Whisper (`faster-whisper` en local, o la API de OpenAI).
2. **Plan de edición**: Claude (o ChatGPT) lee la transcripción numerada y devuelve qué rangos quitar, el gancho y las palabras clave. Sin IA, una heurística detecta las repeticiones.
3. **Ritmo**: con los tiempos de cada palabra se calculan los tramos a conservar según el ritmo elegido.
4. **Montaje** con ffmpeg: cortes con microfundidos de audio, formato vertical, subtítulos ASS animados (libass), limpieza de voz y normalización a -14 LUFS.

## Hoja de ruta

- Fase 2: chat de edición sobre el reel ya montado, efectos (texto detrás de la persona, listas animadas, anillo de texto) e imágenes de apoyo.
- Fase 3: Clipper. De un directo o podcast saca varios reels, cada uno con su gancho y una nota de viralidad explicada.
- Fase 4: Kit. Portada, carrusel y stories con tu marca.

## Tests

```bash
pip install -e ".[dev]" && pytest
```

Las fuentes de `iman/assets/fonts` son de Google Fonts, con licencia SIL OFL 1.1 (ver los `OFL-*.txt`).
