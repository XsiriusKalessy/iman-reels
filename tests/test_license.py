"""Licencias, prueba gratis y la IA incluida (sin red: todo simulado)."""

import time

import pytest
from fastapi.testclient import TestClient

from iman import ai, cloud, config, license

from .test_core import TAKE


@pytest.fixture
def cfg_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(config, "HOME", tmp_path)
    monkeypatch.delenv("IMAN_DEV", raising=False)
    return tmp_path / "config.json"


def test_trial_then_blocked():
    cfg = dict(config.DEFAULTS)
    assert license.can_edit(cfg) == (True, True)
    cfg["free_reels_used"] = license.FREE_REELS
    assert license.can_edit(cfg) == (False, True)
    cfg.update(license_key="K", license_valid=True)
    assert license.can_edit(cfg) == (True, False)


def test_activate_and_validate(monkeypatch):
    calls = []

    def fake_post(action, fields):
        calls.append(action)
        if action == "activate":
            return {"activated": True, "instance": {"id": "inst1"},
                    "license_key": {"expires_at": "2027-10-21"}, "meta": {"product_id": 7}}
        return {"valid": False, "license_key": {"status": "expired"}, "meta": {"product_id": 7}}

    monkeypatch.setattr(license, "_post", fake_post)
    monkeypatch.setattr(license, "PRODUCT_ID", "7")
    data = license.activate(" K-123 ")
    assert data["license_key"] == "K-123" and data["license_instance"] == "inst1" and data["license_valid"]

    # Recién comprobada: no vuelve a preguntar.
    assert license.validate(data) == {}
    data["license_checked"] = 0
    assert license.validate(data)["license_valid"] is False
    assert calls == ["activate", "validate"]


def test_key_from_other_product_is_rejected(monkeypatch):
    monkeypatch.setattr(license, "_post", lambda a, f: {"activated": True, "meta": {"product_id": 99}})
    monkeypatch.setattr(license, "PRODUCT_ID", "7")
    with pytest.raises(license.LicenseError):
        license.activate("K")


def test_offline_grace(monkeypatch):
    def offline(action, fields):
        raise license.LicenseError("sin red")

    monkeypatch.setattr(license, "_post", offline)
    recent = {"license_key": "K", "license_checked": time.time() - 3 * 86400}
    assert license.validate(recent) == {}
    old = {"license_key": "K", "license_checked": time.time() - 30 * 86400}
    assert license.validate(old) == {"license_valid": False}


def test_server_blocks_after_trial(cfg_file):
    from iman import server

    config.save({"free_reels_used": license.FREE_REELS})
    c = TestClient(server.app)
    r = c.post("/api/jobs", files={"video": ("a.mp4", b"x", "video/mp4")})
    assert r.status_code == 402
    assert c.get("/api/settings").json()["license"]["free_left"] == 0


def test_server_license_endpoints(cfg_file, monkeypatch):
    from iman import server

    monkeypatch.setattr(license, "activate", lambda key: {"license_key": key, "license_instance": "i",
                                                          "license_valid": True, "license_checked": time.time()})
    monkeypatch.setattr(license, "deactivate", lambda cfg: None)
    c = TestClient(server.app)
    s = c.post("/api/license", json={"key": "K-1"}).json()
    assert s["license"]["licensed"] and "license_key" not in s
    s = c.delete("/api/license").json()
    assert not s["license"]["licensed"]


def test_included_ai_goes_through_cloud(monkeypatch):
    sent = {}

    def fake_call(cfg, endpoint, payload):
        sent.update(endpoint=endpoint, key=cfg.license_key, n=len(payload["words"]))
        return {"hook_title": "Gancho", "hook_line": "", "drop": [], "emphasis": [], "effects": [], "zooms": []}

    monkeypatch.setattr(cloud, "call", fake_call)
    plan = ai.plan_edit(ai.AIConfig(provider="iman", license_key="K"), TAKE)
    assert plan.hook_title == "Gancho" and plan.source == "iman"
    assert sent == {"endpoint": "plan", "key": "K", "n": len(TAKE)}


def test_cloud_server_checks_license_and_limits(monkeypatch):
    from iman_cloud import app as cloud_app

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(cloud_app, "TRIAL_LIMIT", 1)
    monkeypatch.setattr(cloud_app, "_usage", {})
    monkeypatch.setattr(cloud_app, "_valid_until", {})
    monkeypatch.setattr(ai, "plan_edit_raw", lambda *a: {"hook_title": "ok"})
    monkeypatch.setattr(license, "validate", lambda cfg: {"license_valid": cfg["license_key"] == "BUENA"})
    c = TestClient(cloud_app.app)
    words = [w.__dict__ for w in TAKE]

    assert c.post("/v1/plan", json={"words": words}).json() == {"hook_title": "ok"}
    assert c.post("/v1/plan", json={"words": words}).status_code == 429  # prueba agotada
    assert c.post("/v1/plan", json={"words": words}, headers={"X-Iman-License": "MALA"}).status_code == 403
    assert c.post("/v1/plan", json={"words": words}, headers={"X-Iman-License": "BUENA"}).status_code == 200
    too_long = words * (cloud_app.MAX_WORDS // len(words) + 1)
    assert c.post("/v1/plan", json={"words": too_long}, headers={"X-Iman-License": "BUENA"}).status_code == 413
