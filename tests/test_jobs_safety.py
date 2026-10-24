"""Dos montajes a la vez del mismo reel no se pisan, y un cambio que falla no se lleva el reel hecho."""

import pytest
from fastapi import HTTPException

from iman import server


def test_claim_blocks_a_second_edit(monkeypatch):
    monkeypatch.setitem(server.JOBS, "j1", {"id": "j1", "status": "done", "options": {"style": "auto"}})
    server._claim("j1", step="Aplicando cambios", options={"style": "hormozi"})
    assert server.JOBS["j1"]["status"] == "working" and server.JOBS["j1"]["prev_options"] == {"style": "auto"}
    with pytest.raises(HTTPException) as e:
        server._claim("j1")
    assert e.value.status_code == 409


def test_failed_change_keeps_previous_reel(tmp_path, monkeypatch):
    monkeypatch.setitem(server.JOBS, "j2", {"id": "j2", "status": "working", "options": {"style": "hormozi"},
                                            "prev_options": {"style": "auto"}, "result": {"video": "reel.mp4"}})
    monkeypatch.setattr(server, "_save_job", lambda job: None)

    def boom(*a, **k):
        raise RuntimeError("ffmpeg falló: [h264 @ 0x1] Invalid NAL unit size (752295479 > 28708)")

    monkeypatch.setattr(server.pipeline, "run", boom)
    server._work("j2", tmp_path / "x.mp4", tmp_path, server.pipeline.EditOptions())
    job = server.JOBS["j2"]
    assert job["status"] == "done" and job["options"] == {"style": "auto"}
    assert "NAL" not in job["result"]["notices"][0] and "No he podido" in job["result"]["notices"][0]
    assert (tmp_path / "error.log").exists()
