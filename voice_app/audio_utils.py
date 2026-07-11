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
        # Gọt mép 0.2s ở 2 đầu để tránh tạp âm và tiếng người khác xen ngang
        seg_start = seg["start"] + 0.2
        seg_end   = seg["end"] - 0.2
        
        # Nếu gọt xong bị âm (đoạn quá ngắn), thì bỏ qua đoạn này
        if seg_end <= seg_start:
            continue
            
        take = min(seg_end - seg_start, max_total_sec - total)
        if take <= 0:
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

def split_audio_by_silence(wav_path: str, chunk_length_sec: float = 1800.0, max_chunk_sec: float = 2100.0) -> list:
    """
    VAD "nhẹ nhẹ" theo yêu cầu: Chỉ cắt bỏ những đoạn im lặng chết chóc > 15 giây.
    Mọi tiếng ngập ngừng, lật giấy, nói thầm đều được giữ lại 100%.
    """
    import webrtcvad
    import wave
    import tempfile
    import os

    duration = get_duration(wav_path)
    
    # Mức 3: Nhạy và khắt khe nhất. Bỏ qua hầu hết tiếng ồn, chỉ bắt tiếng người.
    vad = webrtcvad.Vad(3) 
    frame_duration_ms = 30
    
    with wave.open(wav_path, 'rb') as wf:
        sample_rate = wf.getframerate()
        sample_width = wf.getsampwidth()
        n_frames = wf.getnframes()
        raw_data = wf.readframes(n_frames)
        
    frame_size = int(sample_rate * (frame_duration_ms / 1000.0) * sample_width)
    frames = [raw_data[i:i+frame_size] for i in range(0, len(raw_data), frame_size)]
    
    is_speech_flags = []
    for f in frames:
        if len(f) == frame_size:
            is_speech_flags.append(vad.is_speech(f, sample_rate))
        else:
            is_speech_flags.append(False)
            
    # Đệm 0.45 giây (15 frames) trước và sau mỗi điểm nói để tránh lẹm chữ, giảm thu tạp âm
    ring_buffer_size = 15 
    smoothed_flags = [False] * len(is_speech_flags)
    
    for i, flag in enumerate(is_speech_flags):
        if flag:
            start = max(0, i - ring_buffer_size)
            end = min(len(smoothed_flags), i + ring_buffer_size + 1)
            for j in range(start, end):
                smoothed_flags[j] = True

    segments = []
    in_speech = False
    start_frame = 0
    for i, flag in enumerate(smoothed_flags):
        if flag and not in_speech:
            in_speech = True
            start_frame = i
        elif not flag and in_speech:
            in_speech = False
            segments.append((start_frame, i))
            
    if in_speech:
        segments.append((start_frame, len(smoothed_flags)))
        
    # GỘP NHẸ NHÀNG: Khoảng cách < 1.8 giây (60 frames) thì gộp luôn không cắt!
    merged_segments = []
    for seg in segments:
        if not merged_segments:
            merged_segments.append(seg)
        else:
            prev_start, prev_end = merged_segments[-1]
            if seg[0] - prev_end < 60:
                merged_segments[-1] = (prev_start, seg[1])
            else:
                merged_segments.append(seg)
                
    if not merged_segments:
        return [(wav_path, 0.0, [])]

    chunks = []
    current_chunk_frames = []
    current_chunk_mappings = []
    current_dense_start = 0.0
    current_chunk_orig_start = merged_segments[0][0] * 30 / 1000.0
    
    def finalize_chunk():
        nonlocal current_chunk_frames, current_chunk_mappings, current_dense_start, current_chunk_orig_start
        if not current_chunk_frames: return
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            chunk_out = f.name
        with wave.open(chunk_out, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(sample_width)
            wf.setframerate(sample_rate)
            wf.writeframes(b''.join(current_chunk_frames))
        chunks.append((chunk_out, current_chunk_orig_start, current_chunk_mappings))
        current_chunk_frames = []
        current_chunk_mappings = []
        current_dense_start = 0.0

    for start, end in merged_segments:
        seg_duration = (end - start) * 30 / 1000.0
        
        if current_dense_start + seg_duration > chunk_length_sec and current_dense_start > 0:
            finalize_chunk()
            current_chunk_orig_start = start * 30 / 1000.0
            
        orig_start = start * 30 / 1000.0
        orig_end = end * 30 / 1000.0
        dense_end = current_dense_start + (orig_end - orig_start)
        
        current_chunk_mappings.append({
            "orig_start": orig_start,
            "orig_end": orig_end,
            "dense_start": current_dense_start,
            "dense_end": dense_end
        })
        
        for i in range(start, end):
            current_chunk_frames.append(frames[i])
            
        current_dense_start = dense_end

    finalize_chunk()
    return chunks
