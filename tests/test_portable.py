import io

from PIL import Image

from iman import brand, config, portable


def _home(monkeypatch, path):
    monkeypatch.setattr(config, "HOME", path)
    monkeypatch.setattr(config, "CONFIG_FILE", path / "config.json")


def test_move_settings_and_brand_to_another_computer(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path / "tienda")
    config.save({"provider": "claude", "anthropic_key": "sk-ant-secreta", "memory": ["Subtítulos grandes"]})
    brand.save(brand.Brand(name="Travel Elenels", primary="#E63A2E", sector="viajes"))
    png = io.BytesIO()
    Image.new("RGB", (40, 40), "#2B59E6").save(png, "PNG")
    brand.set_logo(png.getvalue())
    brand.save(brand.Brand(name="Travel Elenels", primary="#E63A2E", sector="viajes"))

    plain, full = portable.export(False), portable.export(True)
    assert b"sk-ant-secreta" not in plain

    _home(monkeypatch, tmp_path / "casa")
    got = portable.import_(plain)
    assert got["marca"] and got["logo"] and not got["claves"]
    cfg = config.load()
    assert cfg["memory"] == ["Subtítulos grandes"] and cfg["anthropic_key"] == ""
    b = brand.load()
    assert b.name == "Travel Elenels" and b.primary == "#E63A2E" and b.logo_path

    assert portable.import_(full)["claves"]
    assert config.load()["anthropic_key"] == "sk-ant-secreta"


def test_rejects_other_files(monkeypatch, tmp_path):
    _home(monkeypatch, tmp_path)
    try:
        portable.import_(b"no soy un zip")
    except portable.ImportError_ as e:
        assert "no son" in str(e)
    else:
        raise AssertionError
