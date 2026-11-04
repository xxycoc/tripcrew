from io import BytesIO
import wave


def test_installed_whisper_can_decode_and_resample_audio():
    from faster_whisper.audio import decode_audio

    audio = BytesIO()
    with wave.open(audio, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(b"\x00\x00" * 800)
    audio.seek(0)
    decoded = decode_audio(audio, sampling_rate=16000)
    assert decoded.size == 1600
    assert (decoded == 0).all()
