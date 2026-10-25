"""Emite una licencia firmada de Imán (para ti, la beta o regalos).

    python tools/emitir_licencia.py RUTA_CLAVE_PRIVADA "Nombre" [AAAA-MM-DD] [--plan pro|dueno]

La clave privada vive fuera del repositorio. Sin fecha (o con "-"), la licencia no caduca.
--plan dueno: todo desbloqueado, también lo Pro, y sin límite diario de IA en el servidor de Imán.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from iman import offline_license  # noqa: E402

args = sys.argv[1:]
plan = ""
if "--plan" in args:
    i = args.index("--plan")
    plan = args[i + 1]
    del args[i:i + 2]
sys.argv[1:] = args
secret = bytes.fromhex(Path(sys.argv[1]).read_text().split()[-1])
if offline_license.public_from_secret(secret) != offline_license.PUBLIC_KEY:
    sys.exit("Esa clave privada no es la de Imán")
exp = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "-" else ""
key = offline_license.issue(secret, sys.argv[2], exp, plan)
assert offline_license.read(key)
print(key)
