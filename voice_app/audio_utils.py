import subprocess
import tempfile
import wave
import os

def convert_to_wav(input_path: str):
    """Convert bất kỳ định dạng → WAV 16kHz mono, tối ưu cho STT (ElevenLabs Scribe v2).
    
    Filter chain:
    - highpass f=80   : loại bỏ rumble, tiếng ồn tần số thấp (điều hòa, engine...)
    - lowpass f=8000  : loại bỏ sibilance, noise tần số cao ngoài dải giọng người
    - afftdn nf=-25   : AI noise reduction (FFT denoiser) - khử tiếng phòng, gió
    - dynaudnorm       : dynamic normalization - cân bằng âm lượng linh hoạt hơn loudnorm
    """
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out = f.name
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        "-af", (
            "highpass=f=80,"          # cắt tần số thấp (noise phòng, điều hòa)
            "lowpass=f=8000,"         # cắt tần số cao (ngoài dải giọng người)
            "afftdn=nf=-25,"          # AI FFT denoiser: khử noise nền
            "dynaudnorm=p=0.9:m=100"  # dynamic normalization: không clip, giữ ngữ điệu
        ),
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


def concat_speaker_segments(wav_path: str, segs: list,
                            max_total_sec: float = 25.0,
                            min_seg_sec: float = 1.0) -> str:
    """
    Ghép nhiều đoạn của cùng 1 speaker thành 1 file WAV liên tục.

    Chiến lược:
    - Sắp xếp segments theo độ dài (dài trước)
    - Chọn các đoạn >= min_seg_sec cho đến khi đủ max_total_sec
    - Ghép bằng ffmpeg concat → 1 file WAV để extract embedding tốt hơn

    Returns: path WAV tạm, hoặc None nếu không có đoạn nào đủ dài.
    """
    duration = get_duration(wav_path)

    # Lọc & sắp xếp: ưu tiên đoạn dài, bỏ đoạn quá ngắn
    candidates = sorted(
        [s for s in segs if (s["end"] - s["start"]) >= min_seg_sec],
        key=lambda x: x["end"] - x["start"],
        reverse=True
    )
    if not candidates:
        return None

    # Cắt từng segment thành file tạm, gom đủ max_total_sec
    tmp_files = []
    total = 0.0
    for seg in candidates:
        seg_start = max(0.0, seg["start"] - 0.1)
        seg_end   = min(duration, seg["end"] + 0.1)
        take      = min(seg_end - seg_start, max_total_sec - total)
        if take < min_seg_sec:
            break

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp = f.name
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{seg_start:.3f}", "-i", wav_path,
            "-t", f"{take:.3f}",
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
            tmp,
        ]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode == 0:
            tmp_files.append(tmp)
            total += take
        if total >= max_total_sec:
            break

    if not tmp_files:
        return None

    # Nếu chỉ có 1 đoạn → trả thẳng luôn
    if len(tmp_files) == 1:
        return tmp_files[0]

    # Ghép nhiều đoạn bằng ffmpeg concat
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as lf:
        list_file = lf.name
        for p in tmp_files:
            lf.write(f"file '{p}'\n")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out = f.name

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        out,
    ]
    r = subprocess.run(cmd, capture_output=True)

    # Dọn tmp files
    for p in tmp_files:
        try: os.remove(p)
        except: pass
    try: os.remove(list_file)
    except: pass

    return out if r.returncode == 0 else None
