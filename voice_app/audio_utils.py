import subprocess
import tempfile
import wave
import os

def convert_to_wav(input_path: str):
    """Convert bất kỳ định dạng → WAV 16kHz mono cho ElevenLabs STT."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out = f.name
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        out,
    ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        try: os.remove(out)
        except: pass
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

    if r.returncode != 0:
        try: os.remove(out)
        except: pass
        return None
    return out

def split_audio_by_silence(wav_path: str, chunk_length_sec: float = 900.0, max_chunk_sec: float = 1200.0) -> list:
    """
    Chia file âm thanh thành các chunk dựa trên khoảng lặng.
    Mục tiêu là mỗi chunk dài khoảng `chunk_length_sec` (mặc định 15 phút),
    tối đa `max_chunk_sec` (20 phút).
    Trả về danh sách các tuple: [(chunk_wav_path, start_time_offset), ...]
    """
    import re
    duration = get_duration(wav_path)
    if duration <= max_chunk_sec:
        # Nếu file ngắn hơn max_chunk, không cần chia
        return [(wav_path, 0.0)]
        
    cmd = [
        "ffmpeg", "-i", wav_path,
        "-af", "silencedetect=noise=-30dB:d=0.5",
        "-f", "null", "-"
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    
    silences = []
    for line in r.stderr.splitlines():
        if "silence_start" in line:
            m = re.search(r"silence_start:\s+([\d\.]+)", line)
            if m: silences.append({"start": float(m.group(1))})
        elif "silence_end" in line:
            m = re.search(r"silence_end:\s+([\d\.]+)", line)
            if m and silences and "end" not in silences[-1]:
                silences[-1]["end"] = float(m.group(1))
                
    # Tính điểm giữa của các khoảng lặng
    split_points = []
    for s in silences:
        if "end" in s:
            split_points.append((s["start"] + s["end"]) / 2.0)
            
    chunks = []
    current_start = 0.0
    
    while current_start < duration:
        target_end = current_start + chunk_length_sec
        max_end = current_start + max_chunk_sec
        
        if max_end >= duration:
            # Đoạn cuối
            split_point = duration
        else:
            # Tìm khoảng lặng gần target_end nhất, nhưng không vượt quá max_end
            valid_splits = [p for p in split_points if p > current_start + 60 and p <= max_end]
            if valid_splits:
                # Chọn split gần target_end nhất
                split_point = min(valid_splits, key=lambda x: abs(x - target_end))
            else:
                # Hard split nếu không tìm thấy khoảng lặng
                split_point = target_end
                
        # Cắt file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            chunk_out = f.name
            
        cut_cmd = [
            "ffmpeg", "-y", "-ss", f"{current_start:.3f}",
            "-i", wav_path,
            "-t", f"{split_point - current_start:.3f}",
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
            chunk_out
        ]
        subprocess.run(cut_cmd, capture_output=True)
        
        if os.path.exists(chunk_out) and os.path.getsize(chunk_out) > 0:
            chunks.append((chunk_out, current_start))
            current_start = split_point
        else:
            try: os.remove(chunk_out)
            except: pass
            break  # ffmpeg couldn't cut anymore, break the loop
        
    return chunks
