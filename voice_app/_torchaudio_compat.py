"""
Compatibility shims for torchaudio 2.5+ which removed legacy APIs.
Import this module BEFORE importing pyannote.audio.

APIs shimmed:
  - torchaudio.get_audio_backend()
  - torchaudio.set_audio_backend()
  - torchaudio.list_audio_backends()
  - torchaudio.info()
  - torchaudio.AudioMetaData
  - huggingface_hub.hf_hub_download: use_auth_token → token
  - numpy.NaN (removed in NumPy 2.0)
"""
import numpy as np
if not hasattr(np, "NaN"):
    np.NaN = np.nan

# torch.load: force weights_only=False for PyTorch >= 2.6
import torch as _torch
_orig_torch_load = _torch.load
def _safe_torch_load(*args, **kwargs):
    kwargs["weights_only"] = False
    return _orig_torch_load(*args, **kwargs)
_torch.load = _safe_torch_load

import torchaudio


class _AudioMetaData:
    def __init__(self, sample_rate, num_frames, num_channels,
                 bits_per_sample=16, encoding="PCM_S"):
        self.sample_rate = sample_rate
        self.num_frames = num_frames
        self.num_channels = num_channels
        self.bits_per_sample = bits_per_sample
        self.encoding = encoding


def _torchaudio_info(path, backend=None):
    try:
        import soundfile as sf
        i = sf.info(str(path))
        return _AudioMetaData(i.samplerate, i.frames, i.channels)
    except Exception:
        waveform, sr = torchaudio.load(str(path))
        return _AudioMetaData(sr, waveform.shape[-1], waveform.shape[0])


if not hasattr(torchaudio, "AudioMetaData"):
    torchaudio.AudioMetaData = _AudioMetaData

# torchaudio 2.11 mặc định dùng torchcodec (cần FFmpeg không có sẵn).
# Thay thế hoàn toàn bằng soundfile để tránh torchcodec.
import soundfile as _sf


def _ta_load_soundfile(uri, frame_offset=0, num_frames=-1, normalize=True,
                        channels_first=True, format=None, buffer_size=4096, backend=None):
    import torch
    data, samplerate = _sf.read(str(uri), dtype="float32", always_2d=True)
    # data: [frames, channels] → transpose to [channels, frames]
    waveform = torch.from_numpy(data.T.copy())
    if frame_offset > 0 or (num_frames > 0 and num_frames < waveform.shape[-1]):
        start = frame_offset
        end = (frame_offset + num_frames) if num_frames > 0 else waveform.shape[-1]
        waveform = waveform[:, start:end]
    if not channels_first:
        waveform = waveform.T
    return waveform, samplerate


torchaudio.load = _ta_load_soundfile

if not hasattr(torchaudio, "get_audio_backend"):
    torchaudio.get_audio_backend = lambda: "soundfile"

if not hasattr(torchaudio, "set_audio_backend"):
    torchaudio.set_audio_backend = lambda backend: None

if not hasattr(torchaudio, "list_audio_backends"):
    torchaudio.list_audio_backends = lambda: ["soundfile"]

if not hasattr(torchaudio, "info"):
    torchaudio.info = _torchaudio_info


# huggingface_hub: redirect use_auth_token → token
import huggingface_hub as _hfhub

_orig_hf_hub_dl = _hfhub.hf_hub_download


def _patched_hf_hub_dl(*args, **kwargs):
    if "use_auth_token" in kwargs:
        kwargs["token"] = kwargs.pop("use_auth_token")
    return _orig_hf_hub_dl(*args, **kwargs)


_hfhub.hf_hub_download = _patched_hf_hub_dl

# Also patch on pyannote pipeline module if already imported
try:
    import pyannote.audio.core.pipeline as _ppl_mod
    _ppl_mod.hf_hub_download = _patched_hf_hub_dl
except ImportError:
    _ppl_mod = None

# torchaudio.backend.common shim (pyannote 3.1.x speaker_verification)
import sys
import types

if "torchaudio.backend" not in sys.modules:
    _backend_mod = types.ModuleType("torchaudio.backend")
    _common_mod = types.ModuleType("torchaudio.backend.common")
    _common_mod.AudioMetaData = _AudioMetaData
    _backend_mod.common = _common_mod
    sys.modules["torchaudio.backend"] = _backend_mod
    sys.modules["torchaudio.backend.common"] = _common_mod
    torchaudio.backend = _backend_mod
