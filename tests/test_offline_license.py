import os

from iman import license, offline_license as o


def test_signed_licence_roundtrip(monkeypatch):
    sk = os.urandom(32)
    pk = o.public_from_secret(sk)
    monkeypatch.setattr(o, "PUBLIC_KEY", pk)
    key = o.issue(sk, "Prueba")
    assert o.read(key) == {"n": "Prueba", "exp": ""}
    data = license.activate(key)
    assert data["license_valid"] and license.validate(data)["license_valid"]
    assert license.can_edit(data) == (True, False)


def test_forged_or_expired_licences_fail(monkeypatch):
    sk = os.urandom(32)
    monkeypatch.setattr(o, "PUBLIC_KEY", o.public_from_secret(sk))
    other = o.issue(os.urandom(32), "Pirata")
    assert o.read(other) is None
    assert o.read(o.issue(sk, "Vieja", "2020-01-01")) is None
    body, sig = o.issue(sk, "Ana").split(".")
    assert o.read(body[:-2] + "xx." + sig) is None
