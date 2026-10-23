import subprocess

from iman import media, transcribe


def test_audio_is_decoded_without_pyav(tmp_path):
    wav = tmp_path / "t.wav"
    subprocess.run([media.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=d=1.5", str(wav)], check=True)
    pcm = transcribe._pcm(wav)
    assert pcm.dtype.name == "float32"
    assert abs(len(pcm) - 1.5 * transcribe.SAMPLE_RATE) < 400
