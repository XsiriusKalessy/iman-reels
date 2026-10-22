from iman import updates

ASSETS = [
    {"name": "Iman-0.2.0-Windows.exe", "browser_download_url": "https://x/w.exe", "size": 10},
    {"name": "Iman-v0.2.0-mac-arm64.dmg", "browser_download_url": "https://x/a.dmg", "size": 10},
    {"name": "Iman-v0.2.0-mac-intel.dmg", "browser_download_url": "https://x/i.dmg", "size": 10},
]


def rel(tag="v0.2.0", published="2026-11-01T00:00:00Z"):
    return {"tag_name": tag, "assets": ASSETS, "body": "Novedades", "published_at": published}


def test_versions_compare():
    assert updates.parse_version("v0.10.0") > updates.parse_version("0.9.9")
    assert updates.parse_version("0.1.0-dev") == (0, 1, 0)


def test_picks_the_installer_for_this_machine():
    assert updates.asset_for(ASSETS, "Windows", "AMD64")["name"].endswith(".exe")
    assert "arm64" in updates.asset_for(ASSETS, "Darwin", "arm64")["name"]
    assert "intel" in updates.asset_for(ASSETS, "Darwin", "x86_64")["name"]
    assert updates.asset_for(ASSETS, "Linux", "x86_64") is None


def test_check_offers_newer_versions_covered_by_the_licence(monkeypatch):
    monkeypatch.setattr(updates.platform, "system", lambda: "Windows")
    trial = {"license_valid": False}
    assert updates.check(trial, rel(), "0.1.0")["available"]
    assert updates.check(trial, rel(), "0.1.0")["covered"]
    assert not updates.check(trial, rel("v0.1.0"), "0.1.0")["available"]
    expired = {"license_valid": True, "license_key": "k", "license_expires": "2026-10-30T00:00:00Z"}
    info = updates.check(expired, rel(), "0.1.0")
    assert info["available"] and not info["covered"]
    renewed = {**expired, "license_expires": "2027-10-30T00:00:00Z"}
    assert updates.check(renewed, rel(), "0.1.0")["covered"]


def test_no_release_means_nothing_to_show():
    monkeypatch_free = updates.check({}, {}, "0.1.0")
    assert monkeypatch_free == {"current": "0.1.0", "available": False}
