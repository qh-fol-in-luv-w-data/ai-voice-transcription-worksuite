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
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=120)
    except subprocess.TimeoutExpired:
        try: os.remove(out)
        except: pass
        return None, "ffmpeg error: timeout"
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
    try:
        subprocess.run(cmd, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        pass
    return out


def concat_speaker_segments(wav_path: str, segs: list,
                            max_total_sec: float = 25.0,
                            min_seg_sec: float = 1.0) -> str:
    """
    Ghép nhiều đoạn của cùng 1 speaker thành 1 file WAV liên tục bằng FFmpeg filter_complex (1 lần gọi).

    Chiến lược:
    - Sắp xếp segments theo độ dài (dài trước)
    - Chọn các đoạn >= min_seg_sec cho đến khi đủ max_total_sec
    - Gọt mép 0.2s 2 đầu mỗi đoạn
    - Tạo filter_complex cắt và nối trong 1 tiến trình ffmpeg
    """
    import tempfile
    import subprocess
    import os

    duration = get_duration(wav_path)

    # Lọc & sắp xếp: ưu tiên đoạn dài, bỏ đoạn quá ngắn
    candidates = sorted(
        [s for s in segs if (s["end"] - s["start"]) >= min_seg_sec],
        key=lambda x: x["end"] - x["start"],
        reverse=True
    )
    if not candidates:
        return None

    filters = []
    inputs = []
    total = 0.0

    for i, seg in enumerate(candidates):
        seg_start = seg["start"] + 0.2
        seg_end   = seg["end"] - 0.2
        
        if seg_end <= seg_start:
            continue
            
        take = min(seg_end - seg_start, max_total_sec - total)
        if take <= 0:
            break

        filters.append(f"[0]atrim=start={seg_start:.3f}:duration={take:.3f},asetpts=PTS-STARTPTS[s{i}]")
        inputs.append(f"[s{i}]")
        total += take

    if not inputs:
        return None

    concat_filter = "".join(inputs) + f"concat=n={len(inputs)}:v=0:a=1[out]"
    full_filter = ";".join(filters) + ";" + concat_filter

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out = f.name

    cmd = [
        "ffmpeg", "-y", "-i", wav_path, 
        "-filter_complex", full_filter,
        "-map", "[out]", 
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", 
        out
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        try: os.remove(out)
        except: pass
        return None

    if r.returncode != 0:
        try: os.remove(out)
        except: pass
        return None
    return out

def split_audio_by_silence(wav_path: str, chunk_length_sec: float = 900.0, max_chunk_sec: float = 1200.0, output_dir: str = None) -> list:
    """
    Bỏ VAD theo yêu cầu.
    Chỉ cắt audio thành các đoạn có độ dài tối đa chunk_length_sec để gửi STT.
    """
    import wave
    import tempfile
    import os

    duration = get_duration(wav_path)
    
    with wave.open(wav_path, 'rb') as wf:
        sample_rate = wf.getframerate()
        sample_width = wf.getsampwidth()
        n_frames = wf.getnframes()
        raw_data = wf.readframes(n_frames)
        
    chunks = []
    frames_per_sec = sample_rate * sample_width
    chunk_bytes = int(chunk_length_sec * frames_per_sec)
    
    # Đảm bảo chunk_bytes là bội số của (sample_width * channels) - ở đây wav luôn 1 channel
    block_align = sample_width
    chunk_bytes = (chunk_bytes // block_align) * block_align

    for i, start_byte in enumerate(range(0, len(raw_data), chunk_bytes)):
        end_byte = min(start_byte + chunk_bytes, len(raw_data))
        chunk_data = raw_data[start_byte:end_byte]
        
        orig_start = start_byte / frames_per_sec
        orig_end = end_byte / frames_per_sec
        dense_end = orig_end - orig_start
        
        mappings = [{
            "orig_start": orig_start,
            "orig_end": orig_end,
            "dense_start": 0.0,
            "dense_end": dense_end
        }]
        
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            chunk_out = os.path.join(output_dir, f"chunk_{i}.wav")
        else:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                chunk_out = f.name
                
        with wave.open(chunk_out, 'wb') as wf_out:
            wf_out.setnchannels(1)
            wf_out.setsampwidth(sample_width)
            wf_out.setframerate(sample_rate)
            wf_out.writeframes(chunk_data)
            
        chunks.append((chunk_out, orig_start, mappings))

    return chunks
