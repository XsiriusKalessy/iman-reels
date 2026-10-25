from fastapi.testclient import TestClient

from iman import ai, cloud, config, server


def test_cloud_down_says_what_to_set_up(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.setattr(config, "load", lambda: {**config.DEFAULTS, "provider": "iman"})

    def down(*a, **k):
        raise cloud.CloudError("No hay conexión con el servidor de Imán", 0, licensed=False)

    monkeypatch.setattr(cloud, "call", down)
    r = TestClient(server.app, raise_server_exceptions=False).post("/api/ideas", json={"topic": "Japón", "audience": "grupo"})
    assert r.status_code == 500
    assert "Mi Claude" in r.json()["detail"]


def test_own_key_wins_over_included_ai():
    cfg = config.ai_config({**config.DEFAULTS, "provider": "iman", "anthropic_key": "sk-ant-x"})
    assert cfg.provider == "claude"
    assert config.ai_config({**config.DEFAULTS, "provider": "iman"}).provider == "iman"


def test_messages_for_ai_errors():
    class AuthenticationError(Exception):
        __module__ = "anthropic._exceptions"

    assert "no es válida" in ai.error_message(AuthenticationError("bad key"))
    assert ai.error_message(cloud.CloudError("Licencia no válida o caducada", 403)) == ai.SETUP_AI
    assert ai.error_message(cloud.CloudError("Límite", 429)) == "Límite"
    # Con licencia y sin red: no se manda a la persona a pagar su propia clave, se le dice que es la conexión
    assert "Revisa internet" in ai.error_message(cloud.CloudError("No hay conexión con el servidor de Imán", 0))
    assert "no responde" in ai.error_message(cloud.CloudError("El servidor de Imán respondió 502", 502))
    assert ai.humanize("Japón 18–29 nov — con Elena") == "Japón 18–29 nov, con Elena"
