import pytest

from iman import brand


@pytest.fixture(autouse=True)
def _no_real_brand(tmp_path, monkeypatch):
    """Que ninguna prueba lea ni escriba el kit de marca real del usuario."""
    monkeypatch.setattr(brand, "brand_dir", lambda: tmp_path / "marca")
