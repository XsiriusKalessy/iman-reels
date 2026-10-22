# App de escritorio (Mac y Windows)

Imán se instala como una app normal: el creador hace doble clic, se abre el navegador con Imán y
todo el trabajo (vídeo, transcripción, render) pasa en su ordenador.

## Cómo se genera

El flujo `.github/workflows/desktop.yml` lo hace solo:

- al subir una etiqueta de versión (`git tag v0.1.0 && git push --tags`), o
- a mano desde la pestaña **Actions → App de escritorio → Run workflow**.

Genera tres archivos que se descargan desde la ejecución del flujo:

| Archivo | Para |
|---|---|
| `Iman-<versión>-mac-arm64.dmg` | Mac con chip Apple (M1 en adelante) |
| `Iman-<versión>-mac-intel.dmg` | Mac con Intel |
| `Iman-<versión>-Windows.exe` | Instalador de Windows 10/11 |

Cada uno lleva Python, ffmpeg, las fuentes, el modelo de recorte de la persona y la app web. El modelo de
transcripción (Whisper "small", unos 460 MB) se descarga la primera vez que se edita un vídeo.

Para probarlo en local: `pip install ".[recorte]" pyinstaller`, copiar `ffmpeg` y `ffprobe` a
`packaging/bin/` y `pyinstaller packaging/iman.spec`. `dist/Iman/Iman --smoke` comprueba que todo carga.

## Antes de vender: firmar la app

Sin firma, macOS dice "no se puede abrir porque es de un desarrollador no identificado" y Windows enseña
SmartScreen. Funciona (clic derecho → Abrir en Mac, "Más información → Ejecutar igualmente" en Windows), pero
asusta a los compradores. Para quitarlo:

- **Mac**: cuenta de Apple Developer (99 $/año), certificado "Developer ID Application" y notarización.
  Se añaden como secretos del repositorio y un paso de `codesign` + `notarytool` en el flujo.
- **Windows**: certificado de firma de código (unos 200-400 €/año; los de tipo EV quitan SmartScreen
  desde el primer día) o Azure Trusted Signing (unos 10 $/mes).

## Licencia de ffmpeg

La app incluye ffmpeg (compilación GPL, con libass y x264) como programa aparte, que Imán llama por línea de
comandos; no se enlaza con el código de Imán. Para cumplir la GPL hay que acompañarlo de su licencia y de
un enlace a su código fuente (se pondrá en "Acerca de" y en la web). Si en el futuro se quiere evitar del
todo, se puede usar una compilación LGPL y codificar con el H.264 del sistema (VideoToolbox en Mac,
Media Foundation en Windows).
