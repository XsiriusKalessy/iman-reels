"""Línea de comandos.

  reelia web                         abre la app en el navegador
  reelia editar video.mp4 [opciones] edita un vídeo sin abrir la web
"""

from __future__ import annotations

import argparse
import json
import webbrowser
from pathlib import Path

from . import config, pipeline
from .captions import STYLES
from .rhythm import RHYTHMS


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="reelia", description="Edita tus reels con IA")
    sub = p.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("web", help="Abre la app web local")
    w.add_argument("--port", type=int, default=8765)
    w.add_argument("--no-abrir", action="store_true")

    e = sub.add_parser("editar", help="Edita un vídeo")
    e.add_argument("video", type=Path)
    e.add_argument("-o", "--salida", type=Path, default=None)
    e.add_argument("--ritmo", choices=list(RHYTHMS), default="rapido")
    e.add_argument("--estilo", choices=list(STYLES), default="impacto")
    e.add_argument("--calidad", choices=["1080", "4k"], default="1080")
    e.add_argument("--encuadre", choices=["recortar", "fondo"], default="recortar")
    e.add_argument("--gancho", default="", help="Título del gancho (si no, lo propone la IA)")
    e.add_argument("--sin-gancho", action="store_true")
    e.add_argument("--sin-mejorar-voz", action="store_true", help="No tocar el sonido")
    e.add_argument("--instrucciones", default="", help='Ej.: "quita la parte en la que hablo del precio"')
    e.add_argument("--transcripcion", type=Path, help="JSON con palabras [{text,start,end}] (opcional)")

    args = p.parse_args(argv)

    if args.cmd == "web":
        import uvicorn

        if not args.no_abrir:
            webbrowser.open(f"http://localhost:{args.port}")
        uvicorn.run("reelia.server:app", host="127.0.0.1", port=args.port)
        return

    words = None
    if args.transcripcion:
        from .models import Word

        words = [Word(**w) for w in json.loads(args.transcripcion.read_text())]
    out = args.salida or args.video.with_name(args.video.stem + "-reel.mp4")
    workdir = out.with_suffix("")
    workdir = workdir.parent / (workdir.name + "_trabajo")
    opts = pipeline.EditOptions(
        rhythm=args.ritmo, style=args.estilo, size=args.calidad, fit=args.encuadre,
        hook=not args.sin_gancho, hook_title=args.gancho, instructions=args.instrucciones,
        voice=not args.sin_mejorar_voz,
    )
    res = pipeline.run(args.video, workdir, opts, config.load(),
                       progress=lambda m, pct: print(f"[{pct:4.0%}] {m}"), words=words)
    res.video.replace(out)
    print(f"\nListo: {out}  ({res.duration_in:.1f}s → {res.duration_out:.1f}s, {res.cuts} cortes)")
    if res.plan.hook_title:
        print(f"Gancho: {res.plan.hook_title}")


if __name__ == "__main__":
    main()
