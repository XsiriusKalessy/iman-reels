"""Las canciones de Suno que trae Imán: se listan, se escuchan y el montaje las usa como «tu música»."""
from pathlib import Path

from iman import musica, pipeline


def test_todas_las_canciones_estan():
    for key in musica.CANCIONES:
        p = musica.cancion(key)
        assert p is not None and p.suffix == ".mp3" and p.stat().st_size > 100_000, key


def test_el_montaje_usa_la_cancion(tmp_path: Path):
    key = next(iter(musica.CANCIONES))
    assert pipeline._music(key, tmp_path, 20.0) == musica.cancion(key)
    assert musica.cancion("lib-no-existe") is None
