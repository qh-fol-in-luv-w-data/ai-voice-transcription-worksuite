import subprocess
import tempfile
import wave
import os

def convert_to_wav(input_path: str):
    """Convert bất kỳ định dạng → WAV 16kHz mono, normalize âm lượng."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out = f.name
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        out,
    ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        return None, f"ffmpeg error: {r.stderr.decode(errors='ignore')}"
    return out, None

def get_duration(wav_path: str) -> float:
    with wave.open(wav_path, "rb") as wf:
        return wf.getnframes() / wf.getframerate()

def extract_segment_ffmpeg(wav_path: str, start: float, end: float, padding: float = 0.5) -> str:
    """Cắt đoạn [start, end] giây từ file WAV."""
    duration = get_duration(wav_path)
    padded_start = max(0.0, start - padding)
    padded_end   = min(duration, end + padding)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out = f.name
    # Bỏ loudnorm ở đây để tránh lỗi header trên các đoạn ngắn
    cmd = [
        "ffmpeg", "-y", "-ss", f"{padded_start:.3f}", 
        "-i", wav_path,
        "-t", f"{padded_end - padded_start:.3f}",
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        "-af", "volume=2.5",
        out,
    ]
    subprocess.run(cmd, capture_output=True)
    return out
