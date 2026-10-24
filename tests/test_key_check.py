from fastapi.testclient import TestClient

from iman import ai, server


def test_wrong_kind_of_key_is_explained(tmp_path, monkeypatch):
    monkeypatch.setenv("IMAN_HOME", str(tmp_path))
    c = TestClient(server.app)
    r = c.post("/api/settings/test-key", json={"provider": "claude", "key": "IMAN-abc.def"}).json()
    assert not r["ok"] and "sk-ant-" in r["message"] and "licencia" in r["message"]
    assert "Pega primero" in c.post("/api/settings/test-key", json={"provider": "claude"}).json()["message"]


def test_api_errors_become_plain_spanish(monkeypatch, tmp_path):
    monkeypatch.setenv("IMAN_HOME", str(tmp_path))

    class AuthenticationError(Exception):
        __module__ = "anthropic._exceptions"

    def boom(provider, key):
        raise AuthenticationError("invalid x-api-key")

    monkeypatch.setattr(ai, "test_key", boom)
    r = TestClient(server.app).post("/api/settings/test-key", json={"provider": "claude", "key": "sk-ant-x"}).json()
    assert not r["ok"] and "no es válida" in r["message"]
