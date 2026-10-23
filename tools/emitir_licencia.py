"""Emite una licencia firmada de Imán (para ti, la beta o regalos).

    python tools/emitir_licencia.py RUTA_CLAVE_PRIVADA "Nombre" [AAAA-MM-DD]

La clave privada vive fuera del repositorio. Sin fecha, la licencia no caduca.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from iman import offline_license  # noqa: E402

secret = bytes.fromhex(Path(sys.argv[1]).read_text().split()[-1])
if offline_license.public_from_secret(secret) != offline_license.PUBLIC_KEY:
    sys.exit("Esa clave privada no es la de Imán")
key = offline_license.issue(secret, sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
assert offline_license.read(key)
print(key)
