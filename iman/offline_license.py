"""Licencias firmadas sin servidor: para el dueño, la beta y regalos.

Una licencia es `IMAN-<datos>.<firma>` en base64url. Los datos son un JSON
({"n": nombre, "exp": "AAAA-MM-DD" o "", "p": plan opcional}) y la firma es Ed25519 con la clave
privada de Imán, que NO está en el repositorio. La app solo lleva la pública,
así que nadie puede fabricar licencias.

Ed25519 sigue la implementación de referencia de la RFC 8032 (sección 6), en
Python puro para no añadir dependencias. Es lenta, pero solo verifica una
firma al activar y una vez al día.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time

PREFIX = "IMAN-"
PUBLIC_KEY = bytes.fromhex("21c226b55db850617df6c5a0dedb3e8743a65d7a3961d2040900d7b439fd43b3")

# ---------- Ed25519 (RFC 8032, sección 6) ----------
_p = 2**255 - 19
_d = -121665 * pow(121666, _p - 2, _p) % _p
_q = 2**252 + 27742317777372353535851937790883648493
_I = pow(2, (_p - 1) // 4, _p)


def _sha512(s: bytes) -> int:
    return int.from_bytes(hashlib.sha512(s).digest(), "little")


def _add(P, Q):
    A, B = (P[1] - P[0]) * (Q[1] - Q[0]) % _p, (P[1] + P[0]) * (Q[1] + Q[0]) % _p
    C, D = 2 * P[3] * Q[3] * _d % _p, 2 * P[2] * Q[2] % _p
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F, G * H, F * G, E * H)


def _mul(s: int, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _add(Q, P)
        P = _add(P, P)
        s >>= 1
    return Q


def _equal(P, Q) -> bool:
    return (P[0] * Q[2] - Q[0] * P[2]) % _p == 0 and (P[1] * Q[2] - Q[1] * P[2]) % _p == 0


def _recover_x(y: int, sign: int):
    if y >= _p:
        return None
    x2 = (y * y - 1) * pow(_d * y * y + 1, _p - 2, _p)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_p + 3) // 8, _p)
    if (x * x - x2) % _p != 0:
        x = x * _I % _p
    if (x * x - x2) % _p != 0:
        return None
    if (x & 1) != sign:
        x = _p - x
    return x


_gy = 4 * pow(5, _p - 2, _p) % _p
_gx = _recover_x(_gy, 0)
_G = (_gx, _gy, 1, _gx * _gy % _p)


def _compress(P) -> bytes:
    zinv = pow(P[2], _p - 2, _p)
    x, y = P[0] * zinv % _p, P[1] * zinv % _p
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(s: bytes):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign, y = y >> 255, y & ((1 << 255) - 1)
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _p)


def _expand(secret: bytes) -> tuple[int, bytes]:
    h = hashlib.sha512(secret).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_from_secret(secret: bytes) -> bytes:
    return _compress(_mul(_expand(secret)[0], _G))


def sign(secret: bytes, msg: bytes) -> bytes:
    a, prefix = _expand(secret)
    A = _compress(_mul(a, _G))
    r = _sha512(prefix + msg) % _q
    R = _compress(_mul(r, _G))
    s = (r + _sha512(R + A + msg) * a) % _q
    return R + int.to_bytes(s, 32, "little")


def verify(public: bytes, msg: bytes, signature: bytes) -> bool:
    if len(public) != 32 or len(signature) != 64:
        return False
    A, R = _decompress(public), _decompress(signature[:32])
    if not A or not R:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _q:
        return False
    h = _sha512(signature[:32] + public + msg) % _q
    return _equal(_mul(s, _G), _add(R, _mul(h, A)))


# ---------- licencias ----------
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def is_offline(key: str) -> bool:
    return key.strip().startswith(PREFIX)


def issue(secret: bytes, name: str, expires: str = "", plan: str = "") -> str:
    """`plan`: "" (la normal), "pro" o "dueno" (todo desbloqueado y sin límites de IA)."""
    info = {"n": name, "exp": expires, **({"p": plan} if plan else {})}
    data = json.dumps(info, ensure_ascii=False, separators=(",", ":")).encode()
    return f"{PREFIX}{_b64(data)}.{_b64(sign(secret, data))}"


def read(key: str, public: bytes | None = None) -> dict | None:
    """Los datos de la licencia si la firma es buena y no ha caducado; si no, None."""
    try:
        body, sig = key.strip()[len(PREFIX):].split(".")
        data = _unb64(body)
        if not verify(public or PUBLIC_KEY, data, _unb64(sig)):
            return None
        info = json.loads(data)
    except (ValueError, TypeError):
        return None
    if info.get("exp") and info["exp"] < time.strftime("%Y-%m-%d"):
        return None
    return info
