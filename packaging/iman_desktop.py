"""Arranque de la app de escritorio: levanta Imán en local y abre el navegador.

Si Imán ya está abierto, solo abre otra pestaña en vez de arrancar un segundo servidor.
"""

from __future__ import annotations

import socket
import sys
import threading
import time
import urllib.request
import webbrowser

PORT = 8765


def _running(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/options", timeout=1) as r:
            return r.status == 200
    except OSError:
        return False


def _free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def _fix_streams() -> None:
    """En la app de ventana (sin consola) Windows deja stdout y stderr a None y uvicorn, tqdm y
    cualquier print revientan. Los mandamos a un registro en ~/.iman para poder ver qué pasó."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    from iman.config import HOME

    try:
        HOME.mkdir(parents=True, exist_ok=True)
        log = open(HOME / "registro.txt", "a", encoding="utf-8", buffering=1)
    except OSError:
        import os

        log = open(os.devnull, "w", encoding="utf-8")
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log


def main() -> None:
    _fix_streams()
    port = PORT
    if _running(port):
        webbrowser.open(f"http://localhost:{port}")
        return
    while not _free(port):
        port += 1
    import uvicorn

    from iman.server import app

    def open_when_ready():
        for _ in range(100):
            if _running(port):
                webbrowser.open(f"http://localhost:{port}")
                return
            time.sleep(0.2)

    threading.Thread(target=open_when_ready, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    if "--smoke" in sys.argv:  # comprobación en CI: importa todo y sale
        from iman import media, segment, server  # noqa: F401

        import mediapipe  # noqa: F401  (falla aquí si el recorte no viene en el paquete)

        # Como en la app de ventana de Windows: sin stdout ni stderr, el servidor tiene que arrancar igual.
        out, sys.stdout, sys.stderr = sys.stdout, None, None
        _fix_streams()
        import uvicorn

        uvicorn.Config(server.app, host="127.0.0.1", port=PORT, log_level="warning").configure_logging()
        print("ok", media.FFMPEG, segment.available(), file=out)
    else:
        main()
