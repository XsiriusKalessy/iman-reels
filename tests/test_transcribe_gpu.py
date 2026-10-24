import numpy as np

from iman import transcribe


def test_falls_back_to_cpu_when_cuda_libs_are_missing(monkeypatch, tmp_path):
    devices = []

    class FakeModel:
        def __init__(self, model, device, compute_type):
            self.device = device
            devices.append(device)

        def transcribe(self, pcm, **kw):
            if self.device == "auto":
                raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
            return [], None

    import faster_whisper
    monkeypatch.setattr(faster_whisper, "WhisperModel", FakeModel)
    monkeypatch.setattr(transcribe, "_pcm", lambda a: np.zeros(16000, dtype=np.float32))
    assert transcribe._local(tmp_path / "a.wav", "es", "tiny") == []
    assert devices == ["auto", "cpu"]
