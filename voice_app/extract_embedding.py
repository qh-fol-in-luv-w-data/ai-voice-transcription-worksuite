#!/usr/bin/env python3
"""
Standalone script: Extract speaker embedding in a fresh subprocess.
Bypasses DNNL/NNPACK "could not create a primitive" error caused by Gunicorn --preload + fork.
Usage: python extract_embedding.py <wav_path> <hf_token> [start] [end]
Output: JSON array (embedding vector) written to stdout.
"""
import os
# MUST set before ANY torch/numpy import
os.environ["USE_NNPACK"] = "0"
os.environ["DNNL_PRIMITIVE_CACHE_CAPACITY"] = "0"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import sys
import json
import numpy as np


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Missing arguments: wav_path and hf_token required"}), file=sys.stderr)
        sys.exit(1)

    wav_path = sys.argv[1]
    hf_token = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None

    start = float(sys.argv[3]) if len(sys.argv) > 3 else None
    end   = float(sys.argv[4]) if len(sys.argv) > 4 else None

    import torch

    # Disable NNPACK / MKL-DNN
    if hasattr(torch.backends, 'nnpack'):
        torch.backends.nnpack.enabled = False
    if hasattr(torch.backends, 'mkldnn'):
        torch.backends.mkldnn.enabled = False
    torch.set_num_threads(1)

    # ── Fix 1: torch.load weights_only (PyTorch >= 2.6 mặc định True) ──────────
    # Triệt để override để không bị lỗi với mọi class của pyannote/pytorch_lightning/omegaconf
    import torch.serialization as _ts
    _orig_load = torch.load
    def _safe_load(*args, **kwargs):
        kwargs['weights_only'] = False
        return _orig_load(*args, **kwargs)
    torch.load = _safe_load
    # Override thêm _load internal nếu có
    if hasattr(_ts, '_load'):
        _orig_internal = _ts._load
        def _safe_internal(*args, **kwargs):
            kwargs.pop('weights_only', None)
            return _orig_internal(*args, **kwargs)
        _ts._load = _safe_internal

    # ── Fix 2: pyannote dùng use_auth_token (deprecated) → dùng token ──────────
    # (đã patch model.py, nhưng thêm env var làm fallback)
    if hf_token:
        os.environ["HUGGING_FACE_HUB_TOKEN"] = hf_token
        os.environ["HF_TOKEN"] = hf_token

    from pyannote.audio import Model
    from pyannote.audio.core.inference import Inference

    # Thử load model — nếu đã cache local thì không cần token nữa
    try:
        model = Model.from_pretrained("pyannote/embedding", token=hf_token)
    except TypeError:
        model = Model.from_pretrained("pyannote/embedding", use_auth_token=hf_token)

    inference = Inference(model, window="whole")

    # ── Fix 3: Đọc audio bằng soundfile thay vì torchaudio/torchcodec ──────────
    # torchaudio >= 2.5 dùng torchcodec cần FFmpeg đặc biệt → lỗi trên macOS
    import soundfile as sf
    import torch

    def load_wav_soundfile(path, start=None, end=None):
        """Load WAV bằng soundfile, resample nếu cần, trả về tensor [1, samples]."""
        data, sr = sf.read(path, dtype='float32', always_2d=True)
        # data shape: [samples, channels] → lấy channel đầu, mono
        data = data[:, 0]
        if start is not None and end is not None:
            s_idx = int(start * sr)
            e_idx = int(end * sr)
            data = data[s_idx:e_idx]
        # Resample về 16kHz nếu cần
        if sr != 16000:
            try:
                import resampy
                data = resampy.resample(data, sr, 16000)
            except ImportError:
                # fallback: scipy
                from scipy.signal import resample as sp_resample
                n_out = int(len(data) * 16000 / sr)
                data = sp_resample(data, n_out).astype('float32')
        return torch.tensor(data).unsqueeze(0).unsqueeze(0)  # [1, 1, samples]

    if start is not None and end is not None:
        waveform = load_wav_soundfile(wav_path, start, end)
    else:
        waveform = load_wav_soundfile(wav_path)

    with torch.inference_mode():
        embedding = model(waveform)
        if hasattr(embedding, 'data'):
            embedding = embedding.data
        embedding = embedding.squeeze().cpu().numpy()

    # Output embedding as JSON to stdout
    print(json.dumps(embedding.tolist()))
    sys.exit(0)


if __name__ == "__main__":
    main()
